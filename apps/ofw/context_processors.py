"""Template context shared by the notification bell, sidebar badges and agency
branding."""

from apps.users.agencies import agency_for_user

from .models import Notification


def notifications(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    queryset = Notification.objects.filter(recipient=user)
    return {
        'unread_notifications_count': queryset.filter(is_read=False).count(),
        'recent_notifications': list(queryset[:6]),
        'current_agency': agency_for_user(user),
    }
