"""Seed the database with example KabayaniTrack data for every feature.

Usage:
    python manage.py seed_ofw
    python manage.py seed_ofw --user admin
    python manage.py seed_ofw --clear
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.ofw.models import (
    CheckIn,
    Concern,
    EmergencyContact,
    MonitoringReport,
    OFWProfile,
    RiskLevel,
    WelfareAssessment,
    WelfareStatus,
)


def _date(days_ago):
    return timezone.localdate() - timedelta(days=days_ago)


def _dt(days_ago, hour=9):
    now = timezone.now()
    return (now - timedelta(days=days_ago)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )


class Command(BaseCommand):
    help = 'Populate the database with example OFW monitoring and support records.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            help='Username that will own the seeded records (defaults to the first superuser or user).',
        )
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Delete existing OFW records for the target user before seeding.',
        )

    def handle(self, *args, **options):
        user = self._resolve_user(options.get('user'))

        if options['clear']:
            self._clear(user)
            self.stdout.write(self.style.WARNING('Cleared existing OFW records.'))

        counts = self._seed(user)
        summary = ', '.join(f'{name}={count}' for name, count in counts.items())
        self.stdout.write(self.style.SUCCESS(f'Seeded example data ({summary}) for user "{user}".'))

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

    def _clear(self, user):
        for model in (EmergencyContact, Concern, CheckIn, WelfareAssessment, MonitoringReport, OFWProfile):
            model.objects.filter(user=user).delete()

    @transaction.atomic
    def _seed(self, user):
        counts = {
            'profiles': 0,
            'assessments': 0,
            'checkins': 0,
            'concerns': 0,
            'contacts': 0,
            'reports': 0,
        }

        profiles = {}
        for data in self._profile_data():
            profile, created = OFWProfile.objects.get_or_create(
                first_name=data['first_name'],
                last_name=data['last_name'],
                country=data['country'],
                defaults={**data, 'user': user},
            )
            profiles[data['last_name']] = profile
            counts['profiles'] += int(created)

        for ofw_key, status, risk, days_ago, assessor, notes in self._assessment_data():
            _, created = WelfareAssessment.objects.get_or_create(
                ofw=profiles[ofw_key],
                assessment_date=_date(days_ago),
                defaults={
                    'user': user,
                    'status': status,
                    'risk_level': risk,
                    'assessor': assessor,
                    'notes': notes,
                },
            )
            counts['assessments'] += int(created)

        for ofw_key, days_ago, method, condition, notes in self._checkin_data():
            _, created = CheckIn.objects.get_or_create(
                ofw=profiles[ofw_key],
                checkin_date=_dt(days_ago),
                defaults={
                    'user': user,
                    'method': method,
                    'condition': condition,
                    'notes': notes,
                },
            )
            counts['checkins'] += int(created)

        concerns = {}
        for ofw_key, title, category, severity, status, days_ago, description, actions, resolved in self._concern_data():
            concern, created = Concern.objects.get_or_create(
                ofw=profiles[ofw_key],
                title=title,
                defaults={
                    'user': user,
                    'category': category,
                    'severity': severity,
                    'status': status,
                    'reported_date': _date(days_ago),
                    'description': description,
                    'actions_taken': actions,
                    'resolved_date': _date(resolved) if resolved is not None else None,
                },
            )
            concerns[title] = concern
            counts['concerns'] += int(created)

        for data in self._contact_data():
            _, created = EmergencyContact.objects.get_or_create(
                name=data['name'],
                defaults={**data, 'user': user},
            )
            counts['contacts'] += int(created)

        for data in self._report_data():
            defaults = {**data, 'user': user}
            defaults['period_start'] = _date(defaults.pop('start_days'))
            defaults['period_end'] = _date(defaults.pop('end_days'))
            _, created = MonitoringReport.objects.get_or_create(
                title=data['title'],
                defaults=defaults,
            )
            counts['reports'] += int(created)

        return counts

    def _profile_data(self):
        return [
            {
                'first_name': 'Juan', 'last_name': 'Dela Cruz',
                'passport_number': 'P1234567A', 'birth_date': _date(13800),
                'age': 38,
                'sex': 'M', 'contact_number': '+966 50 123 4567',
                'email': 'juan.delacruz@example.com',
                'permanent_address': '123 Rizal St., Cebu City, Cebu',
                'country': 'Saudi Arabia', 'city_abroad': 'Riyadh',
                'employer_name': 'Al-Rashid Construction Co.',
                'occupation': 'Construction Worker',
                'agency': 'Star Asia Manpower Agency',
                'deployment_date': _date(500), 'contract_end_date': _date(-365),
                'welfare_status': WelfareStatus.ACTIVE,
                'remarks': 'Regular remittance; no issues reported.',
            },
            {
                'first_name': 'Maria', 'last_name': 'Santos',
                'passport_number': 'P2233445B', 'birth_date': _date(13100),
                'age': 36,
                'sex': 'F', 'contact_number': '+852 9123 4567',
                'email': 'maria.santos@example.com',
                'permanent_address': '45 Mabini Ave., Iloilo City, Iloilo',
                'country': 'Hong Kong', 'city_abroad': 'Central',
                'employer_name': 'Chan Family Household',
                'occupation': 'Domestic Helper',
                'agency': 'Bright Future Recruitment',
                'deployment_date': _date(800), 'contract_end_date': _date(120),
                'welfare_status': WelfareStatus.ACTIVE,
                'remarks': 'On home leave until next month.',
            },
            {
                'first_name': 'Pedro', 'last_name': 'Reyes',
                'passport_number': 'P3344556C', 'birth_date': _date(14500),
                'age': 40,
                'sex': 'M', 'contact_number': '+974 3345 6789',
                'email': 'pedro.reyes@example.com',
                'permanent_address': '78 Bonifacio St., Dagupan, Pangasinan',
                'country': 'Qatar', 'city_abroad': 'Doha',
                'employer_name': 'Gulf Logistics W.L.L.',
                'occupation': 'Heavy Equipment Driver',
                'agency': 'Overseas Careers Inc.',
                'deployment_date': _date(300), 'contract_end_date': _date(-200),
                'welfare_status': WelfareStatus.NEEDS_SUPPORT,
                'remarks': 'Reported delayed wages for two months.',
            },
            {
                'first_name': 'Ana', 'last_name': 'Villanueva',
                'passport_number': 'P4455667D', 'birth_date': _date(12500),
                'age': 34,
                'sex': 'F', 'contact_number': '+971 55 987 6543',
                'email': 'ana.villanueva@example.com',
                'permanent_address': '210 Katipunan Rd., Quezon City',
                'country': 'United Arab Emirates', 'city_abroad': 'Dubai',
                'employer_name': 'Emirates Care Hospital',
                'occupation': 'Staff Nurse',
                'agency': 'Gulf Med Staffing',
                'deployment_date': _date(420), 'contract_end_date': _date(-120),
                'welfare_status': WelfareStatus.DISTRESSED,
                'remarks': 'Facing contract substitution and unpaid overtime.',
            },
            {
                'first_name': 'Jose', 'last_name': 'Ramos',
                'passport_number': 'P5566778E', 'birth_date': _date(16000),
                'age': 44,
                'sex': 'M', 'contact_number': '+965 5566 7788',
                'email': 'jose.ramos@example.com',
                'permanent_address': '9 Poblacion, Batangas City, Batangas',
                'country': 'Kuwait', 'city_abroad': 'Kuwait City',
                'employer_name': 'Blue Wave Shipping',
                'occupation': 'Seafarer (Able Seaman)',
                'agency': 'Maritime Crewing Corp.',
                'deployment_date': _date(900), 'contract_end_date': _date(60),
                'welfare_status': WelfareStatus.REPATRIATED,
                'remarks': 'Successfully repatriated; reintegration ongoing.',
            },
        ]

    def _assessment_data(self):
        return [
            ('Dela Cruz', WelfareStatus.ACTIVE, RiskLevel.LOW, 20, 'Case Officer R. Lim',
             'Stable employment; remits regularly.'),
            ('Santos', WelfareStatus.ACTIVE, RiskLevel.LOW, 35, 'Case Officer R. Lim',
             'On approved leave; in good spirits.'),
            ('Reyes', WelfareStatus.NEEDS_SUPPORT, RiskLevel.HIGH, 12, 'Case Officer M. Tan',
             'Salaries unpaid for 2 months; for legal referral.'),
            ('Villanueva', WelfareStatus.DISTRESSED, RiskLevel.CRITICAL, 5, 'Case Officer M. Tan',
             'Contract substitution confirmed; immediate assistance needed.'),
            ('Ramos', WelfareStatus.REPATRIATED, RiskLevel.MEDIUM, 45, 'Case Officer J. Cruz',
             'Repatriated; enrolled in livelihood program.'),
        ]

    def _checkin_data(self):
        return [
            ('Dela Cruz', 3, 'call', 'safe',
             'Doing well at work; no concerns.'),
            ('Dela Cruz', 33, 'app', 'safe',
             'Confirmed receipt of remittance.'),
            ('Santos', 8, 'video', 'safe',
             'Currently vacationing with family.'),
            ('Reyes', 6, 'sms', 'needs_assistance',
             'Requesting help regarding unpaid wages.'),
            ('Villanueva', 2, 'call', 'distressed',
             'Distressed over working conditions; wants repatriation.'),
            ('Ramos', 15, 'in_person', 'safe',
             'Post-repatriation follow-up; attending training.'),
            ('Reyes', 2, 'call', 'unreachable',
             'No answer; will retry tomorrow.'),
        ]

    def _concern_data(self):
        return [
            ('Reyes', 'Delayed salary for two months', 'salary', 'high', 'in_progress', 10,
             'Employer has not released wages for September and October.',
             'Letter sent to employer; coordinating with POLO.', None),
            ('Villanueva', 'Contract substitution by employer', 'contract', 'critical', 'escalated', 4,
             'Signed contract replaced on arrival with lower salary and longer hours.',
             'Referred to POLO and legal assistance provider.', None),
            ('Santos', 'Delay in passport renewal', 'documents', 'low', 'resolved', 40,
             'Passport renewal process took longer than expected.',
             'Assisted with embassy appointment.', 15),
            ('Dela Cruz', 'Unsafe scaffolding at worksite', 'work_environment', 'medium', 'open', 7,
             'Reported missing guardrails on the construction site.',
             'Awaiting employer response.', None),
            ('Ramos', 'Reintegration livelihood support', 'other', 'medium', 'closed', 50,
             'Needs assistance starting a small business after repatriation.',
             'Enrolled in livelihood program.', 20),
        ]

    def _contact_data(self):
        return [
            {
                'name': 'Philippine Embassy — Riyadh',
                'contact_type': 'embassy',
                'country': 'Saudi Arabia', 'city': 'Riyadh',
                'phone': '+966 11 488 8001',
                'email': 'riyadh.pe@dfa.gov.ph',
                'address': 'Diplomatic Quarter, Riyadh',
                'notes': 'Assistance to nationals: 24/7.',
            },
            {
                'name': 'POLO Riyadh',
                'contact_type': 'polo',
                'country': 'Saudi Arabia', 'city': 'Riyadh',
                'phone': '+966 11 480 9000',
                'email': 'polo.riyadh@dmw.gov.ph',
                'address': 'Diplomatic Quarter, Riyadh',
                'notes': 'Labor concerns, wage claims, repatriation.',
            },
            {
                'name': 'OWWA Welfare Office — Riyadh',
                'contact_type': 'owwa',
                'country': 'Saudi Arabia', 'city': 'Riyadh',
                'phone': '+966 11 488 8866',
                'email': 'owwa.riyadh@owwa.gov.ph',
                'address': 'Diplomatic Quarter, Riyadh',
                'notes': 'Welfare and repatriation assistance.',
            },
            {
                'name': 'DMW Action Center Hotline',
                'contact_type': 'dmw',
                'country': 'Philippines', 'city': 'Mandaluyong',
                'phone': '1348',
                'email': 'actioncenter@dmw.gov.ph',
                'address': 'DMW Building, EDSA corner Ortigas Ave.',
                'notes': 'National hotline, available 24/7.',
            },
            {
                'name': 'Philippine Consulate — Hong Kong',
                'contact_type': 'embassy',
                'country': 'Hong Kong', 'city': 'Central',
                'phone': '+852 2823 8500',
                'email': 'hongkong.pcg@dfa.gov.ph',
                'address': '14/F United Centre, Admiralty',
                'notes': 'Consular and welfare assistance.',
            },
            {
                'name': 'Dubai Police Emergency',
                'contact_type': 'police',
                'country': 'United Arab Emirates', 'city': 'Dubai',
                'phone': '999',
                'email': '',
                'address': '',
                'notes': 'Nationwide emergency number.',
            },
            {
                'name': 'Rashid Hospital',
                'contact_type': 'hospital',
                'country': 'United Arab Emirates', 'city': 'Dubai',
                'phone': '+971 4 219 2000',
                'email': '',
                'address': 'Oud Metha Road, Dubai',
                'notes': 'Government hospital with emergency care.',
            },
            {
                'name': 'AJ & Sons Household (Employer)',
                'contact_type': 'employer',
                'country': 'Hong Kong', 'city': 'Mid-Levels',
                'phone': '+852 9123 0000',
                'email': '',
                'address': 'Mid-Levels, Hong Kong',
                'notes': 'Emergency contact for employer.',
            },
            {
                'name': 'Maria Santos (Spouse)',
                'contact_type': 'family',
                'country': 'Philippines', 'city': 'Iloilo City',
                'phone': '+63 917 000 0001',
                'email': '',
                'address': '45 Mabini Ave., Iloilo City',
                'notes': 'Next of kin.',
            },
        ]

    def _report_data(self):
        return [
            {
                'title': 'Monthly Monitoring Report – October 2026',
                'report_type': 'monthly', 'start_days': 31, 'end_days': 1,
                'country': 'Middle East',
                'summary': 'Overall welfare of monitored OFWs remained stable. Wage-related concerns are the most common. '
                           'Strengthen pre-departure orientation on contract verification.',
                'status': 'submitted',
            },
            {
                'title': 'Quarterly Welfare Report – Q3 2026',
                'report_type': 'quarterly', 'start_days': 120, 'end_days': 10,
                'country': 'All Regions',
                'summary': 'Q3 saw a 12% increase in monitored OFWs. Domestic workers report more health and abuse-related concerns. '
                           'Expand shelter and counseling partnerships.',
                'status': 'approved',
            },
            {
                'title': 'Incident Report – Contract Substitution (Villanueva)',
                'report_type': 'incident', 'start_days': 6, 'end_days': 2,
                'country': 'UAE',
                'summary': 'Signed contract replaced on arrival. Referred to POLO and legal assistance provider.',
                'status': 'submitted',
            },
        ]
