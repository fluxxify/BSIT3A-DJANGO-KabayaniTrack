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
    MonitoringReport,
    OFWProfile,
    RiskLevel,
    SupportRecord,
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
        for model in (SupportRecord, Concern, CheckIn, WelfareAssessment, MonitoringReport, OFWProfile):
            model.objects.filter(user=user).delete()

    @transaction.atomic
    def _seed(self, user):
        counts = {
            'profiles': 0,
            'assessments': 0,
            'checkins': 0,
            'concerns': 0,
            'supports': 0,
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

        for ofw_key, days_ago, method, condition, location, person, notes in self._checkin_data():
            _, created = CheckIn.objects.get_or_create(
                ofw=profiles[ofw_key],
                checkin_date=_dt(days_ago),
                defaults={
                    'user': user,
                    'method': method,
                    'condition': condition,
                    'location': location,
                    'contacted_person': person,
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

        for ofw_key, concern_title, support_type, title, description, provider, amount, days_ago, status in self._support_data():
            _, created = SupportRecord.objects.get_or_create(
                ofw=profiles[ofw_key],
                title=title,
                defaults={
                    'user': user,
                    'concern': concerns.get(concern_title),
                    'support_type': support_type,
                    'description': description,
                    'provider': provider,
                    'amount': amount,
                    'date_provided': _date(days_ago),
                    'status': status,
                },
            )
            counts['supports'] += int(created)

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
                'sex': 'F', 'contact_number': '+852 9123 4567',
                'email': 'maria.santos@example.com',
                'permanent_address': '45 Mabini Ave., Iloilo City, Iloilo',
                'country': 'Hong Kong', 'city_abroad': 'Central',
                'employer_name': 'Chan Family Household',
                'occupation': 'Domestic Helper',
                'agency': 'Bright Future Recruitment',
                'deployment_date': _date(800), 'contract_end_date': _date(120),
                'welfare_status': WelfareStatus.ON_LEAVE,
                'remarks': 'On home leave until next month.',
            },
            {
                'first_name': 'Pedro', 'last_name': 'Reyes',
                'passport_number': 'P3344556C', 'birth_date': _date(14500),
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
            ('Santos', WelfareStatus.ON_LEAVE, RiskLevel.LOW, 35, 'Case Officer R. Lim',
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
            ('Dela Cruz', 3, 'call', 'safe', 'Riyadh, Saudi Arabia', 'Juan Dela Cruz',
             'Doing well at work; no concerns.'),
            ('Dela Cruz', 33, 'app', 'safe', 'Riyadh, Saudi Arabia', 'Juan Dela Cruz',
             'Confirmed receipt of remittance.'),
            ('Santos', 8, 'video', 'safe', 'Iloilo City, Philippines', 'Maria Santos',
             'Currently vacationing with family.'),
            ('Reyes', 6, 'sms', 'needs_assistance', 'Doha, Qatar', 'Pedro Reyes',
             'Requesting help regarding unpaid wages.'),
            ('Villanueva', 2, 'call', 'distressed', 'Dubai, UAE', 'Ana Villanueva',
             'Distressed over working conditions; wants repatriation.'),
            ('Ramos', 15, 'in_person', 'safe', 'Batangas City, Philippines', 'Jose Ramos',
             'Post-repatriation follow-up; attending training.'),
            ('Reyes', 2, 'call', 'unreachable', 'Doha, Qatar', '',
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

    def _support_data(self):
        return [
            ('Reyes', 'Delayed salary for two months', 'legal', 'Legal assistance for wage claim',
             'Assisted in filing a wage claim with POLO Qatar.',
             'POLO Qatar', None, 8, 'approved'),
            ('Villanueva', 'Contract substitution by employer', 'legal', 'Legal counsel for contract substitution',
             'Provided legal counsel and documentation support.',
             'DMW Legal Assistance', None, 3, 'released'),
            ('Villanueva', None, 'financial', 'Financial assistance (calamity/emergency)',
             'Emergency financial aid for repatriation costs.',
             'OWWA', 15000.00, 3, 'released'),
            ('Reyes', None, 'financial', 'Financial assistance for dependent family',
             'Interim financial support while case is pending.',
             'OWWA', 10000.00, 6, 'completed'),
            ('Santos', 'Delay in passport renewal', 'referral', 'Referral to embassy services',
             'Referral for expedited passport renewal.',
             'Philippine Embassy HK', None, 38, 'completed'),
            ('Ramos', 'Reintegration livelihood support', 'livelihood', 'Livelihood starter kit',
             'Provided sari-sari store starter kit and training.',
             'OWWA', 25000.00, 30, 'completed'),
            ('Ramos', None, 'counseling', 'Post-repatriation counseling',
             'Psychosocial counseling sessions.',
             'DMW Reintegration Unit', None, 25, 'completed'),
            ('Dela Cruz', None, 'training', 'Occupational safety training',
             'Enrolled in safety training program.',
             'TESDA', None, 12, 'pending'),
        ]

    def _report_data(self):
        return [
            {
                'title': 'Monthly Monitoring Report — October 2026',
                'report_type': 'monthly', 'start_days': 31, 'end_days': 1,
                'country': 'Middle East',
                'total_ofws': 12, 'total_concerns': 5, 'total_support_cases': 4,
                'summary': 'Overall welfare of monitored OFWs remained stable. 5 concerns were logged, '
                           'with 2 escalated for legal assistance.',
                'findings': 'Wage-related concerns are the most common, followed by contract violations.',
                'recommendations': 'Strengthen pre-departure orientation on contract verification.',
                'prepared_by': 'Case Officer R. Lim', 'status': 'submitted',
            },
            {
                'title': 'Quarterly Welfare Report — Q3 2026',
                'report_type': 'quarterly', 'start_days': 120, 'end_days': 10,
                'country': 'All Regions',
                'total_ofws': 34, 'total_concerns': 18, 'total_support_cases': 15,
                'summary': 'Q3 saw a 12% increase in monitored OFWs. Support was rendered in 15 cases.',
                'findings': 'Domestic workers report more health and abuse-related concerns.',
                'recommendations': 'Expand shelter and counseling partnerships in host countries.',
                'prepared_by': 'Case Officer M. Tan', 'status': 'approved',
            },
            {
                'title': 'Incident Report — Contract Substitution (Villanueva)',
                'report_type': 'incident', 'start_days': 5, 'end_days': 1,
                'country': 'United Arab Emirates',
                'total_ofws': 1, 'total_concerns': 1, 'total_support_cases': 2,
                'summary': 'OFW Ana Villanueva reported contract substitution upon arrival in Dubai. '
                           'Two support cases were opened and escalated.',
                'findings': 'Employer replaced the approved contract with a lower-paying one.',
                'recommendations': 'Coordinate with DMW for possible disciplinary action against the employer.',
                'prepared_by': 'Case Officer M. Tan', 'status': 'draft',
            },
        ]
