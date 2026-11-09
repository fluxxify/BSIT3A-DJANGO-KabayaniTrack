"""Preview or delete every OFW account and its monitoring data.

This is the safe way to start fresh without touching management accounts,
agencies, or the safe-location reference data.  Always preview first::

    python manage.py reset_ofw_accounts

Then delete when the counts look right::

    python manage.py reset_ofw_accounts --execute

Use ``--keep-users`` to remove OFW profiles and records but keep the login
accounts (for example, when only the monitoring data should be cleared).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from apps.ofw.models import (
    CheckIn,
    Concern,
    EmergencyAlert,
    LocationTracker,
    OFWActivity,
    OFWProfile,
    PoliceReport,
    WelfareAssessment,
)
from apps.ofw.roles import OFW_GROUP_NAME

User = get_user_model()


class Command(BaseCommand):
    help = 'Preview or delete every OFW account and related monitoring data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--execute',
            action='store_true',
            help=(
                'Delete the OFW accounts and data. Without this flag the '
                'command only shows what would be deleted.'
            ),
        )
        parser.add_argument(
            '--keep-users',
            action='store_true',
            help=(
                'Delete OFW profiles and records but keep the OFW login '
                'accounts.'
            ),
        )

    def handle(self, *args, **options):
        ofw_users = (
            User.objects
            .filter(
                Q(ofw_profiles__isnull=False)
                | Q(groups__name=OFW_GROUP_NAME)
            )
            .exclude(is_staff=True)
            .exclude(is_superuser=True)
            .distinct()
        )
        profile_ids = list(OFWProfile.objects.values_list('pk', flat=True))
        user_ids = list(ofw_users.values_list('pk', flat=True))

        if not profile_ids and not user_ids:
            self.stdout.write(self.style.SUCCESS(
                'No OFW accounts or profiles found. Nothing to delete.'
            ))
            return

        profiles = OFWProfile.objects.filter(pk__in=profile_ids)
        counts = [
            ('OFW login accounts', len(user_ids)),
            ('OFW profiles', len(profile_ids)),
            ('Check-ins', CheckIn.objects.filter(ofw__in=profiles).count()),
            ('Concerns', Concern.objects.filter(ofw__in=profiles).count()),
            (
                'Welfare assessments',
                WelfareAssessment.objects.filter(ofw__in=profiles).count(),
            ),
            (
                'Emergency alerts',
                EmergencyAlert.objects.filter(ofw__in=profiles).count(),
            ),
            (
                'Police reports',
                PoliceReport.objects.filter(ofw__in=profiles).count(),
            ),
            (
                'Location pings',
                LocationTracker.objects.filter(ofw__in=profiles).count(),
            ),
            (
                'Activity records',
                OFWActivity.objects.filter(user_id__in=user_ids).count(),
            ),
        ]

        self.stdout.write('The following OFW data was found:')
        for label, value in counts:
            self.stdout.write(f'  {label}: {value}')

        if not options['execute']:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING(
                'Preview only. Add --execute to delete this data.'
            ))
            return

        with transaction.atomic():
            OFWProfile.objects.filter(pk__in=profile_ids).delete()
            if not options['keep_users']:
                User.objects.filter(pk__in=user_ids).delete()

        if options['keep_users']:
            message = (
                f'Deleted {len(profile_ids)} OFW profile(s) and related '
                'records. Login accounts were kept.'
            )
        else:
            message = (
                f'Deleted {len(user_ids)} OFW account(s) and '
                f'{len(profile_ids)} profile(s) with their related records.'
            )
        self.stdout.write(self.style.SUCCESS(message))
