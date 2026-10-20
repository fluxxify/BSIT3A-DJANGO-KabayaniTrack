"""Domain models for KabayaniTrack, an OFW monitoring and support information system.

The system tracks five key areas:
  * OFW profiles and their welfare status
  * periodic welfare assessments
  * periodic check-ins
  * reported concerns
  * emergency contacts directory
  * monitoring reports
"""

import os

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class WelfareStatus(models.TextChoices):
    ACTIVE = 'active', 'Okay / Working'
    NEEDS_SUPPORT = 'needs_support', 'Needs Help'
    DISTRESSED = 'distressed', 'At Risk / In Danger'
    REPATRIATED = 'repatriated', 'Back in the Philippines'
    MISSING = 'missing', 'Cannot Be Reached'


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
    age = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(150)],
    )
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


class ConcernProof(models.Model):
    """A photo or video file submitted as proof for a reported concern."""

    IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
    VIDEO_EXTENSIONS = ('.mp4', '.mov', '.webm', '.m4v', '.avi', '.mkv', '.3gp')
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB per file
    MAX_FILES = 5

    concern = models.ForeignKey(
        Concern,
        related_name='proofs',
        on_delete=models.CASCADE,
    )
    file = models.FileField(upload_to='concern_proofs/%Y/%m/')
    original_name = models.CharField(max_length=255, blank=True)
    caption = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tblconcernproof'
        ordering = ['uploaded_at', 'id']

    @property
    def is_video(self):
        return os.path.splitext(self.file.name)[1].lower() in self.VIDEO_EXTENSIONS

    @property
    def is_image(self):
        return os.path.splitext(self.file.name)[1].lower() in self.IMAGE_EXTENSIONS

    @property
    def display_name(self):
        return self.original_name or os.path.basename(self.file.name)

    def __str__(self):
        return f'Proof for {self.concern}: {self.display_name}'


class EmergencyContact(models.Model):
    """A directory entry for embassies, hotlines, or personal contacts."""

    class ContactType(models.TextChoices):
        EMBASSY = 'embassy', 'Embassy / Consulate'
        POLO = 'polo', 'POLO / Labor Office'
        OWWA = 'owwa', 'OWWA'
        DMW = 'dmw', 'DMW Hotline'
        POLICE = 'police', 'Police'
        HOSPITAL = 'hospital', 'Hospital / Medical'
        AGENCY = 'agency', 'Recruitment Agency'
        EMPLOYER = 'employer', 'Employer'
        FAMILY = 'family', 'Family / Next of Kin'
        OTHER = 'other', 'Other'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='emergency_contacts',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=200, help_text='Person or office to contact')
    contact_type = models.CharField(
        max_length=20,
        choices=ContactType.choices,
        default=ContactType.OTHER,
    )
    country = models.CharField(max_length=120, blank=True)
    city = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=60)
    email = models.EmailField(max_length=255, blank=True)
    website = models.URLField(
        max_length=255, blank=True,
        help_text='Official website (leave blank to use the default for this type)',
    )
    address = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Fallback websites for contact types that usually have an official portal.
    DEFAULT_WEBSITES = {
        'embassy': 'https://dfa.gov.ph',
        'polo': 'https://www.dmw.gov.ph',
        'owwa': 'https://owwa.gov.ph',
        'dmw': 'https://dmw.gov.ph',
    }

    # Types treated as public hotlines (shown to every OFW based on country),
    # as opposed to personal contacts (family, employer, agency) that stay private.
    PUBLIC_TYPES = ('embassy', 'polo', 'owwa', 'dmw', 'police', 'hospital')

    class Meta:
        db_table = 'tblemergencycontact'
        ordering = ['contact_type', 'name']

    def __str__(self):
        return f'{self.name} ({self.get_contact_type_display()})'

    def website_url(self):
        """Return the resolved website, falling back to a type default."""
        return self.website or self.DEFAULT_WEBSITES.get(self.contact_type, '')


class EmergencyContactRequest(models.Model):
    """A request by an OFW to add a family emergency contact.

    The management team reviews each request; approving one creates a
    matching :class:`EmergencyContact` owned by the requesting OFW.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='contact_requests',
        on_delete=models.CASCADE,
    )
    ofw = models.ForeignKey(
        OFWProfile,
        related_name='contact_requests',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=200, help_text='Family member to contact')
    relationship = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=60)
    email = models.EmailField(max_length=255, blank=True)
    address = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='reviewed_contact_requests',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    review_notes = models.TextField(blank=True)

    class Meta:
        db_table = 'tblemergencycontactrequest'
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.name} ({self.get_status_display()})'


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
    summary = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    attachment = models.FileField(upload_to='reports/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblmonitoringreport'
        ordering = ['-period_end', '-id']

    def __str__(self):
        return self.title
