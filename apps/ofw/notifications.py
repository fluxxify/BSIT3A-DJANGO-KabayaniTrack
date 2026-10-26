"""Small helpers for creating in-app notifications."""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
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
                    exclude_user=None):
    """Notify every active staff member and administrator.

    ``exclude_user`` avoids notifying the person who performed the action (for
    example an administrator logging a check-in on their own account).
    """
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


def mark_concern_read_by_management(concern, user):
    """Mark a concern as seen by management and tell the OFW exactly once.

    Management includes both staff members and administrators.  Merely listing
    concerns does not count as "reading" one; the concern must be opened
    (detail page) or loaded for editing.
    """
    if not (user.is_staff or user.is_superuser):
        return False
    if concern.read_by_management_at is not None:
        return False

    concern.read_by_management_at = timezone.now()
    concern.save(update_fields=['read_by_management_at'])

    recipient = concern.ofw.user
    if recipient is not None and recipient.pk != user.pk:
        notify(
            recipient,
            'Your concern has been read',
            f'Your concern "{concern.title}" has been read by the management '
            'team. They will review it and keep you updated.',
            url=reverse('ofw:portal_concerns'),
            level=Notification.Level.INFO,
        )
    return True
