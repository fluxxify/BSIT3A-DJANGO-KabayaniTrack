"""Middleware that records real OFW portal activity.

The Login Warnings page tells OFWs that using the portal counts as activity.
Sessions can stay signed in for days, so relying on the login signal alone
would flag an OFW who opens the portal every day but never signs in again.
This middleware refreshes ``last_activity_at`` for authenticated OFW portal
requests, throttled to one database write every five minutes.
"""

from datetime import timedelta

from django.utils import timezone

from .models import OFWActivity

THROTTLE = timedelta(minutes=5)
PORTAL_PREFIX = '/ofw/portal/'


class OFWActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        self.record_activity(request)
        return response

    @staticmethod
    def record_activity(request):
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return
        if user.is_staff or user.is_superuser:
            return
        if request.method != 'GET':
            return
        if not request.path.startswith(PORTAL_PREFIX):
            return

        now = timezone.now()
        cutoff = now - THROTTLE
        activity, _ = OFWActivity.objects.get_or_create(user_id=user.pk)
        if activity.last_activity_at is not None and activity.last_activity_at >= cutoff:
            return
        activity.last_activity_at = now
        activity.save(update_fields=['last_activity_at', 'updated_at'])
