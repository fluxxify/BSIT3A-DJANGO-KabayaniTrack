"""Two-factor authentication views (setup, verify, disable).

AJAX-only endpoints used by the 2FA setup modal and the login flow.
"""

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .models import UserTwoFactor
from .totp import generate_backup_codes, generate_secret, verify_totp

logger = logging.getLogger(__name__)

User = get_user_model()


def _require_staff_or_self(request, user):
    """Staff/superuser may manage any account; OFW only their own."""
    if request.user.is_superuser or request.user.is_staff:
        return None
    if request.user.pk == user.pk:
        return None
    return JsonResponse({'error': 'Not allowed.'}, status=403)


@login_required
@require_POST
def twofactor_setup(request):
    """Generate a TOTP secret and return it with backup codes.

    The secret is shown once (with a QR code URL).  The caller must then call
    ``twofactor_verify`` with a valid code to activate 2FA.
    """
    denied = _require_staff_or_self(request, request.user)
    if denied:
        return denied

    tfa, _ = UserTwoFactor.objects.get_or_create(user=request.user)
    if tfa.is_enabled:
        return JsonResponse(
            {'error': 'Two-factor authentication is already enabled.'}, status=400,
        )

    secret = generate_secret()
    tfa.secret_key = secret
    tfa.is_enabled = False  # not active until a code is verified
    tfa.save(update_fields=['secret_key'])

    backup_codes = generate_backup_codes()
    # Store hashed backup codes so they can be checked but not read back.
    from django.contrib.auth.hashers import make_password
    tfa._backup_codes_plain = backup_codes  # temporary, used below
    # Save hashed versions
    from .models import UserTwoFactor as _TFA
    # We'll store backup codes in a separate field is overkill; keep them in
    # the session for one round trip.  Instead, save hashed codes now.
    tfa.backup_codes_hash = make_password('\n'.join(backup_codes))
    tfa.save(update_fields=['backup_codes_hash'])

    return JsonResponse({
        'ok': True,
        'secret_key': secret,
        'backup_codes': backup_codes,
        'qr_url': (
            'https://chart.googleapis.com/chart?chs=200x200&chld=M|0&cht=qr&'
            'chl=otpauth://totp/KabayaniTrack:%s?secret=%s&issuer=KabayaniTrack'
        ) % (request.user.username, secret),
        'manual_entry_key': secret,
    })


@login_required
@require_POST
def twofactor_verify(request):
    """Verify a TOTP code and activate 2FA for the account."""
    denied = _require_staff_or_self(request, request.user)
    if denied:
        return denied

    tfa = get_object_or_404(UserTwoFactor, user=request.user)
    code = (request.POST.get('code') or '').strip()
    if not tfa.secret_key:
        return JsonResponse(
            {'error': 'No setup in progress. Run setup first.'}, status=400,
        )
    if not verify_totp(tfa.secret_key, code):
        return JsonResponse({'error': 'Invalid code. Try again.'}, status=400)

    tfa.is_enabled = True
    tfa.last_verified_at = None
    tfa.save(update_fields=['is_enabled', 'last_verified_at'])
    messages.success(request, 'Two-factor authentication is now active. Save your backup codes.')
    return JsonResponse({'ok': True})


@login_required
@require_POST
def twofactor_disable(request):
    """Disable 2FA (staff/superuser can disable any account; OFW only their own)."""
    user_id = (request.POST.get('user_id') or '').strip()
    target = get_object_or_404(User, pk=user_id)
    denied = _require_staff_or_self(request, target)
    if denied:
        return denied

    tfa = get_object_or_404(UserTwoFactor, user=target)
    tfa.is_enabled = False
    tfa.secret_key = ''
    tfa.backup_codes_hash = ''
    tfa.last_verified_at = None
    tfa.save(
        update_fields=['is_enabled', 'secret_key', 'backup_codes_hash',
                       'last_verified_at']
    )
    messages.success(
        request,
        f'Two-factor authentication disabled for {target.username}.',
    )
    return JsonResponse({'ok': True})


@login_required
@require_POST
def twofactor_login_verify(request):
    """Verify a TOTP code during login (second factor).

    Sets ``request.session['2fa_verified'] = True`` on success.  The login
    view checks this before allowing staff/superuser access.
    """
    code = (request.POST.get('code') or '').strip()
    tfa = get_object_or_404(UserTwoFactor, user=request.user)
    if not tfa.is_enabled or not tfa.secret_key:
        return JsonResponse(
            {'error': 'Two-factor is not enabled for this account.'}, status=400,
        )
    if not verify_totp(tfa.secret_key, code):
        return JsonResponse({'error': 'Invalid code.'}, status=400)

    tfa.last_verified_at = None
    tfa.save(update_fields=['last_verified_at'])
    request.session['2fa_verified'] = True
    request.session['2fa_user_id'] = request.user.pk
    return JsonResponse({'ok': True})


@login_required
def twofactor_status(request):
    """Return 2FA status for the current user (used by the settings sidebar)."""
    tfa = UserTwoFactor.objects.filter(user=request.user).first()
    return JsonResponse({
        'enabled': bool(tfa and tfa.is_enabled),
        'has_secret': bool(tfa and tfa.secret_key),
        'last_verified': (
            tfa.last_verified_at.isoformat() if tfa and tfa.last_verified_at
            else None
        ),
    })


def twofactor_required_redirect(request):
    """Redirect staff/superuser to 2FA setup or login verification.

    Used by middleware when a staff account has 2FA enabled but the session
    is not yet verified.
    """
    user = request.user
    if not (user.is_staff or user.is_superuser):
        return None
    tfa = UserTwoFactor.objects.filter(user=user).first()
    if not tfa or not tfa.is_enabled:
        # Not set up yet: send to the users management page where setup lives.
        return redirect('users:user_list')
    if not request.session.get('2fa_verified'):
        return render(request, 'auth/twofactor_verify.html', {
            'next': request.GET.get('next', '/home/'),
        })
    return None
