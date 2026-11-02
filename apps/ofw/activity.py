"""Helpers for deriving OFW inactivity from successful login timestamps."""

from django.utils import timezone

from .models import OFWActivity


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
    """Ensure and refresh activity rows for every linked OFW account."""
    now = now or timezone.now()
    users = {}
    for profile in profiles.select_related('user'):
        if profile.user_id:
            users[profile.user_id] = profile.user
    if not users:
        return []

    activities = {
        activity.user_id: activity
        for activity in OFWActivity.objects.filter(user_id__in=users)
    }
    refreshed = []
    for user_id, user in users.items():
        activity = activities.get(user_id)
        if activity is None:
            activity, _ = OFWActivity.objects.get_or_create(user=user)
        refreshed.append(refresh_activity_status(activity, now=now))
    return refreshed


def refresh_activity_for_user(user, now=None):
    """Ensure and refresh the current OFW account's activity row."""
    activity, _ = OFWActivity.objects.get_or_create(user=user)
    return refresh_activity_status(activity, now=now)
