import logging
import hashlib
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import LoginAttempt

User = get_user_model()

logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=15)
INVALID_LOGIN_MESSAGE = 'Invalid username or password.'
LOCKED_MESSAGE = 'Too many failed attempts. Locked for 15 minutes.'

REGISTRATION_MAX_ATTEMPTS = 5
REGISTRATION_LOCKOUT_MINUTES = 15


def _lock_key(request, username):
    client_ip = request.META.get('REMOTE_ADDR', '')
    raw = f'{username.strip().casefold()}|{client_ip}'.encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def _get_lock_state(request, username):
    attempt = LoginAttempt.objects.filter(key=_lock_key(request, username)).first()
    if not attempt:
        return 0, None
    if attempt.locked_until and timezone.now() < attempt.locked_until:
        return attempt.failed_attempts, max(
            1, int((attempt.locked_until - timezone.now()).total_seconds())
        )
    if attempt.locked_until:
        attempt.delete()
        return 0, None
    return attempt.failed_attempts, None


def _record_failed_attempt(request, username):
    key = _lock_key(request, username)
    with transaction.atomic():
        attempt, _ = LoginAttempt.objects.select_for_update().get_or_create(key=key)
        attempt.failed_attempts += 1
        if attempt.failed_attempts >= MAX_FAILED_ATTEMPTS:
            attempt.locked_until = timezone.now() + LOCK_DURATION
        attempt.save(update_fields=['failed_attempts', 'locked_until', 'updated_at'])
    if attempt.locked_until:
        remaining = max(1, int((attempt.locked_until - timezone.now()).total_seconds()))
        return attempt.failed_attempts, remaining
    return attempt.failed_attempts, None


def _home_url_name(user):
    """Send OFW accounts to their portal and management users to the dashboard."""
    from apps.ofw.roles import is_ofw

    return 'ofw:portal' if is_ofw(user) else 'dashboard'


def _agency_for_slug(agency_slug):
    if not agency_slug:
        return None
    from apps.users.models import Agency

    return get_object_or_404(Agency, slug__iexact=agency_slug.strip(), is_active=True)


def _auth_context(agency):
    if agency is None:
        return {
            'agency': None,
            'register_url': reverse('register'),
            'login_url': reverse('login'),
        }
    return {
        'agency': agency,
        'register_url': reverse('agency_register', args=[agency.slug]),
        'login_url': reverse('agency_login', args=[agency.slug]),
    }


def agency_landing(request, agency_slug):
    agency = _agency_for_slug(agency_slug)
    if request.user.is_authenticated:
        return redirect(_home_url_name(request.user))
    return render(request, 'auth/agency_landing.html', {
        'agency': agency,
        'register_url': reverse('agency_register', args=[agency.slug]),
        'login_url': reverse('agency_login', args=[agency.slug]),
    })


def _validate_registration_data(data):
    errors = {}

    username = data.get('username', '').strip()
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not username:
        errors['username'] = 'Username is required.'
    elif User.objects.filter(username=username).exists():
        errors['username'] = 'Username already taken.'

    if not first_name:
        errors['first_name'] = 'First name is required.'

    if not last_name:
        errors['last_name'] = 'Last name is required.'

    if not email:
        errors['email'] = 'Email is required.'
    else:
        try:
            validate_email(email)
        except ValidationError:
            errors['email'] = 'Enter a valid email address.'
        else:
            if User.objects.filter(email=email).exists():
                errors['email'] = 'Email already registered.'

    if not password:
        errors['password'] = 'Password is required.'
    elif len(password) < 8:
        errors['password'] = 'Password must be at least 8 characters.'
    else:
        try:
            validate_password(password)
        except ValidationError as exc:
            errors['password'] = ' '.join(exc.messages)

    if password != confirm_password:
        errors['confirm_password'] = 'Passwords do not match.'

    return errors


@require_http_methods(['GET', 'POST'])
def login_view(request, agency_slug=None):
    agency = _agency_for_slug(agency_slug)
    if request.user.is_authenticated:
        return redirect(_home_url_name(request.user))

    context = _auth_context(agency)
    username = request.POST.get('username', '').strip() if request.method == 'POST' else ''
    failed_attempts, remaining = _get_lock_state(request, username)
    if remaining is not None:
        messages.error(
            request,
            f'Too many failed attempts. Try again in {remaining} seconds.',
            extra_tags='lock',
        )
        return render(
            request, 'auth/login.html',
            {**context, 'locked': True, 'remaining': remaining},
        )

    if request.method == 'GET':
        return render(request, 'auth/login.html', context)

    password = request.POST.get('password', '')

    user = authenticate(request, username=username, password=password)

    if user is not None:
        LoginAttempt.objects.filter(key=_lock_key(request, username)).delete()
        login(request, user)
        messages.success(
            request,
            'Logged in successfully.',
            extra_tags='auth',
        )
        return redirect(_home_url_name(user))

    failed_attempts, remaining = _record_failed_attempt(request, username)
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        messages.error(request, LOCKED_MESSAGE, extra_tags='lock')
        return render(
            request, 'auth/login.html',
            {**context, 'locked': True, 'remaining': remaining},
        )

    remaining_attempts = MAX_FAILED_ATTEMPTS - failed_attempts
    messages.error(request, f'{INVALID_LOGIN_MESSAGE} {remaining_attempts} attempts remaining.')
    return render(
        request, 'auth/login.html',
        {**context, 'username': username},
    )


