"""Helpers for deriving OFW inactivity from successful login timestamps."""

from django.utils import timezone
from django.db import transaction
from django.urls import reverse

from .models import OFWActivity, Notification
from .notifications import notify_inactivity_managers


def refresh_activity_status(activity, now=None):
    """Refresh one activity row from the account's most recent login.

    Older accounts may predate the login signal, so Django's ``last_login`` is
    used to backfill the activity timestamp. Accounts that have never signed
    in are counted from ``date_joined`` while keeping ``last_login_at`` empty.
    """
    now = now or timezone.now()
    user = activity.user
    login_times = [
        value for value in (activity.last_login_at, user.last_login)
        if value is not None
    ]
    last_login_at = max(login_times) if login_times else None
    inactivity_since = last_login_at or user.date_joined
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
    if activity.is_account_active or days < OFWActivity.INACTIVE_THRESHOLD_DAYS:
        return

    full_name = (profile.full_name or activity.user.username)[:120]
    last_login = (
        timezone.localtime(activity.last_login_at).strftime('%B %d, %Y, %I:%M %p')
        if activity.last_login_at else 'Never logged in'
    )
    url = reverse('ofw:inactive_ofws')

    if days > 5 and activity.followup_sent_at is None:
        created = notify_inactivity_managers(
            profile,
            f'Follow-up overdue: {full_name}',
            f'{full_name} has not successfully logged in for {days} days. '
            f'Last login: {last_login}. Please follow up promptly.',
            url,
            Notification.Level.DANGER,
        )
        if created:
            activity.warning_sent_at = activity.warning_sent_at or now
            activity.followup_sent_at = now
            activity.save(update_fields=[
                'warning_sent_at', 'followup_sent_at', 'updated_at',
            ])
    elif activity.warning_sent_at is None:
        created = notify_inactivity_managers(
            profile,
            f'OFW login warning: {full_name}',
            f'{full_name} has not successfully logged in for {days} days. '
            f'Last login: {last_login}. Contact them for a welfare check.',
            url,
            Notification.Level.WARNING,
        )
        if created:
            activity.warning_sent_at = now
            activity.save(update_fields=['warning_sent_at', 'updated_at'])


def refresh_activity_for_user(user, now=None):
    """Ensure and refresh the current OFW account's activity row."""
    activity, _ = OFWActivity.objects.get_or_create(user=user)
    return refresh_activity_status(activity, now=now)
