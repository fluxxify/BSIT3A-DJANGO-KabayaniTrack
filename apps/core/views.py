from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

User = get_user_model()

MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=1)
INVALID_LOGIN_MESSAGE = 'Invalid username or password.'
LOCKED_MESSAGE = 'Too many failed attempts. Locked for 1 minute.'


def _reset_lock_state(request):
    request.session['failed_attempts'] = 0
    request.session['lock_time'] = None


def _get_lock_state(request):
    failed_attempts = request.session.get('failed_attempts', 0)
    lock_time = request.session.get('lock_time')

    if not lock_time:
        return failed_attempts, None

    try:
        unlock_time = timezone.datetime.fromisoformat(lock_time)
    except (TypeError, ValueError):
        _reset_lock_state(request)
        return 0, None

    if timezone.now() < unlock_time:
        remaining = int((unlock_time - timezone.now()).total_seconds())
        return failed_attempts, remaining

    _reset_lock_state(request)
    return 0, None


def _set_lock_state(request):
    lock_until = timezone.now() + LOCK_DURATION
    request.session['failed_attempts'] = MAX_FAILED_ATTEMPTS
    request.session['lock_time'] = lock_until.isoformat()
    return int(LOCK_DURATION.total_seconds())


def _home_url_name(user):
    """Send OFW accounts to their portal and management users to the dashboard."""
    from apps.ofw.roles import is_ofw

    return 'ofw:portal' if is_ofw(user) else 'dashboard'


def _account_type_context(selected=''):
    from apps.ofw.roles import ACCOUNT_TYPE_CHOICES

    return {'account_types': ACCOUNT_TYPE_CHOICES, 'selected_type': selected}


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
def login_view(request):
    if request.user.is_authenticated:
        return redirect(_home_url_name(request.user))

    failed_attempts, remaining = _get_lock_state(request)
    if remaining is not None:
        messages.error(request, f'Too many failed attempts. Try again in {remaining} seconds.')
        return render(
            request, 'auth/login.html',
            {**_account_type_context(), 'locked': True, 'remaining': remaining},
        )

    if request.method == 'GET':
        return render(request, 'auth/login.html', _account_type_context())

    from apps.ofw.roles import account_role, account_role_label

    username = request.POST.get('username', '').strip()
    password = request.POST.get('password', '')
    account_type = request.POST.get('account_type', '').strip()
    valid_types = {'admin', 'ofw', 'staff'}

    if account_type not in valid_types:
        messages.error(request, 'Please choose the account type you are signing in as.')
        return render(
            request, 'auth/login.html',
            {**_account_type_context(account_type), 'username': username},
        )

    user = authenticate(request, username=username, password=password)

    if user is not None:
        if account_role(user) != account_type:
            label = account_role_label(account_type)
            messages.error(
                request,
                f'These credentials do not match the {label} account type. '
                'Please pick the correct account type.',
            )
            return render(
                request, 'auth/login.html',
                {**_account_type_context(account_type), 'username': username},
            )

        _reset_lock_state(request)
        login(request, user)
        return redirect(_home_url_name(user))

    failed_attempts += 1
    request.session['failed_attempts'] = failed_attempts
    if failed_attempts >= MAX_FAILED_ATTEMPTS:
        remaining = _set_lock_state(request)
        messages.error(request, LOCKED_MESSAGE)
        return render(
            request, 'auth/login.html',
            {**_account_type_context(), 'locked': True, 'remaining': remaining},
        )

    remaining_attempts = MAX_FAILED_ATTEMPTS - failed_attempts
    messages.error(request, f'{INVALID_LOGIN_MESSAGE} {remaining_attempts} attempts remaining.')
    return render(
        request, 'auth/login.html',
        {**_account_type_context(account_type), 'username': username},
    )


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def home(request):
    from apps.ofw.roles import is_ofw

    if is_ofw(request.user):
        return redirect('ofw:portal')

    from apps.ofw.views import dashboard_stats

    return render(request, 'home.html', {'stats': dashboard_stats(request.user)})


@require_http_methods(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'auth/register.html', _account_type_context('ofw'))

    form_data = {
        'username': request.POST.get('username', ''),
        'first_name': request.POST.get('first_name', ''),
        'last_name': request.POST.get('last_name', ''),
        'email': request.POST.get('email', ''),
        'password': request.POST.get('password', ''),
        'confirm_password': request.POST.get('confirm_password', ''),
    }

    errors = _validate_registration_data(form_data)

    account_type = request.POST.get('account_type', 'ofw').strip() or 'ofw'
    if account_type != 'ofw':
        errors['account_type'] = 'Only OFW accounts can be self-registered.'

    if errors:
        return render(
            request, 'auth/register.html',
            {**_account_type_context(account_type), 'errors': errors, 'form_data': form_data},
        )

    user = User.objects.create_user(
        username=form_data['username'].strip(),
        first_name=form_data['first_name'].strip(),
        last_name=form_data['last_name'].strip(),
        email=form_data['email'].strip(),
        password=form_data['password'],
    )

    from apps.ofw.models import OFWProfile
    from apps.ofw.roles import mark_as_ofw

    mark_as_ofw(user)
    OFWProfile.objects.create(
        user=user,
        first_name=form_data['first_name'].strip(),
        last_name=form_data['last_name'].strip(),
        email=form_data['email'].strip(),
    )

    login(request, user)
    return redirect('ofw:portal')
