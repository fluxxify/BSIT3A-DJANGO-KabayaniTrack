"""Seed the database with emergency-related test data for all features.

Usage:
    python manage.py seed_emergency
    python manage.py seed_emergency --user admin
    python manage.py seed_emergency --clear

Creates:
  * Emergency Alerts (open / acknowledged / escalated / resolved)
  * Police Reports (draft / submitted / responded / closed)
  * Location Tracker pings (emergency and standard)
  * OFW Activity records (active, inactive, warning-due, escalated)
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ofw.models import (
    EmergencyAlert,
    LocationTracker,
    OFWActivity,
    OFWProfile,
    PoliceReport,
)


def _dt(days_ago, hour=9):
    now = timezone.now()
    return (now - timedelta(days=days_ago)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


class Command(BaseCommand):
    help = 'Populate emergency-related test data for OFW admin and portal features.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            help='Username that will own the seeded records (defaults to first superuser).',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing seeded emergency records before seeding again.',
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get('user'))

        if options['clear']:
            self._clear()
            self.stdout.write(self.style.WARNING('Cleared existing emergency records.'))

        counts = self._seed(user)
        summary = ', '.join(f'{name}={count}' for name, count in counts.items())
        self.stdout.write(
            self.style.SUCCESS(f'Seeded emergency data ({summary}) for user "{user}".')
        )

    def _resolve_user(self, username):
        User = get_user_model()
        if username:
            try:
                return User.objects.get(username=username)
            except User.DoesNotExist:
                raise CommandError(f'No user named "{username}".')
        user = User.objects.filter(is_superuser=True).order_by('id').first()
        if user is None:
            user = User.objects.order_by('id').first()
        if user is None:
            raise CommandError(
                'No users exist. Create one first with "python manage.py createsuperuser".'
            )
        return user

    def _clear(self):
        LocationTracker.objects.all().delete()
        EmergencyAlert.objects.all().delete()
        PoliceReport.objects.all().delete()
        OFWActivity.objects.all().delete()

    @transaction.atomic
    def _seed(self, user):
        profiles = list(OFWProfile.objects.all().order_by('id'))
        if not profiles:
            raise CommandError(
                'No OFW profiles exist. Run "python manage.py seed_ofw" first.'
            )

        counts = {
            'alerts': 0,
            'police_reports': 0,
            'location_pings': 0,
            'activities': 0,
        }

        # --- OFW Activity records (inactive detection) ---
        activity_data = [
            # (profile_index, days_inactive, is_account_active, warning_sent, escalated)
            (0, 0, True, False, False),      # active OFW
            (1, 0, True, False, False),      # active OFW
            (2, 5, False, False, False),     # inactive 5 days, no warning yet -> warning due
            (3, 6, False, True, False),      # inactive 6 days, warned, not escalated -> escalation due
            (4, 10, False, True, True),      # inactive 10 days, warned, escalated
        ]
        for idx, days_inactive, active, warned, escalated in activity_data:
            profile = profiles[idx % len(profiles)]
            activity, created = OFWActivity.objects.update_or_create(
                user=profile.user,
                defaults={
                    'last_login_at': _dt(days_inactive + 1) if active else None,
                    'last_activity_at': _dt(days_inactive + 1) if active else None,
                    'is_account_active': active,
                    'days_inactive': days_inactive,
                    'warning_sent_at': _dt(days_inactive - 1) if warned else None,
                    'escalated_to_police_at': _dt(days_inactive - 2) if escalated else None,
                },
            )
            counts['activities'] += int(created)

        # --- Location Tracker pings ---
        ping_data = [
            # (profile_index, lat, lng, is_emergency, days_ago)
            (3, 14.5995, 120.9842, True, 1),   # Villanueva emergency SOS ping
            (3, 14.6001, 120.9850, False, 2),  # Villanueva standard ping
            (2, 25.2048, 55.2708, True, 0),    # Reyes emergency ping
            (4, 25.2867, 55.3144, False, 3),   # Ramos standard ping
        ]
        for idx, lat, lng, is_emergency, days_ago in ping_data:
            profile = profiles[idx % len(profiles)]
            _, created = LocationTracker.objects.update_or_create(
                ofw=profile,
                recorded_at=_dt(days_ago),
                defaults={
                    'latitude': lat,
                    'longitude': lng,
                    'accuracy_meters': 15,
                    'is_emergency': is_emergency,
                },
            )
            counts['location_pings'] += int(created)

        # --- Emergency Alerts ---
        alert_data = [
            # (profile_index, title, message, level, status, acknowledged)
            (
                3,
                'Emergency SOS from Ana Villanueva',
                'Ana Villanueva sent an emergency location ping (lat: 14.5995, lng: 120.9842). '
                'Nearest safe place: Manila Police District Headquarters (0.4 km north) in Manila. '
                'Guide them to the nearest safe place.',
                EmergencyAlert.Level.CRITICAL,
                EmergencyAlert.Status.OPEN,
                False,
            ),
            (
                2,
                'Distressed check-in from Pedro Reyes',
                'Pedro Reyes reported a distressed condition via Phone Call. '
                'Distressed over working conditions; wants repatriation.',
                EmergencyAlert.Level.DANGER,
                EmergencyAlert.Status.OPEN,
                False,
            ),
            (
                0,
                'Distressed check-in from Juan Dela Cruz',
                'Juan Dela Cruz reported another distressed check-in via App. '
                'Unsafe scaffolding at worksite.',
                EmergencyAlert.Level.WARNING,
                EmergencyAlert.Status.ACKNOWLEDGED,
                True,
            ),
            (
                4,
                'Emergency SOS from Jose Ramos',
                'Jose Ramos sent an emergency location ping (lat: 25.2867, lng: 55.3144). '
                'Guide them to the nearest safe place.',
                EmergencyAlert.Level.CRITICAL,
                EmergencyAlert.Status.RESOLVED,
                True,
            ),
        ]
        for idx, title, message, level, status, acknowledged in alert_data:
            profile = profiles[idx % len(profiles)]
            alert, created = EmergencyAlert.objects.update_or_create(
                ofw=profile,
                title=title,
                defaults={
                    'message': message,
                    'level': level,
                    'status': status,
                    'acknowledged_by': user if acknowledged else None,
                    'acknowledged_at': timezone.now() if acknowledged else None,
                    'escalated_to_police': status == EmergencyAlert.Status.ESCALATED,
                },
            )
            counts['alerts'] += int(created)

        # --- Police Reports ---
        police_data = [
            # (profile_index, title, description, police_station, police_contact, status)
            (
                2,
                'Missing / Unresponsive OFW — Pedro Reyes',
                'OFW Pedro Reyes has been inactive for 5 days. Management called but received no response. '
                'Last known country: Qatar, city: Doha. Employer: Gulf Logistics W.L.L.',
                'Doha Central Police Station',
                '+974 4444 8888',
                PoliceReport.Status.SUBMITTED,
            ),
            (
                3,
                'Missing / Unresponsive OFW — Ana Villanueva',
                'OFW Ana Villanueva has been inactive for 6 days. Management called but received no response. '
                'Last known country: United Arab Emirates, city: Dubai. Employer: Emirates Care Hospital.',
                'Dubai Police',
                '999',
                PoliceReport.Status.DRAFT,
            ),
        ]
        for idx, title, description, station, contact, status in police_data:
            profile = profiles[idx % len(profiles)]
            alert = EmergencyAlert.objects.filter(
                ofw=profile, status=EmergencyAlert.Status.OPEN
            ).order_by('-created_at').first()
            report, created = PoliceReport.objects.update_or_create(
                ofw=profile,
                title=title,
                defaults={
                    'description': description,
                    'police_station': station,
                    'police_contact': contact,
                    'status': status,
                    'reported_by': user,
                },
            )
            if alert and status == PoliceReport.Status.SUBMITTED:
                alert.status = EmergencyAlert.Status.ESCALATED
                alert.escalated_to_police = True
                alert.police_report = report
                alert.save(
                    update_fields=['status', 'escalated_to_police', 'police_report', 'updated_at']
                )
            counts['police_reports'] += int(created)

        return counts
