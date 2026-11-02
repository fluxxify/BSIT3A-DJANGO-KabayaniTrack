"""Refresh login inactivity and send due in-app management notifications."""

from django.core.management.base import BaseCommand

from apps.ofw.activity import refresh_activities_for_profiles
from apps.ofw.models import OFWProfile


class Command(BaseCommand):
    help = 'Check OFW login inactivity and send 3-day and 6-day notifications.'

    def handle(self, *args, **options):
        activities = refresh_activities_for_profiles(
            OFWProfile.objects.all().select_related('user', 'agency_org')
        )
        inactive = sum(
            not activity.is_account_active for activity in activities
        )
        self.stdout.write(self.style.SUCCESS(
            f'Checked {len(activities)} linked OFW accounts; '
            f'{inactive} currently inactive.'
        ))
