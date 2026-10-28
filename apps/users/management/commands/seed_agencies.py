"""Seed the ten partner agencies and their management accounts.

Usage::

    python manage.py seed_agencies

Running the command is idempotent: agencies are updated in place and the
matching staff accounts are created when missing.  Pass ``--preserve-passwords``
to keep any passwords that were already changed in production.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.users.models import Agency, AgencyStaff

User = get_user_model()

AGENCIES = [
    {
        'slug': 'owwa',
        'name': 'Overseas Workers Welfare Administration',
        'short_name': 'OWWA',
        'website': 'https://owwa.gov.ph',
        'category': 'Local & state government offices',
        'address': 'F B Harrison St, 1302 Pasay, Metro Manila',
        'phone': '+63 2 8891 7601',
    },
    {
        'slug': 'fvj',
        'name': 'FVJ Overseas Placement, Inc',
        'short_name': 'FVJ',
        'website': 'http://fvj.com.ph',
        'category': 'Employment agencies',
        'address': '128 Porvenir Street, 1305 Pasay, Metro Manila',
        'phone': '+63 6325265897',
    },
    {
        'slug': 'uno',
        'name': 'UNO Overseas Placement, Inc.',
        'short_name': 'UNO',
        'website': 'http://www.unoph.com',
        'category': 'Employment agencies',
        'address': '867 M F Jhocson Street, 1008 Manila, Metro Manila',
        'phone': '+63 2 8743 1134',
    },
    {
        'slug': 'profile',
        'name': 'Profile Overseas Manpower Services, Inc.',
        'short_name': 'Profile',
        'website': 'http://www.profilemanpower.com',
        'category': 'Employment agencies',
        'address': 'V A Rufino Street, 1200 Makati, Metro Manila',
        'phone': '+63 2 8813 3234',
    },
    {
        'slug': 'workasia',
        'name': 'Work Asia International Recruitment Agency Inc',
        'short_name': 'WorkAsia',
        'website': 'http://www.workasia.com.ph',
        'category': 'Professional services',
        'address': '3713 Bautista St, 1235 Makati, Metro Manila',
        'phone': '+63 2 8938 1024',
    },
    {
        'slug': 'mip',
        'name': 'MIP International Manpower Services',
        'short_name': 'MIP',
        'website': 'http://www.mipinternational.com',
        'category': 'Employment agencies',
        'address': '28 G S I S Avenue, 1116 Quezon City, Metro Manila',
        'phone': '+63 2 8927 6546',
    },
    {
        'slug': 'ywa',
        'name': 'YWA Human Resource Corporation',
        'short_name': 'YWA',
        'website': 'http://www.ywacorp.com',
        'category': 'Employment agencies',
        'address': '1268 General Luna Street, Manila, Metro Manila',
        'phone': '+63 2 8524 7777',
    },
    {
        'slug': 'manila',
        'name': 'Manila Recruitment',
        'short_name': 'Manila',
        'website': 'https://www.manilarecruitment.com',
        'category': 'Professional services',
        'address': 'Orion Street, 1209 Makati, Metro Manila',
        'phone': '+63 2 8867 7676',
    },
    {
        'slug': 'mercan',
        'name': 'Mercan Canada Employment Phils Incorporated',
        'short_name': 'Mercan',
        'website': 'http://www.mercanph.com',
        'category': 'Employment agencies',
        'address': 'Galleria Corporate Center Driveway, Quezon City, Metro Manila',
        'phone': '+63 2 8240 8020',
    },
    {
        'slug': 'mitac',
        'name': 'Mitac Overseas Manpower Corporation',
        'short_name': 'Mitac',
        'website': 'http://mitacoverseas.com',
        'category': 'Employment agencies',
        'address': 'Aguinaldo St, 1900 Antipolo, Calabarzon',
        'phone': '+63 2 8556 7548',
    },
]


class Command(BaseCommand):
    help = 'Create/update the ten partner agencies and their login accounts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--preserve-passwords',
            action='store_true',
            help='Do not reset passwords for accounts that already exist.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        preserve = options['preserve_passwords']

        for index, data in enumerate(AGENCIES, start=1):
            username = data['slug']
            password = f'Agency{index:02d}'

            agency, _ = Agency.objects.update_or_create(
                slug=data['slug'],
                defaults={
                    'name': data['name'],
                    'website': data['website'],
                    'category': data['category'],
                    'address': data['address'],
                    'phone': data['phone'],
                    'description': (
                        'KabayaniTrack partner agency for OFW monitoring and '
                        'welfare support.'
                    ),
                    'is_active': True,
                },
            )

            user, created = User.objects.get_or_create(
                username=username,
                defaults={'email': f'{username}@agency.local', 'is_staff': True},
            )
            changed = False
            if not user.is_staff:
                user.is_staff = True
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if created or (not preserve and not user.check_password(password)):
                user.set_password(password)
                changed = True
            if changed:
                user.save()

            AgencyStaff.objects.update_or_create(
                user=user,
                defaults={'agency': agency},
            )

            state = 'created' if created else 'updated'
            self.stdout.write(
                self.style.SUCCESS(
                    f'[{index:02d}] {state}: {username} / {password} -> {agency.name}'
                )
            )

        self.stdout.write(self.style.SUCCESS('Agency seeding complete.'))
