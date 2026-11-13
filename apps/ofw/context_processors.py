"""Template context shared by the notification bell, sidebar badges and agency
branding."""

from django.urls import reverse

from apps.users.agencies import agency_for_user

from .models import (
    EmergencyAlert,
    Notification,
    OFWActivity,
    OFWLocationSharing,
    SafeLocationSuggestion,
)
from .roles import is_ofw


def notifications(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    queryset = Notification.objects.filter(recipient=user)
    ctx = {
        'unread_notifications_count': queryset.filter(is_read=False).count(),
        'recent_notifications': list(queryset[:6]),
        'current_agency': agency_for_user(user),
    }

    # Inactive OFW count shown to management on the dashboard header
    if user.is_superuser or user.is_staff:
        from django.db.models import Q
        inactive_qs = OFWActivity.objects.filter(
            is_account_active=False,
            days_inactive__gte=OFWActivity.INACTIVE_THRESHOLD_DAYS,
        )
        if not user.is_superuser:
            agency = agency_for_user(user)
            if agency is not None:
                inactive_qs = inactive_qs.filter(user__ofw_profiles__agency_org=agency).distinct()
            else:
                inactive_qs = inactive_qs.none()
        ctx['inactive_ofw_count'] = inactive_qs.count()

        # Open emergency alerts count
        alerts_qs = EmergencyAlert.objects.filter(status=EmergencyAlert.Status.OPEN)
        if not user.is_superuser:
            agency = agency_for_user(user)
            if agency is not None:
                alerts_qs = alerts_qs.filter(ofw__agency_org=agency)
            else:
                alerts_qs = alerts_qs.none()
        ctx['open_emergency_alert_count'] = alerts_qs.count()

        # Safe place suggestions waiting for a review decision.
        suggestions_qs = SafeLocationSuggestion.objects.filter(
            status=SafeLocationSuggestion.Status.PENDING
        )
        if not user.is_superuser:
            agency = agency_for_user(user)
            if agency is not None:
                suggestions_qs = suggestions_qs.filter(
                    submitted_by__ofw_profiles__agency_org=agency
                ).distinct()
            else:
                suggestions_qs = suggestions_qs.none()
        ctx['pending_safe_location_suggestions_count'] = suggestions_qs.count()

    return ctx


def live_location(request):
    """Tell the base template whether to load the OFW location tracker.

    The tracker lives in ``theme/base.html`` so it keeps running when the OFW
    moves between portal pages instead of dying with the location page.  Only
    OFW accounts that explicitly enabled sharing pay for the extra query;
    management users and anonymous visitors get an empty dict.
    """
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated or not is_ofw(user):
        return {}

    profile = user.ofw_profiles.order_by('id').only('id').first()
    if profile is None:
        return {}

    enabled = OFWLocationSharing.objects.filter(
        ofw_id=profile.pk, is_enabled=True
    ).exists()
    if not enabled:
        return {'live_location_enabled': False}

    return {
        'live_location_enabled': True,
        'live_location_ping_url': reverse('ofw:portal_location_sharing_ping'),
    }
