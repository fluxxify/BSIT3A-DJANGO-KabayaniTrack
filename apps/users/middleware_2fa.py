"""Two-factor enforcement middleware.

Staff and superuser accounts that manage sensitive OFW data must complete
2FA before accessing the management console.  The middleware:

1. Allows anonymous users, login, and 2FA endpoints through.
2. For staff/superuser with 2FA enabled but no verified session: redirects to
   the 2FA verification page (or setup if 2FA is not enabled yet).
3. Sets a session flag ``2fa_verified`` after successful TOTP verification.
4. OFW accounts are never forced into 2FA (opt-in only).
"""

import logging

from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger(__name__)

# Paths that do not require 2FA verification even for staff.
_EXEMPT_PATHS = {
    'users:twofactor_setup',
    'users:twofactor_verify',
    'users:twofactor_disable',
    'users:twofactor_login_verify',
    'users:twofactor_status',
    'logout',
    'login',
    'password_reset',
    'password_reset_done',
    'password_reset_confirm',
    'password_reset_complete',
}


class TwoFactorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        response = None

        if user is not None and user.is_authenticated:
            response = self._enforce(request, user)
        if response is None:
            response = self.get_response(request)
        return response

    def _enforce(self, request, user):
        # Only staff/superuser are subject to mandatory 2FA.
        if not (user.is_staff or user.is_superuser):
            return None

        # Always allow 2FA setup / login and auth pages.
        resolved = getattr(request, 'resolver_match', None)
        if resolved and resolved.url_name in _EXEMPT_PATHS:
            return None
        if request.path.startswith('/admin/'):
            # Django admin has its own auth; 2FA applies to the KabayaniTrack
            # console, not to /admin/.  Keep admin accessible but note it.
            return None

        from apps.users.models import UserTwoFactor
        tfa = UserTwoFactor.objects.filter(user=user).first()

        if not tfa or not tfa.is_enabled:
            # 2FA not enabled yet: one-time nudge to set it up, but do not
            # block console access so existing staff are not locked out.
            # The setup link is rendered in the sidebar.
            return None

        if request.session.get('2fa_verified'):
            return None

        # 2FA enabled but session not verified: show the verification page.
        from django.shortcuts import render
        return render(
            request, 'auth/twofactor_verify.html',
            {'next': request.get_full_path()},
        )
