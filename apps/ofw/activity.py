"""Helpers for deriving OFW inactivity from logins and portal activity."""

import json

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone
from django.db import transaction
from django.urls import reverse

from .models import AuditLog, OFWActivity, Notification
from .notifications import notify, notify_inactivity_managers


def record_activity_event(activity, stage, days, note=''):
    """Write a warning/follow-up event so the OFW and staff can see history.

    Inactivity cycles used to disappear when the counters were reset on the
    next successful login. Audit entries keep the trail without adding a new
    table.
    """
    try:
        AuditLog.objects.create(
            user=None,
            action=AuditLog.Action.UPDATE,
            model_name='OFW activity',
            object_id=str(activity.user_id),
            object_repr=str(activity.user)[:255],
            changes=json.dumps({
                'stage': stage,
                'days_inactive': days,
                'note': note,
            }, default=str),
        )
    except Exception:
        # History must never block the warning itself.
        pass


def send_ofw_warning_email(user, subject, body):
    """Best-effort email copy of an in-app warning.

    OFWs often stop opening the portal before a warning is raised, so the
    in-app message alone cannot reach them. Email is optional: when SMTP is
    not configured the send fails silently and the in-app message remains.
    """
    email = (getattr(user, 'email', '') or '').strip()
    if not email:
        return False
    try:
        send_mail(
            subject,
            body,
            getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            [email],
            fail_silently=True,
        )
        return True
    except Exception:
        return False


def refresh_activity_status(activity, now=None):
    """Refresh one activity row from the account's most recent sign of life.

    ``last_seen_at`` is the later of the last successful login and the last
    recorded portal action, so an OFW who keeps using the portal while a
    session stays open is not treated as missing. Older accounts may predate
    the login signal, so Django's ``last_login`` is used to backfill the
    activity timestamp. Accounts that have never signed in are counted from
    ``date_joined`` while keeping ``last_login_at`` empty.
    """
    now = now or timezone.now()
    user = activity.user
    login_times = [
        value for value in (activity.last_login_at, user.last_login)
        if value is not None
    ]
    last_login_at = max(login_times) if login_times else None
    last_seen_at = activity.last_seen_at
    inactivity_since = last_seen_at or user.date_joined
    days_inactive = max((now - inactivity_since).days, 0)
    is_account_active = days_inactive < OFWActivity.INACTIVE_THRESHOLD_DAYS

    changed_fields = []
    if activity.last_login_at != last_login_at:
        activity.last_login_at = last_login_at
        changed_fields.append('last_login_at')
    if activity.days_inactive != days_inactive:
        activity.days_inactive = days_inactive
        changed_fields.append('days_inactive')
    if activity.is_account_active != is_account_active:
        activity.is_account_active = is_account_active
        changed_fields.append('is_account_active')
    if changed_fields:
        activity.save(update_fields=[*changed_fields, 'updated_at'])
    return activity


def refresh_activities_for_profiles(profiles, now=None):
    """Refresh linked OFW accounts and notify management at 3 and 6 days."""
    now = now or timezone.now()
    users = {}
    profile_by_user = {}
    for profile in profiles.select_related('user', 'agency_org'):
        if profile.user_id:
            users[profile.user_id] = profile.user
            profile_by_user[profile.user_id] = profile
    if not users:
        return []

    activities = {
        activity.user_id: activity
        for activity in OFWActivity.objects.filter(user_id__in=users)
    }
    refreshed = []
    for user_id, user in users.items():
        with transaction.atomic():
            activity = activities.get(user_id)
            if activity is None:
                activity, _ = OFWActivity.objects.get_or_create(user=user)
            activity = OFWActivity.objects.select_for_update().select_related(
                'user'
            ).get(pk=activity.pk)
            profile = profile_by_user[user_id]
            activity = refresh_activity_status(activity, now=now)
            _send_due_inactivity_notification(activity, profile, now)
            refreshed.append(activity)
    return refreshed


def _send_due_inactivity_notification(activity, profile, now):
    """Send one warning per inactivity cycle and one follow-up at day six."""
    days = activity.days_inactive
    if activity.is_account_active or days < OFWActivity.WARNING_DAYS:
        return

    # A declared offline window is not a disappearance. Suppress the warning
    # until the window ends so a seafarer or site worker is not escalated while
    # they told the agency they would be unreachable.
    if activity.offline_notice_active:
        return

    full_name = (profile.full_name or activity.user.username)[:120]
    last_login = (
        timezone.localtime(activity.last_login_at).strftime('%B %d, %Y, %I:%M %p')
        if activity.last_login_at else 'Never logged in'
    )
    last_seen = (
        timezone.localtime(activity.last_seen_at).strftime('%B %d, %Y, %I:%M %p')
        if activity.last_seen_at else 'Never recorded'
    )
    url = reverse('ofw:inactive_ofws')

    if days >= OFWActivity.FOLLOWUP_DAYS and activity.followup_sent_at is None:
        created = notify_inactivity_managers(
            profile,
            f'Follow-up overdue: {full_name}',
            f'{full_name} has not been seen for {days} days. '
            f'Last login: {last_login}. Last activity: {last_seen}. '
            f'Please follow up promptly.',
            url,
            Notification.Level.DANGER,
        )
        if created:
            activity.warning_sent_at = activity.warning_sent_at or now
            activity.followup_sent_at = now
            activity.save(update_fields=[
                'warning_sent_at', 'followup_sent_at', 'updated_at',
            ])
            record_activity_event(
                activity,
                'follow-up',
                days,
                'Six-day follow-up sent to management.',
            )
    elif activity.warning_sent_at is None:
        created = notify_inactivity_managers(
            profile,
            f'OFW login warning: {full_name}',
            f'{full_name} has not been seen for {days} days. '
            f'Last login: {last_login}. Last activity: {last_seen}. '
            f'Contact them for a welfare check.',
            url,
            Notification.Level.WARNING,
        )
        if created:
            activity.warning_sent_at = now
            activity.save(update_fields=['warning_sent_at', 'updated_at'])
            record_activity_event(
                activity,
                'warning',
                days,
                'Three-day warning sent to management.',
            )
            message = (
                f'Hi {profile.first_name or activity.user.first_name}, '
                f'your agency has not seen you for {days} days. '
                f'Log a check-in so they know you are safe, or open '
                f'Emergency SOS if you need help.'
            )
            notify(
                activity.user,
                'Check-in reminder from your agency',
                message,
                url=reverse('ofw:portal_login_warnings'),
                level=Notification.Level.WARNING,
            )
            send_ofw_warning_email(
                activity.user,
                'Your agency is checking on you',
                f'{message}\n\nOpen KabayaniTrack: '
                f'{settings.SITE_BASE_URL}'
                f'{reverse("ofw:portal_login_warnings")}',
            )


def refresh_activity_for_user(user, now=None):
    """Ensure and refresh the current OFW account's activity row."""
    activity, _ = OFWActivity.objects.get_or_create(user=user)
    return refresh_activity_status(activity, now=now)
