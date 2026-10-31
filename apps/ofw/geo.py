"""Small geo helpers for the OFW emergency features.

The portal does not use a paid maps provider.  Distances and compass
directions are computed locally, and the "where am I" label comes from a free
reverse-geocoding service with a second provider as a fallback.  Everything is
best-effort: if both services are unreachable the caller still gets usable
coordinates and distances.
"""

import json
import math
import urllib.parse
import urllib.request

from django.core.cache import cache

EARTH_RADIUS_KM = 6371.0088

COMPASS_POINTS = (
    'north', 'north-east', 'east', 'south-east',
    'south', 'south-west', 'west', 'north-west',
)

GEOCODE_CACHE_SECONDS = 60 * 60 * 24  # 24 hours per ~100 m cell
REQUEST_TIMEOUT = 5


def distance_km(lat1, lng1, lat2, lng2):
    """Great-circle distance between two points in kilometres."""
    lat1, lng1, lat2, lng2 = map(float, (lat1, lng1, lat2, lng2))
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_degrees(lat1, lng1, lat2, lng2):
    """Initial bearing from point 1 to point 2 (0 = north, 90 = east)."""
    lat1, lng1, lat2, lng2 = map(float, (lat1, lng1, lat2, lng2))
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_lambda = math.radians(lng2 - lng1)
    y = math.sin(d_lambda) * math.cos(phi2)
    x = (
        math.cos(phi1) * math.sin(phi2)
        - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    )
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass_direction(bearing):
    """Turn a bearing into one of eight plain-English directions."""
    index = int(((float(bearing) % 360) / 45) + 0.5) % 8
    return COMPASS_POINTS[index]


def format_distance(km):
    """Human-friendly distance label (metres below 1 km)."""
    km = float(km)
    if km < 1:
        metres = max(10, round(km * 1000 / 10) * 10)
        return f'{metres:.0f} m'
    if km < 10:
        return f'{km:.1f} km'
    return f'{km:.0f} km'


def walking_minutes(km):
    """Rough walking time at a relaxed 4.5 km/h pace."""
    return max(1, round(float(km) / 4.5 * 60))


def _http_json(url, headers=None):
    request = urllib.request.Request(
        url,
        headers={
            'User-Agent': 'KabayaniTrack/1.0 (OFW emergency portal)',
            'Accept': 'application/json',
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode('utf-8', 'replace'))


def _bigdatacloud(lat, lng):
    params = urllib.parse.urlencode({
        'latitude': lat,
        'longitude': lng,
        'localityLanguage': 'en',
    })
    url = 'https://api.bigdatacloud.net/data/reverse-geocode-client?' + params
    data = _http_json(url)
    if not isinstance(data, dict):
        return None

    parts = []
    for key in ('locality', 'city', 'principalSubdivision', 'countryName'):
        value = (data.get(key) or '').strip()
        if value and value not in parts:
            parts.append(value)
    label = ', '.join(parts)
    if not label:
        return None
    return {
        'label': label,
        'city': (data.get('city') or data.get('locality') or '').strip(),
        'region': (data.get('principalSubdivision') or '').strip(),
        'country': (data.get('countryName') or '').strip(),
        'source': 'bigdatacloud',
    }


def _nominatim(lat, lng):
    params = urllib.parse.urlencode({
        'format': 'jsonv2',
        'lat': lat,
        'lon': lng,
        'zoom': 16,
        'addressdetails': 1,
    })
    url = 'https://nominatim.openstreetmap.org/reverse?' + params
    data = _http_json(url)
    if not isinstance(data, dict):
        return None
    address = data.get('address') or {}

    city = (
        address.get('city') or address.get('town') or address.get('village')
        or address.get('municipality') or address.get('suburb') or ''
    ).strip()
    region = (address.get('state') or address.get('region') or '').strip()
    country = (address.get('country') or '').strip()
    parts = []
    for value in (city, region, country):
        if value and value not in parts:
            parts.append(value)
    label = ', '.join(parts) or (data.get('display_name') or '').strip()
    if not label:
        return None
    return {
        'label': label,
        'city': city,
        'region': region,
        'country': country,
        'source': 'nominatim',
    }


def reverse_geocode(lat, lng):
    """Return ``{'label', 'city', 'region', 'country'}`` for a coordinate.

    Results are cached in ~100 m cells so repeat lookups (the live guide
    refreshes position often) never hammer the free services.
    """
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return {}

    cache_key = f'ofw:geocode:{lat:.3f}:{lng:.3f}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result = {}
    for provider in (_bigdatacloud, _nominatim):
        try:
            result = provider(lat, lng) or {}
        except Exception:
            result = {}
        if result:
            break

    # Cache failures briefly as well so a broken network does not slow every
    # request down; a later refresh can still pick up a real answer.
    cache.set(cache_key, result, GEOCODE_CACHE_SECONDS if result else 300)
    return result
