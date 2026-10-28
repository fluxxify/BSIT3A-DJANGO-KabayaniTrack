from django.conf import settings
from django.db import models


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
