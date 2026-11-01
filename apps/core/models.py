from django.db import models

class LoginAttempt(models.Model):
    """Shared failed-login counter for a username and client IP pair."""

    key = models.CharField(max_length=64, unique=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'tblloginattempt'

