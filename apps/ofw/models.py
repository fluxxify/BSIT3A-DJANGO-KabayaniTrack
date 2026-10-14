"""Domain models for KabayaniTrack, an OFW monitoring and support information system.

The system tracks five key areas:
  * OFW profiles and their welfare status
  * periodic welfare assessments
  * periodic check-ins
  * reported concerns
  * support documentation (assistance rendered)
  * monitoring reports
"""

from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class WelfareStatus(models.TextChoices):
    ACTIVE = 'active', 'Active / Deployed'
    ON_LEAVE = 'on_leave', 'On Leave'
    NEEDS_SUPPORT = 'needs_support', 'Needs Support'
    DISTRESSED = 'distressed', 'Distressed'
    REPATRIATED = 'repatriated', 'Repatriated'
    MISSING = 'missing', 'Missing'
    DECEASED = 'deceased', 'Deceased'


class RiskLevel(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class OFWProfile(models.Model):
    """Personal, employment, and welfare profile of an Overseas Filipino Worker."""

    class Sex(models.TextChoices):
        MALE = 'M', 'Male'
        FEMALE = 'F', 'Female'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='ofw_profiles',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120)
    passport_number = models.CharField(max_length=40, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices, blank=True)
    contact_number = models.CharField(max_length=40, blank=True)
    email = models.EmailField(max_length=255, blank=True)
    permanent_address = models.CharField(max_length=255, blank=True)
    country = models.CharField(max_length=120, help_text='Country of deployment')
    city_abroad = models.CharField(max_length=120, blank=True)
    employer_name = models.CharField(max_length=200, blank=True)
    occupation = models.CharField(max_length=120, blank=True)
    agency = models.CharField(max_length=200, blank=True)
    deployment_date = models.DateField(null=True, blank=True)
    contract_end_date = models.DateField(null=True, blank=True)
    welfare_status = models.CharField(
        max_length=20,
        choices=WelfareStatus.choices,
        default=WelfareStatus.ACTIVE,
    )
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblofwprofile'
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f'{self.last_name}, {self.first_name}'

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()


class WelfareAssessment(models.Model):
    """A point-in-time welfare assessment recorded for an OFW."""

    OFW = 'ofw'

    ofw = models.ForeignKey(
        OFWProfile,
        related_name='assessments',
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='welfare_assessments',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, choices=WelfareStatus.choices)
    risk_level = models.CharField(
        max_length=10,
        choices=RiskLevel.choices,
        default=RiskLevel.LOW,
    )
    assessment_date = models.DateField()
    assessor = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblwelfareassessment'
        ordering = ['-assessment_date', '-id']

    def __str__(self):
        return f'{self.ofw} — {self.get_status_display()}'


class CheckIn(models.Model):
    """A periodic check-in contact made with an OFW."""

    class Method(models.TextChoices):
        APP = 'app', 'Mobile App'
        SMS = 'sms', 'SMS'
        EMAIL = 'email', 'Email'
        CALL = 'call', 'Phone Call'
        VIDEO = 'video', 'Video Call'
        IN_PERSON = 'in_person', 'In Person'

    class Condition(models.TextChoices):
        SAFE = 'safe', 'Safe'
        NEEDS_ASSISTANCE = 'needs_assistance', 'Needs Assistance'
        DISTRESSED = 'distressed', 'Distressed'
        UNREACHABLE = 'unreachable', 'Unreachable'

    ofw = models.ForeignKey(
        OFWProfile,
        related_name='checkins',
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='checkins',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    checkin_date = models.DateTimeField()
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CALL)
    condition = models.CharField(
        max_length=20,
        choices=Condition.choices,
        default=Condition.SAFE,
    )
    location = models.CharField(max_length=200, blank=True)
    contacted_person = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblcheckin'
        ordering = ['-checkin_date', '-id']

    def __str__(self):
        return f'Check-in for {self.ofw} on {self.checkin_date:%b %d, %Y}'


class Concern(models.Model):
    """A welfare concern or case reported for an OFW."""

    class Category(models.TextChoices):
        SALARY = 'salary', 'Salary / Compensation'
        CONTRACT = 'contract', 'Contract Violation'
        HEALTH = 'health', 'Health / Medical'
        ABUSE = 'abuse', 'Abuse / Maltreatment'
        DOCUMENTS = 'documents', 'Passport / Documents'
        ILLEGAL_RECRUITMENT = 'illegal_recruitment', 'Illegal Recruitment'
        WORK_ENVIRONMENT = 'work_environment', 'Work Environment'
        OTHER = 'other', 'Other'

    class Severity(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        CRITICAL = 'critical', 'Critical'

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In Progress'
        ESCALATED = 'escalated', 'Escalated'
        RESOLVED = 'resolved', 'Resolved'
        CLOSED = 'closed', 'Closed'

    ofw = models.ForeignKey(
        OFWProfile,
        related_name='concerns',
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='concerns',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    reported_date = models.DateField()
    description = models.TextField(blank=True)
    actions_taken = models.TextField(blank=True)
    resolved_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblconcern'
        ordering = ['-reported_date', '-id']

    def __str__(self):
        return self.title


class SupportRecord(models.Model):
    """Documentation of support or assistance rendered to an OFW."""

    class SupportType(models.TextChoices):
        FINANCIAL = 'financial', 'Financial Assistance'
        LEGAL = 'legal', 'Legal Assistance'
        MEDICAL = 'medical', 'Medical Assistance'
        COUNSELING = 'counseling', 'Counseling'
        REPATRIATION = 'repatriation', 'Repatriation'
        TRAINING = 'training', 'Skills Training'
        LIVELIHOOD = 'livelihood', 'Livelihood'
        REFERRAL = 'referral', 'Referral'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        RELEASED = 'released', 'Released'
        COMPLETED = 'completed', 'Completed'

    ofw = models.ForeignKey(
        OFWProfile,
        related_name='supports',
        on_delete=models.CASCADE,
    )
    concern = models.ForeignKey(
        Concern,
        related_name='supports',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='support_records',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    support_type = models.CharField(
        max_length=20,
        choices=SupportType.choices,
        default=SupportType.OTHER,
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    provider = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal('0'))],
    )
    date_provided = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    document = models.FileField(upload_to='support_docs/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblsupportrecord'
        ordering = ['-date_provided', '-id']

    def __str__(self):
        return self.title


class MonitoringReport(models.Model):
    """A consolidated monitoring report covering a reporting period."""

    class ReportType(models.TextChoices):
        MONTHLY = 'monthly', 'Monthly'
        QUARTERLY = 'quarterly', 'Quarterly'
        ANNUAL = 'annual', 'Annual'
        INCIDENT = 'incident', 'Incident Report'
        CASE = 'case', 'Case Report'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        SUBMITTED = 'submitted', 'Submitted'
        APPROVED = 'approved', 'Approved'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='monitoring_reports',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200)
    report_type = models.CharField(
        max_length=20,
        choices=ReportType.choices,
        default=ReportType.MONTHLY,
    )
    period_start = models.DateField()
    period_end = models.DateField()
    country = models.CharField(max_length=120, blank=True)
    total_ofws = models.PositiveIntegerField(default=0, blank=True)
    total_concerns = models.PositiveIntegerField(default=0, blank=True)
    total_support_cases = models.PositiveIntegerField(default=0, blank=True)
    summary = models.TextField(blank=True)
    findings = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    prepared_by = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    attachment = models.FileField(upload_to='reports/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblmonitoringreport'
        ordering = ['-period_end', '-id']

    def __str__(self):
        return self.title
