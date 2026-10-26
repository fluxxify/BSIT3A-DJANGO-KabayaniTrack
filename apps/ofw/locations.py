"""World countries and city suggestions for OFW profile dropdowns.

The dataset in ``data/world_locations.json`` combines the dr5hn country list
with populated places (5,000+ residents) from GeoNames and the curated
destination cities that this module used to hard-code.  ``COUNTRY_CHOICES``
feeds the country datalist, ``CITIES_BY_COUNTRY`` powers the dependent city
datalist (served on demand by the ``portal_cities`` view), and ``COUNTRY_GEO``
maps a country to its ISO2 code and map centroid.  Values stay plain strings
because the underlying model fields are free-text ``CharField``s, so an OFW may
still type a destination that is not listed here.
"""

import json
from pathlib import Path

_DATA_FILE = Path(__file__).resolve().parent / 'data' / 'world_locations.json'
_COUNTRIES = json.loads(_DATA_FILE.read_text(encoding='utf-8'))['countries']

COUNTRY_CHOICES = [country['name'] for country in _COUNTRIES]
CITIES_BY_COUNTRY = {country['name']: country['cities'] for country in _COUNTRIES}
COUNTRY_GEO = {
    country['name']: (country['iso2'], country['lat'], country['lng'])
    for country in _COUNTRIES
}
_COUNTRY_BY_FOLDED = {name.casefold(): name for name in COUNTRY_CHOICES}
_COUNTRY_BY_ISO2 = {
    iso2.casefold(): name for name, (iso2, _lat, _lng) in COUNTRY_GEO.items()
}

# Common shorthand so a typed value still resolves to the canonical name.
COUNTRY_ALIASES = {
    'usa': 'United States',
    'u.s.a.': 'United States',
    'u.s.a': 'United States',
    'united states of america': 'United States',
    'america': 'United States',
    'uk': 'United Kingdom',
    'u.k.': 'United Kingdom',
    'u.k': 'United Kingdom',
    'great britain': 'United Kingdom',
    'britain': 'United Kingdom',
    'england': 'United Kingdom',
    'scotland': 'United Kingdom',
    'wales': 'United Kingdom',
    'northern ireland': 'United Kingdom',
    'uae': 'United Arab Emirates',
    'u.a.e.': 'United Arab Emirates',
    'u.a.e': 'United Arab Emirates',
    'emirates': 'United Arab Emirates',
    'ksa': 'Saudi Arabia',
    'saudi': 'Saudi Arabia',
    'kingdom of saudi arabia': 'Saudi Arabia',
    'hong kong s.a.r.': 'Hong Kong',
    'hong kong sar': 'Hong Kong',
    'hong kong sar china': 'Hong Kong',
    'hongkong': 'Hong Kong',
    'macao': 'Macau',
    'macau s.a.r.': 'Macau',
    'macao sar china': 'Macau',
    'czechia': 'Czech Republic',
    'turkiye': 'Turkey',
    'türkiye': 'Turkey',
    'macedonia': 'North Macedonia',
    'burma': 'Myanmar',
    'swaziland': 'Eswatini',
    'east timor': 'Timor-Leste',
    'holland': 'Netherlands',
    'vatican': 'Vatican City',
    'st. kitts and nevis': 'Saint Kitts and Nevis',
    'st kitts and nevis': 'Saint Kitts and Nevis',
    'st. lucia': 'Saint Lucia',
    'st lucia': 'Saint Lucia',
    'st vincent and the grenadines': 'Saint Vincent and the Grenadines',
    'sao tome': 'Sao Tome and Principe',
    'republic of china': 'Taiwan',
    'korea': 'South Korea',
    'republic of korea': 'South Korea',
    'korea, republic of': 'South Korea',
    'dprk': 'North Korea',
    "korea, democratic people's republic of": 'North Korea',
    'russian federation': 'Russia',
    'viet nam': 'Vietnam',
    'brunei darussalam': 'Brunei',
    'ivory coast': 'Ivory Coast',
    "cote d'ivoire": 'Ivory Coast',
    "côte d'ivoire": 'Ivory Coast',
    'palestinian territories': 'Palestine',
    'taiwan, province of china': 'Taiwan',
    'british virgin islands': 'Virgin Islands (British)',
    'u.s. virgin islands': 'Virgin Islands (US)',
    'us virgin islands': 'Virgin Islands (US)',
    'st. barthelemy': 'Saint Barthelemy',
    'st barthelemy': 'Saint Barthelemy',
    'st. martin': 'Saint-Martin',
    'st martin': 'Saint-Martin',
    'saint martin': 'Saint-Martin',
    'st. pierre and miquelon': 'Saint Pierre and Miquelon',
    'st. vincent and the grenadines': 'Saint Vincent and the Grenadines',
    'congo, democratic republic of the': 'Democratic Republic of the Congo',
    'drc': 'Democratic Republic of the Congo',
    'congo-brazzaville': 'Republic of the Congo',
    'congo-kinshasa': 'Democratic Republic of the Congo',
}


def canonical_country(country):
    """Return the dataset's canonical name for a free-text country value.

    Profiles store plain strings, so ``UAE``, ``uae`` and ``United Arab
    Emirates`` should all resolve to the same hotline set.  Unknown values are
    returned stripped but otherwise untouched, which keeps typo-tolerant DB
    matching possible.
    """
    value = (country or '').strip()
    if not value:
        return ''
    folded = value.casefold()
    if folded in _COUNTRY_BY_FOLDED:
        return _COUNTRY_BY_FOLDED[folded]
    alias = COUNTRY_ALIASES.get(folded)
    if alias:
        return alias
    return _COUNTRY_BY_ISO2.get(folded, value)


def cities_for_country(country):
    """Return the city suggestions for ``country``, tolerating case and aliases."""
    country = (country or '').strip()
    if not country:
        return []
    if country in CITIES_BY_COUNTRY:
        return CITIES_BY_COUNTRY[country]
    folded = country.casefold()
    for name, cities in CITIES_BY_COUNTRY.items():
        if name.casefold() == folded:
            return cities
    alias = COUNTRY_ALIASES.get(folded)
    if alias:
        return CITIES_BY_COUNTRY.get(alias, [])
    return []


# Data sources: dr5hn/countries-states-cities-database (countries) and
# GeoNames cities5000 (populated places), merged with the originally curated
# destination cities.  Regenerate the JSON rather than editing it by hand.
