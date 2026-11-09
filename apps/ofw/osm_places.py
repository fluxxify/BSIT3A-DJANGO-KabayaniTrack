"""Live safe-place fallback backed by OpenStreetMap.

The seeded :class:`~apps.ofw.models.SafeLocation` table only covers the cities
and countries where the project has data. When an OFW is somewhere else, the
nearest registered place can be tens of kilometres away, so this module asks
the free Overpass API for nearby police stations, fire stations, hospitals and
clinics. Results are cached briefly and treated as best-effort: any network
problem simply returns an empty list and the registered places remain in use.
"""

import json
import logging
import math
import urllib.parse
import urllib.request

from django.core.cache import cache

from .geo import (
    bearing_degrees,
    compass_direction,
    distance_km,
    format_distance,
    walking_minutes,
)

logger = logging.getLogger(__name__)

# If the closest registered place is farther than this, ask OpenStreetMap.
LIVE_FALLBACK_KM = 10

DEFAULT_RADIUS_KM = 15
CACHE_SECONDS = 60 * 15
FAILURE_CACHE_SECONDS = 60 * 5
REQUEST_TIMEOUT = 10

OVERPASS_ENDPOINTS = (
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
)

# Used when Overpass is unavailable. Nominatim is the same free service the
# reverse geocoder already uses, and its bounded search works well for POIs.
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
NOMINATIM_SEARCHES = (
    ('police station', 'police_station', 'Police Station'),
    ('hospital', 'hospital', 'Hospital'),
    ('fire station', 'fire', 'Fire Station'),
)

# amenity tag -> (location type key, human label)
AMENITY_TYPES = {
    'police': ('police_station', 'Police Station'),
    'fire_station': ('fire', 'Fire Station'),
    'hospital': ('hospital', 'Hospital'),
    'clinic': ('other', 'Clinic'),
}

QUERY_TEMPLATE = """[out:json][timeout:10];
(
  node["amenity"~"^(police|fire_station|hospital|clinic)$"](around:{radius},{lat:.6f},{lng:.6f});
  way["amenity"~"^(police|fire_station|hospital|clinic)$"](around:{radius},{lat:.6f},{lng:.6f});
);
out center tags;"""


def _request_overpass(url, query):
    """POST an Overpass query and return the decoded JSON response."""
    payload = urllib.parse.urlencode({'data': query}).encode('utf-8')
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            'User-Agent': 'KabayaniTrack/1.0 (OFW emergency portal)',
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode('utf-8', 'replace'))


def _fetch_overpass(lat, lng, radius_m):
    """Try each Overpass endpoint until one returns usable JSON."""
    query = QUERY_TEMPLATE.format(radius=radius_m, lat=lat, lng=lng)
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            data = _request_overpass(endpoint, query)
        except Exception as exc:  # network, timeout, HTTP, bad JSON
            logger.warning('OpenStreetMap lookup failed via %s: %s', endpoint, exc)
            continue
        if isinstance(data, dict):
            return data
    return None


def _first_tag(tags, *keys):
    for key in keys:
        value = (tags.get(key) or '').strip()
        if value:
            return value
    return ''


def _address(tags):
    street = ' '.join(
        part for part in (
            _first_tag(tags, 'addr:housenumber'),
            _first_tag(tags, 'addr:street'),
        ) if part
    )
    parts = [street]
    for key in ('addr:barangay', 'addr:suburb', 'addr:district'):
        value = _first_tag(tags, key)
        if value and value not in parts:
            parts.append(value)
    return ', '.join(part for part in parts if part)


def _normalise_overpass(data, default_city='', default_country=''):
    """Turn an Overpass response into plain safe-place dictionaries."""
    rows = []
    seen = set()

    for element in data.get('elements', []) if isinstance(data, dict) else []:
        tags = element.get('tags') or {}
        amenity = tags.get('amenity') or ''
        if amenity not in AMENITY_TYPES:
            continue

        lat = element.get('lat')
        lng = element.get('lon')
        if lat is None or lng is None:
            center = element.get('center') or {}
            lat = center.get('lat')
            lng = center.get('lon')
        if lat is None or lng is None:
            continue

        type_key, type_label = AMENITY_TYPES[amenity]
        name = (
            _first_tag(tags, 'name', 'operator', 'brand')
            or f'{type_label} (OpenStreetMap)'
        )

        key = (name.lower(), round(float(lat), 4), round(float(lng), 4))
        if key in seen:
            continue
        seen.add(key)

        city = _first_tag(
            tags, 'addr:city', 'addr:town', 'addr:municipality',
            'addr:village', 'addr:suburb',
        ) or default_city
        country = _first_tag(tags, 'addr:country') or default_country

        rows.append({
            'id': 'osm-{}-{}'.format(element.get('type', 'node'), element.get('id', '')),
            'name': name,
            'type': type_label,
            'type_key': type_key,
            'city': city,
            'country': country,
            'address': _address(tags),
            'phone': _first_tag(
                tags, 'phone', 'contact:phone', 'emergency:phone', 'mobile',
            ),
            'emergency_phone': '',
            'latitude': float(lat),
            'longitude': float(lng),
            'lat': float(lat),
            'lng': float(lng),
            'source': 'openstreetmap',
        })
    return rows


def _get_json(url):
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'KabayaniTrack/1.0 (OFW emergency portal)',
            'Accept': 'application/json',
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode('utf-8', 'replace'))


