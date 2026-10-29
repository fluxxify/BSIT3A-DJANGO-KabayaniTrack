"""Template context shared by the notification bell, sidebar badges and agency
branding."""

from apps.users.agencies import agency_for_user

from .models import EmergencyAlert, Notification, OFWActivity


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

    return ctx