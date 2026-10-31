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


class Command(BaseCommand):
    help = 'Seed Philippine safe locations (police, hospitals, embassies, OWWA/DMW).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--country',
            default='Philippines',
            help='Country label to store on the seeded rows (default: Philippines).',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete the seeded Philippine rows before seeding again.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        country = options['country']

        if options['clear']:
            names = [row[0] for row in PHILIPPINES_SAFE_LOCATIONS]
            deleted, _ = SafeLocation.objects.filter(
                country=country, name__in=names
            ).delete()
            self.stdout.write(f'Removed {deleted} existing seeded rows.')

        created = updated = 0
        for name, location_type, city, address, phone, lat, lng in PHILIPPINES_SAFE_LOCATIONS:
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

        total = SafeLocation.objects.filter(country=country, is_active=True).count()
        self.stdout.write(self.style.SUCCESS(
            f'Seeded safe locations: {created} created, {updated} updated. '
            f'{total} active location(s) for {country}.'
        ))
