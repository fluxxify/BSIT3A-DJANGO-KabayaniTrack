"""Template context shared by the notification bell and sidebar badges."""

from .models import Notification


def notifications(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}

    queryset = Notification.objects.filter(recipient=user)
    return {
        'unread_notifications_count': queryset.filter(is_read=False).count(),
        'recent_notifications': list(queryset[:6]),
    }