def logout_view(request):
    logout(request)
    messages.success(request, 'Logged out successfully.')
    return redirect('login')


@login_required(login_url='login')
def home(request):
    from apps.ofw.roles import is_ofw

    if is_ofw(request.user):
        return redirect('ofw:portal')

    from apps.ofw.views import dashboard_stats

    return render(request, 'home.html', {'stats': dashboard_stats(request.user)})


@require_http_methods(['GET', 'POST'])
def register_view(request, agency_slug=None):
    agency = _agency_for_slug(agency_slug)
    if request.user.is_authenticated:
        return redirect('dashboard')

    context = _auth_context(agency)

    if request.method == 'GET':
        return render(request, 'auth/register.html', context)

    # Rate-limit registrations by IP to prevent abuse.
    client_ip = request.META.get('REMOTE_ADDR', '')
    reg_key = f'reg:{client_ip}'
    reg_attempts = cache.get(reg_key, 0)
    if reg_attempts >= REGISTRATION_MAX_ATTEMPTS:
        messages.error(
            request,
            f'Too many registration attempts. Try again in '
            f'{REGISTRATION_LOCKOUT_MINUTES} minutes.',
            extra_tags='lock',
        )
        return render(request, 'auth/register.html', {
            **context, 'locked': True,
        })
    cache.set(reg_key, reg_attempts + 1, REGISTRATION_LOCKOUT_MINUTES * 60)

    form_data = {
        'username': request.POST.get('username', ''),
        'first_name': request.POST.get('first_name', ''),
        'middle_name': request.POST.get('middle_name', ''),
        'last_name': request.POST.get('last_name', ''),
        'suffix': request.POST.get('suffix', ''),
        'email': request.POST.get('email', ''),
        'password': request.POST.get('password', ''),
        'confirm_password': request.POST.get('confirm_password', ''),
    }

    errors = _validate_registration_data(form_data)

    if errors:
        return render(
            request, 'auth/register.html',
            {**context, 'errors': errors, 'form_data': form_data},
        )

    from apps.ofw.models import Notification, OFWProfile
    from apps.ofw.notifications import notify, notify_managers
    from apps.ofw.roles import mark_as_ofw

    # Create both records together.  A half-created account (user without an
    # OFW profile) is invisible in the OFW admin and cannot use the portal.
    with transaction.atomic():
        user = User.objects.create_user(
            username=form_data['username'].strip(),
            first_name=form_data['first_name'].strip(),
            last_name=form_data['last_name'].strip(),
            email=form_data['email'].strip(),
            password=form_data['password'],
        )

        mark_as_ofw(user)
        profile = OFWProfile.objects.create(
            user=user,
            first_name=form_data['first_name'].strip(),
            middle_name=form_data['middle_name'].strip(),
            last_name=form_data['last_name'].strip(),
            suffix=form_data['suffix'].strip(),
            email=form_data['email'].strip(),
            country='',
            agency_org=agency,
            agency=agency.name if agency else '',
        )

    # Notifications are useful but must never block a successful registration.
    try:
        notify_managers(
            f'New OFW registered: {profile.full_name}',
            (
                f'{profile.full_name} ({user.username}) just registered. '
                f'Email: {user.email or "not provided"}. '
                f'Country of deployment: {profile.country or "not set"}.'
            ),
            url=reverse('ofw:profile_detail', args=[profile.pk]),
            level=Notification.Level.SUCCESS,
            agency=agency,
        )
        notify(
            user,
            'Welcome to KabayaniTrack',
            (
                'Your OFW account is ready. Complete your profile, especially '
                'your country of deployment, so we can show the right emergency '
                'hotlines.'
            ),
            url=reverse('ofw:portal_profile'),
            level=Notification.Level.INFO,
        )
    except Exception:
        logger.exception('Could not create registration notifications for %s', user.pk)

    login(request, user)
    cache.delete(reg_key)
    return redirect('ofw:portal')
