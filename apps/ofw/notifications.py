"""Small helpers for creating in-app notifications.

Notifications are reserved for events that need action or reassurance:
emergencies, concerns, check-ins, inactivity warnings and case status changes.
Routine edits such as updating a profile or adding a family contact stay silent
on purpose so the bell does not become noisy.
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .models import Notification

User = get_user_model()


def notify(user, title, message='', url='', level=Notification.Level.INFO):
    """Create a notification for a single user (no-op for anonymous users)."""
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    return Notification.objects.create(
        recipient=user,
        title=title,
        message=message,
        url=url,
        level=level,
    )


def notify_managers(title, message='', url='', level=Notification.Level.INFO,
                    exclude_user=None, agency=None):
    """Notify the relevant agency staff.

    When ``agency`` is supplied, only that agency's staff are notified.
    Without an agency, all staff are notified (legacy/global behaviour).
    Superusers are intentionally excluded from agency-scoped notifications so
    that an OFW's agency is the only one that sees alerts about their OFWs.
    """
    if agency is not None:
        recipients = User.objects.filter(
            agency_staff__agency=agency,
            is_active=True,
        )
    else:
        recipients = User.objects.filter(
            Q(is_staff=True) | Q(is_superuser=True),
            is_active=True,
        )
    if exclude_user is not None and exclude_user.is_authenticated:
        recipients = recipients.exclude(pk=exclude_user.pk)

    return Notification.objects.bulk_create([
        Notification(
            recipient=user,
            title=title,
            message=message,
            url=url,
            level=level,
        )
        for user in recipients
    ])


def notify_inactivity_managers(profile, title, message, url, level):
    """Notify global admins and the agency assigned to an inactive OFW."""
    if profile.agency_org_id:
        recipients = User.objects.filter(is_active=True).filter(
            Q(is_superuser=True) |
            Q(is_staff=True, agency_staff__agency_id=profile.agency_org_id) |
            Q(is_staff=True, agency_staff__isnull=True)
        ).distinct()
    else:
        recipients = User.objects.filter(
            Q(is_staff=True) | Q(is_superuser=True), is_active=True,
        ).distinct()

    notifications = Notification.objects.bulk_create([
        Notification(
            recipient=user,
            title=title,
            message=message,
            url=url,
            level=level,
        )
        for user in recipients
    ])
    return len(notifications)


def mark_concern_read_by_management(concern, user):
    """Mark a concern as seen by management.

    Management includes both staff members and administrators.  Merely listing
    concerns does not count as "reading" one; the concern must be opened
    (detail page) or loaded for editing.  This is silent: a read receipt is
    routine and would only add notification noise.
    """
    if not (user.is_staff or user.is_superuser):
        return False
    if concern.read_by_management_at is not None:
        return False

    concern.read_by_management_at = timezone.now()
    concern.save(update_fields=['read_by_management_at'])
    return True
