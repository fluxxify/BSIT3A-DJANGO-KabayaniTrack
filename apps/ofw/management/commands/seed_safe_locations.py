"""Seed the database with Philippine safe locations for local testing.

Usage:
    python manage.py seed_safe_locations
    python manage.py seed_safe_locations --country Philippines
    python manage.py seed_safe_locations --clear

The command is idempotent: running it again updates the existing rows instead
of creating duplicates, so it is safe to run on the live site after a deploy.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ofw.models import SafeLocation

POLICE = SafeLocation.LocationType.POLICE_STATION
HOSPITAL = SafeLocation.LocationType.HOSPITAL
EMBASSY = SafeLocation.LocationType.EMBASSY
POLO = SafeLocation.LocationType.POLO
OWWA = SafeLocation.LocationType.OWWA
FIRE = SafeLocation.LocationType.FIRE
OTHER = SafeLocation.LocationType.OTHER

# (name, type, city, address, phone, latitude, longitude)
PHILIPPINES_SAFE_LOCATIONS = [
    # --- Metro Manila -----------------------------------------------------
    ('Manila Police District Headquarters', POLICE, 'Manila',
     'UN Avenue, Ermita, Manila', '911', 14.582600, 120.982200),
    ('Manila Police Station 1 (City Hall)', POLICE, 'Manila',
     'Padre Burgos Avenue, Intramuros, Manila', '911', 14.589600, 120.981200),
    ('Philippine General Hospital', HOSPITAL, 'Manila',
     'Taft Avenue, Ermita, Manila', '', 14.578600, 120.985700),
    ('Ospital ng Maynila Medical Center', HOSPITAL, 'Manila',
     'Quirino Avenue, Malate, Manila', '', 14.576500, 120.982200),
    ('Bureau of Fire Protection - Manila', FIRE, 'Manila',
     'A. Soriano Avenue, Intramuros, Manila', '911', 14.595500, 120.984800),
    ('National Bureau of Investigation (NBI)', OTHER, 'Manila',
     'Taft Avenue, Ermita, Manila', '', 14.602600, 120.993800),
    ('Embassy of the United States - Manila', EMBASSY, 'Manila',
     '1201 Roxas Boulevard, Ermita, Manila', '', 14.578400, 120.977800),
    ('Embassy of Japan - Manila', EMBASSY, 'Manila',
     '2627 Roxas Boulevard, Pasay City', '', 14.582100, 120.976800),
    ('Camp Crame - PNP National Headquarters', POLICE, 'Quezon City',
     'Boni Serrano Avenue, Camp Crame, Quezon City', '911', 14.608500, 121.057500),
    ('Quezon City Police District (Camp Karingal)', POLICE, 'Quezon City',
     'Sikatuna Village, Quezon City', '911', 14.635500, 121.043700),
    ('East Avenue Medical Center', HOSPITAL, 'Quezon City',
     'East Avenue, Diliman, Quezon City', '', 14.638900, 121.043900),
    ("St. Luke's Medical Center - Quezon City", HOSPITAL, 'Quezon City',
     '279 E. Rodriguez Sr. Boulevard, Quezon City', '', 14.621800, 121.026600),
    ('Philippine Heart Center', HOSPITAL, 'Quezon City',
     'East Avenue, Diliman, Quezon City', '', 14.639500, 121.047900),
    ('Makati Central Police Station', POLICE, 'Makati',
     'Ayala Avenue, Makati City', '911', 14.554700, 121.024400),
    ('Makati Medical Center', HOSPITAL, 'Makati',
     '2 Amorsolo Street, Legazpi Village, Makati City', '', 14.558600, 121.014600),
    ('Pasig City Police Station', POLICE, 'Pasig',
     'Caruncho Avenue, Pasig City', '911', 14.576400, 121.085100),
    ('The Medical City - Ortigas', HOSPITAL, 'Pasig',
     'Ortigas Avenue, Pasig City', '', 14.585500, 121.062300),
    ('Taguig City Police Station', POLICE, 'Taguig',
     'Gen. Luna Street, Taguig City', '911', 14.517600, 121.050900),
    ('Caloocan City Police Station', POLICE, 'Caloocan',
     '10th Avenue, Caloocan City', '911', 14.657000, 120.983000),
    ('Department of Migrant Workers (DMW)', POLO, 'Mandaluyong',
     'EDSA corner Ortigas Avenue, Mandaluyong City', '', 14.579200, 121.035700),
    ('OWWA Central Office', OWWA, 'Pasay',
     'CCP Complex, Roxas Boulevard, Pasay City', '', 14.556700, 120.987600),
    ('DFA Office of Consular Affairs (ASEANA)', EMBASSY, 'Paranaque',
     'ASEANA Business Park, Macapagal Boulevard, Paranaque City', '',
     14.514600, 120.996000),
    # --- Luzon ------------------------------------------------------------
    ('Baguio City Police Office', POLICE, 'Baguio',
     'Abanao Street, Baguio City', '911', 16.408600, 120.598600),
    ('Baguio General Hospital and Medical Center', HOSPITAL, 'Baguio',
     'Gov. Pack Road, Baguio City', '', 16.402300, 120.593900),
    ('Batangas City Police Station', POLICE, 'Batangas City',
     'P. Burgos Street, Batangas City', '911', 13.756500, 121.058300),
    ('Batangas Medical Center', HOSPITAL, 'Batangas City',
     'Kumintang Ibaba, Batangas City', '', 13.756000, 121.054000),
    ('Angeles City Police Office', POLICE, 'Angeles City',
     'Sto. Rosario Street, Angeles City, Pampanga', '911', 15.145000, 120.588700),
    ('The Medical City Clark', HOSPITAL, 'Mabalacat',
     'Clark Freeport Zone, Mabalacat, Pampanga', '', 15.177000, 120.541000),
    # --- Visayas ----------------------------------------------------------
    ('Cebu City Police Office', POLICE, 'Cebu City',
     'Sergio Osmena Boulevard, Cebu City', '911', 10.296500, 123.902000),
    ('Chong Hua Hospital', HOSPITAL, 'Cebu City',
     'Don Mariano Cui Street, Cebu City', '', 10.309600, 123.893000),
    ('Vicente Sotto Memorial Medical Center', HOSPITAL, 'Cebu City',
     'B. Rodriguez Street, Cebu City', '', 10.300600, 123.890900),
    ('Iloilo City Police Office', POLICE, 'Iloilo City',
     'Iznart Street, Iloilo City', '911', 10.720200, 122.562100),
    ('Western Visayas Medical Center', HOSPITAL, 'Iloilo City',
     'Q. Abeto Street, Mandurriao, Iloilo City', '', 10.729500, 122.551300),
    ('Bacolod City Police Office', POLICE, 'Bacolod',
     'San Juan Street, Bacolod City', '911', 10.676500, 122.950900),
    ('Corazon Locsin Montelibano Memorial Regional Hospital', HOSPITAL, 'Bacolod',
     'Lacson Street, Bacolod City', '', 10.670000, 122.953000),
    # --- Negros (Masulog / Canlaon / La Castellana) -----------------------
    # Real barangay-level places so "nearest safe place" works in the
    # mountain barangays around Masulog, not just in the big cities.
    ('Masulog Barangay Health Center', HOSPITAL, 'La Castellana',
     'Vallehermoso - Canlaon City - La Castellana Road, Masulog, La Castellana, Negros Occidental',
     '', 10.359540, 123.170334),
    ('Canlaon City Police Station', POLICE, 'Canlaon City',
     'Vallehermoso - Canlaon City - La Castellana Road, Uptown, Mabigo, Canlaon, Negros Oriental',
     '911', 10.383766, 123.213462),
    ('Canlaon District Hospital', HOSPITAL, 'Canlaon City',
     'Mabigo, Canlaon City, Negros Oriental', '', 10.401160, 123.213366),
    ('La Castellana Police Station', POLICE, 'La Castellana',
     'Feria Street, Robles, La Castellana, Negros Occidental',
     '911', 10.322445, 123.019797),
    ('La Castellana Rural Health Unit', HOSPITAL, 'La Castellana',
     'Poblacion, La Castellana, Negros Occidental', '', 10.323600, 123.021000),
    # --- Mindanao ---------------------------------------------------------
    ('Davao City Police Office', POLICE, 'Davao City',
     'San Pedro Street, Davao City', '911', 7.067200, 125.608700),
    ('Southern Philippines Medical Center', HOSPITAL, 'Davao City',
     'JP Laurel Avenue, Davao City', '', 7.086000, 125.600000),
    ('Cagayan de Oro City Police Office', POLICE, 'Cagayan de Oro',
     'Don Apolinar Velez Street, Cagayan de Oro City', '911', 8.482200, 124.647200),
    ('Northern Mindanao Medical Center', HOSPITAL, 'Cagayan de Oro',
     'Capitol Compound, Cagayan de Oro City', '', 8.483300, 124.642000),
    ('Zamboanga City Police Office', POLICE, 'Zamboanga City',
     'Valderosa Street, Zamboanga City', '911', 6.910300, 122.075000),
    ('Zamboanga City Medical Center', HOSPITAL, 'Zamboanga City',
     'Dr. Evangelista Street, Zamboanga City', '', 6.910000, 122.079000),
]


# (country, name, type, city, address, phone, latitude, longitude)
# Safe places for the countries where KabayaniTrack OFWs are deployed, so the
# nearest-safe-place guide works wherever the OFW actually is.
OVERSEAS_SAFE_LOCATIONS = [
    # --- Hong Kong --------------------------------------------------------
    ('Hong Kong', 'Philippine Consulate General Hong Kong', EMBASSY, 'Hong Kong',
     '14/F United Centre, 95 Queensway, Admiralty', '+852 2823 8500',
     22.279370, 114.165470),
    ('Hong Kong', 'POLO Hong Kong', POLO, 'Hong Kong',
     '14/F United Centre, 95 Queensway, Admiralty', '+852 2866 0543',
     22.279300, 114.165300),
    ('Hong Kong', 'OWWA Hong Kong', OWWA, 'Hong Kong',
     '14/F United Centre, 95 Queensway, Admiralty', '+852 2866 0641',
     22.279400, 114.165500),
    ('Hong Kong', 'Central Police Station', POLICE, 'Hong Kong',
     '9 Justice Drive, Central', '999', 22.279700, 114.159800),
    ('Hong Kong', 'Wan Chai Police Station', POLICE, 'Hong Kong',
     '1 Arsenal Street, Wan Chai', '999', 22.277500, 114.173000),
    ('Hong Kong', 'Queen Mary Hospital', HOSPITAL, 'Hong Kong',
     '102 Pok Fu Lam Road', '+852 2255 3838', 22.270700, 114.130400),
    # --- Saudi Arabia -----------------------------------------------------
    ('Saudi Arabia', 'Philippine Embassy Riyadh', EMBASSY, 'Riyadh',
     'Diplomatic Quarter, Riyadh', '+966 11 488 0899',
     24.690700, 46.627000),
    ('Saudi Arabia', 'POLO Riyadh', POLO, 'Riyadh',
     'Diplomatic Quarter, Riyadh', '+966 11 488 0899',
     24.690300, 46.626500),
    ('Saudi Arabia', 'OWWA Riyadh', OWWA, 'Riyadh',
     'Diplomatic Quarter, Riyadh', '+966 11 488 0899',
     24.691000, 46.627500),
    ('Saudi Arabia', 'Riyadh Police Department', POLICE, 'Riyadh',
     'Al Olaya, Riyadh', '999', 24.694000, 46.685000),
    ('Saudi Arabia', 'King Fahd Medical City', HOSPITAL, 'Riyadh',
     'Al Mursalat, Riyadh', '997', 24.710000, 46.675000),
    ('Saudi Arabia', 'Philippine Consulate General Jeddah', EMBASSY, 'Jeddah',
     'Al Andalus, Jeddah', '+966 12 660 0345', 21.543300, 39.172800),
    ('Saudi Arabia', 'King Fahd General Hospital Jeddah', HOSPITAL, 'Jeddah',
     'Al Sharafeyah, Jeddah', '997', 21.516900, 39.174700),
    ('Saudi Arabia', 'POLO Dammam', POLO, 'Dammam',
     'Al Faisaliyah, Dammam', '+966 13 834 5555', 26.420700, 50.088800),
    ('Saudi Arabia', 'King Fahd Specialist Hospital Dammam', HOSPITAL, 'Dammam',
     'Al Aqrabiyah, Dammam', '997', 26.406000, 50.131000),
    # --- Kuwait -----------------------------------------------------------
    ('Kuwait', 'Philippine Embassy Kuwait', EMBASSY, 'Kuwait City',
     'Block 1, Street 101, Jabriya', '+965 2531 2625',
     29.313500, 48.046500),
    ('Kuwait', 'POLO Kuwait', POLO, 'Kuwait City',
     'Jabriya, Kuwait', '+965 2531 2625', 29.313000, 48.046000),
    ('Kuwait', 'OWWA Kuwait', OWWA, 'Kuwait City',
     'Jabriya, Kuwait', '+965 2531 2625', 29.314000, 48.047000),
    ('Kuwait', 'Amiri Hospital', HOSPITAL, 'Kuwait City',
     'Kuwait City', '112', 29.383300, 47.983300),
    ('Kuwait', 'Kuwait Police Station', POLICE, 'Kuwait City',
     'Kuwait City', '112', 29.375000, 47.980000),
    # --- Qatar ------------------------------------------------------------
    ('Qatar', 'Philippine Embassy Doha', EMBASSY, 'Doha',
     'Building 26, Street 860, Zone 43, Al Hilal', '+974 4486 7845',
     25.241000, 51.507000),
    ('Qatar', 'POLO Doha', POLO, 'Doha',
     'Al Hilal, Doha', '+974 4486 7845', 25.240500, 51.506500),
    ('Qatar', 'OWWA Doha', OWWA, 'Doha',
     'Al Hilal, Doha', '+974 4486 7845', 25.241500, 51.507500),
    ('Qatar', 'Hamad General Hospital', HOSPITAL, 'Doha',
     'Al Rayyan Road, Doha', '999', 25.295000, 51.504000),
    ('Qatar', 'Doha Police Station', POLICE, 'Doha',
     'Al Sadd, Doha', '999', 25.280000, 51.510000),
    # --- United Arab Emirates --------------------------------------------
    ('United Arab Emirates', 'Philippine Embassy Abu Dhabi', EMBASSY, 'Abu Dhabi',
     'Villa 5, Street 4, Al Mushrif, Abu Dhabi', '+971 2 449 6888',
     24.462000, 54.376000),
    ('United Arab Emirates', 'POLO Abu Dhabi', POLO, 'Abu Dhabi',
     'Al Mushrif, Abu Dhabi', '+971 2 449 6888', 24.461500, 54.375500),
    ('United Arab Emirates', 'Philippine Consulate General Dubai', EMBASSY, 'Dubai',
     'Al Khaleej Centre, Bur Dubai', '+971 4 351 0325',
     25.259000, 55.297000),
    ('United Arab Emirates', 'POLO Dubai', POLO, 'Dubai',
     'Bur Dubai, Dubai', '+971 4 351 0325', 25.258500, 55.296500),
    ('United Arab Emirates', 'Rashid Hospital', HOSPITAL, 'Dubai',
     'Oud Metha Road, Dubai', '998', 25.234000, 55.315000),
    ('United Arab Emirates', 'Dubai Police Headquarters', POLICE, 'Dubai',
     'Al Twar, Dubai', '999', 25.268000, 55.340000),
    ('United Arab Emirates', 'Abu Dhabi Police', POLICE, 'Abu Dhabi',
     'Al Mushrif, Abu Dhabi', '999', 24.478000, 54.368000),
    # --- Switzerland ------------------------------------------------------
    ('Switzerland', 'Philippine Embassy Bern', EMBASSY, 'Bern',
     'Kramgasse 22, 3011 Bern', '+41 31 350 46 00', 46.948000, 7.452000),
    ('Switzerland', 'Bern Police Station', POLICE, 'Bern',
     'Waisenhausplatz, Bern', '117', 46.949000, 7.447000),
    ('Switzerland', 'Inselspital Bern', HOSPITAL, 'Bern',
     'Freiburgstrasse, Bern', '144', 46.947000, 7.464000),
    ('Switzerland', 'Philippine Consulate General Geneva', EMBASSY, 'Geneva',
     'Rue de Chantepoulet 1, Geneva', '+41 22 716 32 00',
     46.207000, 6.144000),
    ('Switzerland', 'Geneva Police Station', POLICE, 'Geneva',
     'Boulevard Carl-Vogt, Geneva', '117', 46.200000, 6.140000),
    ('Switzerland', 'HUG Geneva University Hospital', HOSPITAL, 'Geneva',
     'Rue Gabrielle-Perret-Gentil, Geneva', '144', 46.193000, 6.150000),
]


class Command(BaseCommand):
    help = (
        'Seed safe locations for the Philippines and the countries where '
        'OFWs are deployed (police, hospitals, embassies, OWWA/POLO).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--country',
            default=None,
            help='Only seed one country (default: Philippines + all OFW countries).',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete the seeded rows for the selected countries first.',
        )

    def _rows(self, country_filter):
        """Yield (country, name, type, city, address, phone, lat, lng)."""
        wanted = (country_filter or '').strip().lower()

        def matches(country):
            return not wanted or country.lower() == wanted

        if matches('Philippines'):
            for row in PHILIPPINES_SAFE_LOCATIONS:
                yield ('Philippines',) + row

        for row in OVERSEAS_SAFE_LOCATIONS:
            if matches(row[0]):
                yield row

    @transaction.atomic
    def handle(self, *args, **options):
        rows = list(self._rows(options['country']))

        if options['clear']:
            pairs = {(row[0], row[1]) for row in rows}
            deleted = 0
            for country, name in pairs:
                count, _ = SafeLocation.objects.filter(
                    country=country, name=name
                ).delete()
                deleted += count
            self.stdout.write(f'Removed {deleted} existing seeded rows.')

        created = updated = 0
        for country, name, location_type, city, address, phone, lat, lng in rows:
            _, was_created = SafeLocation.objects.update_or_create(
                name=name,
                city=city,
                country=country,
                defaults={
                    'location_type': location_type,
                    'address': address,
                    'phone': phone,
                    'latitude': lat,
                    'longitude': lng,
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

        seeded_countries = sorted({row[0] for row in rows})
        total = SafeLocation.objects.filter(
            country__in=seeded_countries, is_active=True
        ).count()
        self.stdout.write(self.style.SUCCESS(
            f'Seeded safe locations: {created} created, {updated} updated. '
            f'{total} active location(s) across {len(seeded_countries)} country/countries.'
        ))