def _nominatim_viewbox(lat, lng, radius_km):
    lat_delta = float(radius_km) / 111.0
    lng_delta = float(radius_km) / max(
        111.0 * math.cos(math.radians(lat)), 1.0,
    )
    return '{left:.6f},{top:.6f},{right:.6f},{bottom:.6f}'.format(
        left=lng - lng_delta,
        top=lat + lat_delta,
        right=lng + lng_delta,
        bottom=lat - lat_delta,
    )


def _fetch_nominatim(lat, lng, radius_km, default_city='', default_country=''):
    """Search nearby POIs with Nominatim when Overpass is unavailable.

    Nominatim has no radius search, so a bounded viewbox is used and results
    are filtered to the requested radius afterwards. Three small cached
    searches (police, hospital, fire) are enough for the fallback.
    """
    viewbox = _nominatim_viewbox(lat, lng, radius_km)
    rows = []
    seen = set()

    for term, type_key, type_label in NOMINATIM_SEARCHES:
        params = urllib.parse.urlencode({
            'q': term,
            'format': 'jsonv2',
            'limit': 10,
            'viewbox': viewbox,
            'bounded': 1,
            'addressdetails': 1,
            'extratags': 1,
        })
        try:
            data = _get_json(f'{NOMINATIM_URL}?{params}')
        except Exception as exc:
            logger.warning('Nominatim safe-place lookup failed: %s', exc)
            continue
        if not isinstance(data, list):
            continue

        for item in data:
            try:
                place_lat = float(item.get('lat'))
                place_lng = float(item.get('lon'))
            except (TypeError, ValueError):
                continue
            if distance_km(lat, lng, place_lat, place_lng) > radius_km + 1:
                continue

            # Skip clearly unrelated results (for example a barangay that
            # happens to be named "Hospital").
            place_class = (item.get('class') or '').lower()
            if place_class and place_class not in (
                'amenity', 'building', 'healthcare', 'emergency',
            ):
                continue

            address = item.get('address') or {}
            city = (
                address.get('city') or address.get('town')
                or address.get('village') or address.get('municipality')
                or default_city
            )
            country = address.get('country') or default_country
            display = (item.get('display_name') or '').strip()
            name = (item.get('name') or '').strip()
            if not name:
                name = display.split(',')[0].strip() or type_label

            key = (name.lower(), round(place_lat, 4), round(place_lng, 4))
            if key in seen:
                continue
            seen.add(key)

            address_parts = [
                address.get('house_number') or '',
                address.get('road') or '',
                address.get('suburb') or '',
                city,
            ]
            extratags = item.get('extratags') or {}

            rows.append({
                'id': 'osm-nominatim-{}'.format(item.get('place_id') or len(rows)),
                'name': name,
                'type': type_label,
                'type_key': type_key,
                'city': city,
                'country': country,
                'address': ', '.join(
                    part for part in dict.fromkeys(address_parts) if part
                ),
                'phone': _first_tag(extratags, 'phone', 'contact:phone'),
                'emergency_phone': '',
                'latitude': place_lat,
                'longitude': place_lng,
                'lat': place_lat,
                'lng': place_lng,
                'source': 'openstreetmap',
            })
    return rows


def _cached_places(lat, lng, radius_km, default_city, default_country):
    # Round to roughly a 1 km cell so nearby viewers share one cached lookup.
    cache_key = 'osm-safe:{:.2f}:{:.2f}:{}'.format(lat, lng, radius_km)
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Nominatim first: its bounded search is the most reliable free option and
    # it is already used by the reverse geocoder. Overpass is the richer
    # fallback when Nominatim returns nothing.
    rows = _fetch_nominatim(
        lat, lng, radius_km, default_city, default_country,
    )

    if not rows:
        data = _fetch_overpass(lat, lng, int(radius_km * 1000))
        rows = _normalise_overpass(data, default_city, default_country) if data else []

    if not rows:
        cache.set(cache_key, [], FAILURE_CACHE_SECONDS)
        return []

    cache.set(cache_key, rows, CACHE_SECONDS)
    return rows


def nearby_safe_places(
    lat,
    lng,
    radius_km=DEFAULT_RADIUS_KM,
    limit=8,
    default_city='',
    default_country='',
):
    """Return OpenStreetMap safe places sorted by distance from a point.

    The public shape matches ``views.nearest_safe_places`` so templates can use
    live and registered places interchangeably. Demand failures return ``[]``.
    """
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return []

    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        return []

    raw_rows = _cached_places(
        lat, lng, float(radius_km), default_city, default_country,
    )

    rows = []
    for place in raw_rows:
        place_lat = float(place['latitude'])
        place_lng = float(place['longitude'])
        km = distance_km(lat, lng, place_lat, place_lng)
        bearing = bearing_degrees(lat, lng, place_lat, place_lng)
        row = dict(place)
        row.update({
            'distance_km': round(km, 3),
            'distance_text': format_distance(km),
            'walking_minutes': walking_minutes(km),
            'bearing': round(bearing, 1),
            'direction': compass_direction(bearing),
            'maps_url': (
                'https://www.google.com/maps/dir/?api=1&destination='
                f'{place_lat},{place_lng}'
            ),
        })
        rows.append(row)

    rows.sort(key=lambda row: (row['distance_km'], row['name'].lower()))
    return rows[:limit] if limit else rows
