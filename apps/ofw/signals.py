"""Housekeeping for records removed through the management or portal UI.

Django cascades database rows, but it does not remove files from storage or
clean up notifications that point at a record that no longer exists.  These
handlers keep the media directory and notification centre consistent with the
database.

Also tracks OFW account activity so management and agency staff can see which
OFWs have been inactive for 3-5 days and need a welfare check / police escalation.
"""

from django.contrib.auth.models import User
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone

from .models import (
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyAlert,
    LocationTracker,
    MonitoringReport,
    Notification,
    OFWActivity,
    OFWProfile,
    PoliceReport,
    SafeLocation,
)


def _file_name(field_file):
    return getattr(field_file, 'name', '') or ''


def _delete_stored_name(storage, name):
    if not name or storage is None:
        return
    try:
        storage.delete(name)
    except Exception:
        # A missing file (or a storage backend that cannot delete) must not
        # turn a successful record deletion into a 500 response.
        pass


def _delete_stored_file(field_file):
    _delete_stored_name(getattr(field_file, 'storage', None), _file_name(field_file))


def _delete_notifications_for(url):
    if url:
        Notification.objects.filter(url=url).delete()


@receiver(post_delete, sender=ConcernProof)
def delete_concern_proof_file(sender, instance, **kwargs):
    _delete_stored_file(instance.file)


@receiver(post_delete, sender=Concern)
def delete_concern_notifications(sender, instance, **kwargs):
    _delete_notifications_for(
        reverse('ofw:concern_detail', args=[instance.pk])
    )


@receiver(post_delete, sender=CheckIn)
def delete_checkin_notifications(sender, instance, **kwargs):
    _delete_notifications_for(
        reverse('ofw:checkin_detail', args=[instance.pk])
    )


@receiver(post_delete, sender=OFWProfile)
def delete_profile_file_and_notifications(sender, instance, **kwargs):
    _delete_stored_file(instance.profile_picture)
    _delete_notifications_for(
        reverse('ofw:profile_detail', args=[instance.pk])
    )


@receiver(post_delete, sender=MonitoringReport)
def delete_report_attachment(sender, instance, **kwargs):
    _delete_stored_file(instance.attachment)


@receiver(pre_save, sender=OFWProfile)
def remember_replaced_profile_picture(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    instance._replaced_profile_picture_name = _file_name(previous.profile_picture)


@receiver(post_save, sender=OFWProfile)
def delete_replaced_profile_picture(sender, instance, **kwargs):
    old_name = getattr(instance, '_replaced_profile_picture_name', '')
    new_name = _file_name(instance.profile_picture)
    if old_name and old_name != new_name:
        _delete_stored_name(instance.profile_picture.storage, old_name)
    if hasattr(instance, '_replaced_profile_picture_name'):
        del instance._replaced_profile_picture_name


@receiver(pre_save, sender=MonitoringReport)
def remember_replaced_report_attachment(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        previous = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return
    instance._replaced_report_attachment_name = _file_name(previous.attachment)


@receiver(post_save, sender=MonitoringReport)
def delete_replaced_report_attachment(sender, instance, **kwargs):
    old_name = getattr(instance, '_replaced_report_attachment_name', '')
    new_name = _file_name(instance.attachment)
    if old_name and old_name != new_name:
        _delete_stored_name(instance.attachment.storage, old_name)
    if hasattr(instance, '_replaced_report_attachment_name'):
        del instance._replaced_report_attachment_name


# ---------------------------------------------------------------------------
# OFW activity tracking (inactive account detection + emergency alerts)
# ---------------------------------------------------------------------------


@receiver(post_save, sender=User)
def ensure_ofw_activity(sender, instance, created, **kwargs):
    """Create an OFWActivity row for every new OFW (non-staff) user."""
    if created and not instance.is_staff and not instance.is_superuser:
        OFWActivity.objects.get_or_create(user=instance)


@receiver(post_save, sender=OFWProfile)
def update_activity_on_profile_change(sender, instance, **kwargs):
    """Bump last_activity_at whenever an OFW profile is updated."""
    if instance.user_id:
        activity, _ = OFWActivity.objects.get_or_create(user_id=instance.user_id)
        activity.last_activity_at = timezone.now()
        activity.is_account_active = True
        activity.days_inactive = 0
        activity.save(update_fields=['last_activity_at', 'is_account_active', 'days_inactive', 'updated_at'])


@receiver(user_logged_in)
def update_activity_on_login(sender, request, user, **kwargs):
    """Bump last_login_at / last_activity_at when an OFW signs in."""
    if not user.is_staff and not user.is_superuser:
        activity, _ = OFWActivity.objects.get_or_create(user=user)
        now = timezone.now()
        activity.last_login_at = now
        activity.last_activity_at = now
        activity.is_account_active = True
        activity.days_inactive = 0
        activity.save(update_fields=[
            'last_login_at', 'last_activity_at',
            'is_account_active', 'days_inactive', 'updated_at',
        ])
