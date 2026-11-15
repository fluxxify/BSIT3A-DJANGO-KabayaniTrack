from django.conf import settings
from django.db import models
from django.utils import timezone


class Agency(models.Model):
    """A recruitment agency (or partner office) using KabayaniTrack."""

    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    website = models.URLField(max_length=255, blank=True)
    category = models.CharField(max_length=200, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=60, blank=True)
    email = models.EmailField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tblagency'
        ordering = ['name']
        verbose_name_plural = 'agencies'

    def __str__(self):
        return self.name


class AgencyStaff(models.Model):
    """Link a management user to exactly one agency."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='agency_staff',
    )
    agency = models.ForeignKey(
        Agency,
        on_delete=models.CASCADE,
        related_name='staff',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'tblagencystaff'

    def __str__(self):
        return f'{self.user.username} — {self.agency.name}'


class UserTwoFactor(models.Model):
    """TOTP two-factor state for a user account.

    Required for staff and superuser accounts that manage sensitive OFW data.
    OFW accounts may opt in.  When enabled, the user must present a valid
    6-digit TOTP code after password login before the session is considered
    fully authenticated.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='two_factor',
    )
    secret_key = models.CharField(max_length=64, blank=True,
        help_text='Base32 TOTP secret (set when 2FA is enabled).')
    backup_codes_hash = models.CharField(max_length=255, blank=True,
        help_text='Hashed single-use backup codes (newline-separated).')
    is_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tblusertwofactor'

    def __str__(self):
        return f'{self.user.username} 2FA: {"on" if self.is_enabled else "off"}'

    def generate_secret(self):
        from .totp import generate_secret
        self.secret_key = generate_secret()
        return self.secret_key

    def verify_code(self, code):
        """Verify a TOTP code and record the verification time."""
        from .totp import verify_totp
        if not self.secret_key:
            return False
        ok = verify_totp(self.secret_key, code)
        if ok:
            self.last_verified_at = timezone.now()
            self.save(update_fields=['last_verified_at'])
        return ok
