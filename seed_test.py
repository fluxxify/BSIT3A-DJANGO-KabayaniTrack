from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import date, timedelta
from apps.ofw.models import *

User = get_user_model()

# Create users
users = []
for i in range(1, 6):
    u, created = User.objects.get_or_create(username=f'ofw_test{i}', defaults={'email': f'ofw{i}@test.com'})
    u.set_password('test1234')
    u.save()
    users.append(u)
    print(f'User {i}: {created}')

# Create OFW Profiles
ofws_data = [
    {'first_name': 'Juan', 'last_name': 'Dela Cruz', 'passport_number': 'P1234567A', 'birth_date': date(1990, 5, 12), 'age': 35, 'sex': 'M', 'contact_number': '+971501234567', 'email': 'juan.dc@example.com', 'permanent_address': '123 Rizal St, Manila', 'country': 'United Arab Emirates', 'city_abroad': 'Dubai', 'employer_name': 'Al Mansoori Contracting', 'occupation': 'Construction Worker', 'agency': 'Golden Horizon Agency', 'deployment_date': date(2023, 3, 15), 'contract_end_date': date(2026, 3, 15), 'welfare_status': WelfareStatus.ACTIVE, 'remarks': 'Good standing.'},
    {'first_name': 'Maria', 'last_name': 'Santos', 'passport_number': 'P2345678B', 'birth_date': date(1992, 8, 25), 'age': 33, 'sex': 'F', 'contact_number': '+96599123456', 'email': 'maria.santos@example.com', 'permanent_address': '456 Mabini St, Cebu City', 'country': 'Kuwait', 'city_abroad': 'Kuwait City', 'employer_name': 'Al Shaya Group', 'occupation': 'Household Service Worker', 'agency': 'Bright Star Agency', 'deployment_date': date(2022, 7, 10), 'contract_end_date': date(2025, 7, 10), 'welfare_status': WelfareStatus.NEEDS_SUPPORT, 'remarks': 'Needs assistance with contract terms.'},
    {'first_name': 'Pedro', 'last_name': 'Reyes', 'passport_number': 'P3456789C', 'birth_date': date(1988, 11, 3), 'age': 37, 'sex': 'M', 'contact_number': '+966501234567', 'email': 'pedro.reyes@example.com', 'permanent_address': '789 Bonifacio St, Davao City', 'country': 'Saudi Arabia', 'city_abroad': 'Riyadh', 'employer_name': 'Saudi Aramco Contractors', 'occupation': 'Welder', 'agency': 'Prime Link Agency', 'deployment_date': date(2021, 1, 20), 'contract_end_date': date(2026, 1, 20), 'welfare_status': WelfareStatus.DISTRESSED, 'remarks': 'High priority case.'},
    {'first_name': 'Ana', 'last_name': 'Garcia', 'passport_number': 'P4567890D', 'birth_date': date(1995, 2, 14), 'age': 30, 'sex': 'F', 'contact_number': '+85291234567', 'email': 'ana.garcia@example.com', 'permanent_address': '321 Luna St, Quezon City', 'country': 'Hong Kong', 'city_abroad': 'Central', 'employer_name': 'Chan Family', 'occupation': 'Domestic Helper', 'agency': 'Reliable Manpower Agency', 'deployment_date': date(2024, 6, 1), 'contract_end_date': date(2026, 6, 1), 'welfare_status': WelfareStatus.ACTIVE, 'remarks': 'Regular monitoring.'},
    {'first_name': 'Roberto', 'last_name': 'Lopez', 'passport_number': 'P5678901E', 'birth_date': date(1993, 9, 7), 'age': 32, 'sex': 'M', 'contact_number': '+6581234567', 'email': 'roberto.lopez@example.com', 'permanent_address': '654 Del Pilar St, Bacolod City', 'country': 'Singapore', 'city_abroad': 'Singapore', 'employer_name': 'Marina Bay Hospitality', 'occupation': 'Chef', 'agency': 'Global Talent Agency', 'deployment_date': date(2023, 9, 5), 'contract_end_date': date(2026, 9, 5), 'welfare_status': WelfareStatus.REPATRIATED, 'remarks': 'Successfully repatriated.'},
]

ofws = []
for i, data in enumerate(ofws_data):
    ofw, created = OFWProfile.objects.get_or_create(passport_number=data['passport_number'], defaults={**data, 'user': users[i]})
    ofws.append(ofw)
    print(f'OFW {i+1}: {ofw.full_name} ({created})')

# Welfare Assessments
for i, ofw in enumerate(ofws):
    status = ofw.welfare_status
    if status == WelfareStatus.ACTIVE:
        risk = RiskLevel.LOW
    elif status == WelfareStatus.NEEDS_SUPPORT:
        risk = RiskLevel.MEDIUM
    else:
        risk = RiskLevel.CRITICAL
    wa, created = WelfareAssessment.objects.get_or_create(ofw=ofw, assessment_date=date.today()-timedelta(days=30*i), defaults={'user': users[i], 'status': status, 'risk_level': risk, 'assessor': 'Case Officer', 'notes': f'Assessment for {ofw.full_name}'})
    print(f'Assessment {i+1}: {created}')

