"""Create one clearly labeled OFW record for previewing inactivity warnings."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ofw.models import OFWActivity, OFWProfile
from apps.ofw.roles import mark_as_ofw
from apps.users.models import Agency


DEMO_USERNAME = 'demo_ofw_inactive_4d'


class Command(BaseCommand):
    help = 'Create a local/live demo OFW with a successful login four days ago.'

    @transaction.atomic
    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(username=DEMO_USERNAME).exists():
            self.stdout.write(self.style.WARNING(
                f'{DEMO_USERNAME} already exists; no records were changed.'
            ))
            return

        try:
            agency = Agency.objects.get(slug='owwa', is_active=True)
        except Agency.DoesNotExist as exc:
            raise CommandError(
                'Active OWWA agency not found. Create or activate it first.'
            ) from exc

        now = timezone.now()
        last_login = now - timedelta(days=4)
        user = User(
            username=DEMO_USERNAME,
            email='demo.ofw.inactive@example.test',
            first_name='Demo',
            last_name='Inactive OFW',
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        user.set_unusable_password()
        user.save()
        user.date_joined = last_login - timedelta(days=30)
        user.last_login = last_login
        user.save(update_fields=['date_joined', 'last_login'])
        mark_as_ofw(user)

        profile = OFWProfile.objects.create(
            user=user,
            first_name='Demo',
            last_name='Inactive OFW',
            country='Qatar',
            city_abroad='Doha',
            agency_org=agency,
            remarks=(
                'DEMO RECORD: inactivity dashboard preview. '
                'Remove after the demonstration.'
            ),
        )
        OFWActivity.objects.update_or_create(
            user=user,
            defaults={
                'last_login_at': last_login,
                'last_activity_at': last_login,
                'days_inactive': 4,
                'is_account_active': False,
                'warning_sent_at': None,
                'followup_sent_at': None,
                'escalated_to_police_at': None,
            },
        )

        self.stdout.write(self.style.SUCCESS(
            f'Created {DEMO_USERNAME} (profile #{profile.pk}) under OWWA. '
            f'Last successful login: {last_login:%Y-%m-%d %H:%M %Z}. '
            'Visible to administrators and OWWA agency staff only; '
            'password login is disabled.'
        ))