# Check-ins
methods = [CheckIn.Method.CALL, CheckIn.Method.APP, CheckIn.Method.VIDEO, CheckIn.Method.SMS, CheckIn.Method.IN_PERSON]
conditions = [CheckIn.Condition.SAFE, CheckIn.Condition.NEEDS_ASSISTANCE, CheckIn.Condition.DISTRESSED, CheckIn.Condition.SAFE, CheckIn.Condition.SAFE]
for i, ofw in enumerate(ofws):
    ci, created = CheckIn.objects.get_or_create(ofw=ofw, checkin_date=timezone.now()-timedelta(days=10*i), defaults={'user': users[i], 'method': methods[i], 'condition': conditions[i], 'notes': f'Check-in for {ofw.full_name}'})
    print(f'Check-in {i+1}: {created}')

# Concerns
titles = ['Delayed Salary Payment', 'Excessive Work Hours', 'Verbal Abuse from Employer', 'Passport Withheld', 'Medical Emergency']
cats = [Concern.Category.SALARY, Concern.Category.WORK_ENVIRONMENT, Concern.Category.ABUSE, Concern.Category.DOCUMENTS, Concern.Category.HEALTH]
sevs = [Concern.Severity.HIGH, Concern.Severity.MEDIUM, Concern.Severity.CRITICAL, Concern.Severity.HIGH, Concern.Severity.CRITICAL]
stats = [Concern.Status.IN_PROGRESS, Concern.Status.OPEN, Concern.Status.ESCALATED, Concern.Status.IN_PROGRESS, Concern.Status.RESOLVED]
for i, ofw in enumerate(ofws):
    c, created = Concern.objects.get_or_create(ofw=ofw, title=titles[i], defaults={'user': users[i], 'category': cats[i], 'severity': sevs[i], 'status': stats[i], 'reported_date': date.today()-timedelta(days=15-i), 'description': f'Detailed description for {ofw.full_name}'})
    print(f'Concern {i+1}: {created}')

# Emergency Contacts
contacts = [
    {'name': 'PH Embassy Dubai', 'contact_type': EmergencyContact.ContactType.EMBASSY, 'country': 'United Arab Emirates', 'city': 'Dubai', 'phone': '+97143531100', 'email': 'dubai.pe@dfa.gov.ph'},
    {'name': 'POLO Kuwait', 'contact_type': EmergencyContact.ContactType.POLO, 'country': 'Kuwait', 'city': 'Kuwait City', 'phone': '+96525312222', 'email': 'polo.kuwait@dmw.gov.ph'},
    {'name': 'OWWA Riyadh', 'contact_type': EmergencyContact.ContactType.OWWA, 'country': 'Saudi Arabia', 'city': 'Riyadh', 'phone': '+966114880000', 'email': 'owwa.riyadh@owwa.gov.ph'},
    {'name': 'DMW Hotline', 'contact_type': EmergencyContact.ContactType.DMW, 'phone': '1348', 'email': 'hotline@dmw.gov.ph'},
    {'name': 'Mother - Maria Lopez', 'contact_type': EmergencyContact.ContactType.FAMILY, 'phone': '+639171234567', 'relationship': 'Mother'},
]
for cd in contacts:
    ec, created = EmergencyContact.objects.get_or_create(name=cd['name'], defaults=cd)
    print(f'Contact: {ec.name} ({created})')

# Monitoring Reports
reports = [
    {'title': 'Q1 2026 OFW Welfare Report', 'report_type': MonitoringReport.ReportType.QUARTERLY, 'period_start': date(2026, 1, 1), 'period_end': date(2026, 3, 31), 'country': '', 'summary': 'Quarterly summary of OFW welfare cases.', 'status': MonitoringReport.Status.SUBMITTED},
    {'title': 'Dubai Deployment Monthly Report', 'report_type': MonitoringReport.ReportType.MONTHLY, 'period_start': date(2026, 9, 1), 'period_end': date(2026, 9, 30), 'country': 'United Arab Emirates', 'summary': 'Monthly monitoring for Dubai deployments.', 'status': MonitoringReport.Status.DRAFT},
    {'title': 'Kuwait Incident Report', 'report_type': MonitoringReport.ReportType.INCIDENT, 'period_start': date(2026, 8, 15), 'period_end': date(2026, 9, 1), 'country': 'Kuwait', 'summary': 'Investigation of abuse case.', 'status': MonitoringReport.Status.APPROVED},
]
for rd in reports:
    mr, created = MonitoringReport.objects.get_or_create(title=rd['title'], defaults=rd)
    print(f'Report: {mr.title} ({created})')

# Notifications
for i, user in enumerate(users):
    n, created = Notification.objects.get_or_create(recipient=user, title=f'Update for your case #{i+1}', defaults={'message': 'There is an update regarding your OFW monitoring case.', 'url': '/ofw/portal/', 'level': Notification.Level.INFO})
    print(f'Notif {i+1}: {created}')

print('DONE!')
