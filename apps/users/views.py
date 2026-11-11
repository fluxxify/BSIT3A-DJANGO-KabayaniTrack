"""Administrator screens for agencies and agency user accounts.

Only superusers may manage accounts and agencies.  The querysets and the
write endpoints enforce that rule themselves, so hiding a button is never the
only protection.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from .forms import AgencyForm
from .models import Agency, AgencyStaff

USER_ROLE_CHOICES = (
    ('admin', 'Administrator'),
    ('agency', 'Agency Staff'),
    ('staff', 'Management Staff'),
    ('ofw', 'OFW'),
)

ROLE_LABELS = dict(USER_ROLE_CHOICES)

USER_SORT_CHOICES = (
    ('joined', 'Newest account'),
    ('name', 'Name'),
    ('username', 'Username'),
    ('agency', 'Agency'),
)

USER_PER_PAGE = 10
AGENCY_PER_PAGE = 10


def _is_admin(user):
    """Only administrators (superusers) may manage accounts and agencies."""
    return user.is_superuser


def _can_touch(actor, target):
    """A non-superuser staff member must never modify a superuser account."""
    return actor.is_superuser or not target.is_superuser


def _write_audit(request, action, model_name, *, object_id='', object_repr='',
                 changes=None):
    """Record an account or agency change without blocking the request."""
    try:
        from apps.ofw.models import AuditLog

        AuditLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            action=action,
            model_name=model_name,
            object_id=str(object_id or ''),
            object_repr=str(object_repr or '')[:255],
            changes=json.dumps(changes or {}, default=str),
            ip_address=(
                request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                or request.META.get('REMOTE_ADDR')
                or None
            ),
        )
    except Exception:
        # Auditing must never break the action the user requested.
        pass


def _role_for_user(user):
    if user.is_superuser:
        return 'admin'
    if user.is_staff:
        return 'agency' if getattr(user, 'agency_staff', None) else 'staff'
    return 'ofw'


def _role_label(user):
    return ROLE_LABELS.get(_role_for_user(user), 'Account')


def _agency_name(user):
    staff = getattr(user, 'agency_staff', None)
    return staff.agency.name if staff and staff.agency else ''


def _user_queryset():
    return User.objects.select_related('agency_staff__agency')


def _filter_users(queryset, params):
    query = (params.get('q') or '').strip()
    if query:
        queryset = queryset.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(agency_staff__agency__name__icontains=query)
        )

    agency = (params.get('agency') or '').strip()
    if agency in ('none', 'unassigned'):
        queryset = queryset.filter(agency_staff__isnull=True)
    elif agency:
        try:
            agency_id = int(agency)
        except (TypeError, ValueError):
            pass
        else:
            # Agency staff belong through AgencyStaff, while an OFW account
            # belongs through the agency stored on their profile.
            queryset = queryset.filter(
                Q(agency_staff__agency_id=agency_id)
                | Q(ofw_profiles__agency_org_id=agency_id)
            )

    role = (params.get('role') or '').strip()
    if role == 'admin':
        queryset = queryset.filter(is_superuser=True)
    elif role == 'agency':
        queryset = queryset.filter(
            is_staff=True, is_superuser=False, agency_staff__isnull=False
        )
    elif role == 'staff':
        queryset = queryset.filter(
            is_staff=True, is_superuser=False, agency_staff__isnull=True
        )
    elif role == 'ofw':
        queryset = queryset.filter(is_staff=False, is_superuser=False)

    status = (params.get('status') or '').strip()
    if status == 'active':
        queryset = queryset.filter(is_active=True)
    elif status == 'inactive':
        queryset = queryset.filter(is_active=False)

    sort = (params.get('sort') or 'joined').strip()
    order = {
        'joined': ('-date_joined', '-id'),
        'name': ('first_name', 'last_name', 'username'),
        'username': ('username',),
        'agency': ('agency_staff__agency__name', 'first_name', 'last_name'),
    }.get(sort, ('-date_joined', '-id'))

    return queryset.distinct().order_by(*order)


def _role_tabs(params, summary):
    """Build the account-type tabs shown above the Users table.

    The tabs are a friendlier version of the role filter: they keep the other
    active filters (search, agency, status, sort) and only swap ``role``.
    """
    current = (params.get('role') or '').strip()
    tabs = (
        ('', 'All accounts', summary['accounts_total']),
        ('agency', 'Agency users', summary['agency_staff_total']),
        ('ofw', 'OFW accounts', summary['ofw_total']),
        ('staff', 'Management staff', summary['unassigned_staff_total']),
        ('admin', 'Administrators', summary['admin_total']),
    )
    result = []
    for value, label, count in tabs:
        query = params.copy()
        query.pop('page', None)
        if value:
            query['role'] = value
        else:
            query.pop('role', None)
        result.append({
            'value': value,
            'label': label,
            'count': count,
            'active': current == value,
            'querystring': query.urlencode(),
        })
    return result


def _filter_context(params, summary=None):
    querystring = params.copy()
    querystring.pop('page', None)
    return {
        'agencies': Agency.objects.order_by('name'),
        'role_choices': USER_ROLE_CHOICES,
        'sort_choices': USER_SORT_CHOICES,
        'query': (params.get('q') or '').strip(),
        'agency_filter': (params.get('agency') or '').strip(),
        'role_filter': (params.get('role') or '').strip(),
        'status_filter': (params.get('status') or '').strip(),
        'sort_filter': (params.get('sort') or 'joined').strip(),
        'querystring': querystring.urlencode(),
        'role_tabs': _role_tabs(params, summary) if summary else [],
    }


def _user_counts():
    staff = User.objects.filter(is_staff=True, is_superuser=False)
    return {
        'accounts_total': User.objects.count(),
        'agency_staff_total': staff.filter(
            agency_staff__isnull=False
        ).distinct().count(),
        'unassigned_staff_total': staff.filter(agency_staff__isnull=True).count(),
        'inactive_accounts_total': User.objects.filter(is_active=False).count(),
        'ofw_total': User.objects.filter(
            is_staff=False, is_superuser=False
        ).count(),
        'admin_total': User.objects.filter(is_superuser=True).count(),
    }


def _agency_base_queryset():
    return Agency.objects.annotate(
        ofw_count=Count('ofws', distinct=True),
        staff_count=Count('staff', distinct=True),
        active_staff_count=Count(
            'staff', filter=Q(staff__user__is_active=True), distinct=True
        ),
        inactive_staff_count=Count(
            'staff', filter=Q(staff__user__is_active=False), distinct=True
        ),
    )


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
def user_list_page(request):
    users_list = _filter_users(_user_queryset(), request.GET)

    paginator = Paginator(users_list, USER_PER_PAGE)
    users = paginator.get_page(request.GET.get('page', 1))

    summary = _user_counts()
    context = {
        'users': users,
        'summary': summary,
        **_filter_context(request.GET, summary),
    }
    return render(request, 'users/list.html', context)


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
def user_list_ajax(request):
    users_list = _filter_users(_user_queryset(), request.GET)
    paginator = Paginator(users_list, USER_PER_PAGE)
    users = paginator.get_page(request.GET.get('page', 1))

    data = [
        {
            'id': user.pk,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'is_staff': user.is_staff,
            'is_superuser': user.is_superuser,
            'is_active': user.is_active,
            'date_joined': user.date_joined.isoformat(),
            'agency_id': getattr(getattr(user, 'agency_staff', None), 'agency_id', None),
            'agency_name': _agency_name(user),
            'role': _role_for_user(user),
            'role_label': _role_label(user),
        }
        for user in users.object_list
    ]
    return JsonResponse({
        'data': data,
        'has_next': users.has_next(),
        'has_prev': users.has_previous(),
        'page': users.number,
        'pages': users.paginator.num_pages,
        'total': users.paginator.count,
    })


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
def user_get_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    if not _can_touch(request.user, user):
        return JsonResponse(
            {'error': 'You cannot manage a superuser account.'}, status=403
        )

    staff = getattr(user, 'agency_staff', None)
    return JsonResponse({
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'is_staff': user.is_staff,
        'is_active': user.is_active,
        'is_superuser': user.is_superuser,
        'agency': staff.agency_id if staff else '',
        'agency_name': staff.agency.name if staff else '',
        'role': _role_for_user(user),
        'role_label': _role_label(user),
    })


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
@require_POST
def user_save_ajax(request):
    user_id = request.POST.get('id')
    is_update = bool(user_id)

    if is_update:
        user = get_object_or_404(User, pk=user_id)
        if not _can_touch(request.user, user):
            return JsonResponse(
                {'error': 'You cannot manage a superuser account.'}, status=403
            )
    else:
        user = User()

    username = (request.POST.get('username') or '').strip()
    email = (request.POST.get('email') or '').strip()
    first_name = (request.POST.get('first_name') or '').strip()
    last_name = (request.POST.get('last_name') or '').strip()
    is_staff = request.POST.get('is_staff') == 'true'
    is_active = request.POST.get('is_active') == 'true'
    password = request.POST.get('password') or ''
    agency_raw = (request.POST.get('agency') or '').strip()

    if not username:
        return JsonResponse({'error': 'Username is required.'}, status=400)

    duplicate = User.objects.filter(username__iexact=username)
    if user_id:
        duplicate = duplicate.exclude(pk=user_id)
    if duplicate.exists():
        return JsonResponse(
            {'error': 'That username is already taken.'}, status=400
        )

    if email:
        duplicate_email = User.objects.filter(email__iexact=email)
        if user_id:
            duplicate_email = duplicate_email.exclude(pk=user_id)
        if duplicate_email.exists():
            return JsonResponse(
                {'error': 'That email is already in use.'}, status=400
            )

    if is_update and user.pk == request.user.pk and not is_active:
        return JsonResponse(
            {'error': 'You cannot deactivate your own account.'}, status=400
        )

    target_agency = None
    if agency_raw:
        target_agency = Agency.objects.filter(pk=agency_raw).first()
        if target_agency is None:
            return JsonResponse(
                {'error': 'Choose a valid agency from the list.'}, status=400
            )

    if not is_staff and target_agency is not None:
        return JsonResponse(
            {'error': 'An agency can only be assigned to a staff account.'},
            status=400,
        )

    # Superusers are global and must not be limited to one agency.
    if user.is_superuser:
        target_agency = None
        # Never strip the staff flag from a superuser through this screen;
        # administrator accounts are managed through Django's superuser tools.
        is_staff = True

    # A newly promoted staff account needs an agency so its records are
    # scoped.  Legacy unassigned staff can still be edited without one, but
    # the page shows a warning for them.
    becoming_staff = is_staff and not user.is_staff
    if (
        is_staff
        and not user.is_superuser
        and target_agency is None
        and (not is_update or becoming_staff)
    ):
        return JsonResponse({
            'error': (
                'Assign an agency to this staff account. Staff without an '
                'agency can see every agency\'s records.'
            )
        }, status=400)

    user.username = username
    user.first_name = first_name
    user.last_name = last_name
    user.email = email
    user.is_staff = is_staff
    user.is_active = is_active

    if password:
        try:
            validate_password(password, user=user)
        except ValidationError as exc:
            return JsonResponse(
                {'error': ' '.join(exc.messages)}, status=400
            )
        user.set_password(password)
    elif not is_update:
        return JsonResponse(
            {'error': 'Password is required for new users.'}, status=400
        )

    if is_update:
        previous = User.objects.get(pk=user.pk)
        before = {
            'username': previous.username,
            'first_name': previous.first_name,
            'last_name': previous.last_name,
            'email': previous.email,
            'is_staff': previous.is_staff,
            'is_active': previous.is_active,
            'agency': _agency_name(previous),
        }
    else:
        before = {
            'username': '',
            'first_name': '',
            'last_name': '',
            'email': '',
            'is_staff': False,
            'is_active': True,
            'agency': '',
        }

    try:
        user.save()
    except IntegrityError:
        return JsonResponse({
            'error': (
                'Could not save the account due to a duplicate username or '
                'email address.'
            )
        }, status=400)

    if user.is_superuser or not is_staff:
        AgencyStaff.objects.filter(user=user).delete()
    elif target_agency is not None:
        AgencyStaff.objects.update_or_create(
            user=user, defaults={'agency': target_agency}
        )
    else:
        AgencyStaff.objects.filter(user=user).delete()

    after = {
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'is_staff': user.is_staff,
        'is_active': user.is_active,
        'agency': _agency_name(user),
    }
    if password:
        before['password'] = 'unchanged'
        after['password'] = 'changed'

    if is_update:
        from apps.ofw.models import AuditLog

        changed = {
            key: {'from': before.get(key, ''), 'to': value}
            for key, value in after.items()
            if str(before.get(key, '')) != str(value)
        }
        if changed:
            _write_audit(
                request, AuditLog.Action.UPDATE, 'User',
                object_id=user.pk, object_repr=user.username, changes=changed,
            )
    else:
        from apps.ofw.models import AuditLog

        _write_audit(
            request, AuditLog.Action.CREATE, 'User',
            object_id=user.pk, object_repr=user.username, changes=after,
        )

    messages.success(
        request,
        f'User "{user.username}" has been '
        f'{"updated" if is_update else "saved"} successfully.',
    )

    staff = getattr(user, 'agency_staff', None)
    return JsonResponse({
        'status': 'success',
        'id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'email': user.email,
        'is_staff': user.is_staff,
        'is_active': user.is_active,
        'is_superuser': user.is_superuser,
        'agency': staff.agency_id if staff else '',
        'agency_name': staff.agency.name if staff else '',
        'role': _role_for_user(user),
        'role_label': _role_label(user),
    })


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
@require_POST
def user_delete_ajax(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.user == user:
        return JsonResponse({'error': 'You cannot delete yourself.'}, status=400)
    if not _can_touch(request.user, user):
        return JsonResponse(
            {'error': 'You cannot manage a superuser account.'}, status=403
        )

    linked = []
    if user.ofw_profiles.exists():
        linked.append('OFW profile')
    if user.welfare_assessments.exists():
        linked.append('welfare assessment')
    if user.checkins.exists():
        linked.append('check-in')
    if user.concerns.exists():
        linked.append('reported concern')
    if user.emergency_contacts.exists():
        linked.append('emergency contact')
    if user.monitoring_reports.exists():
        linked.append('monitoring report')
    if user.police_reports.exists():
        linked.append('police report')
    if user.acknowledged_alerts.exists():
        linked.append('emergency alert')
    if user.notifications.exists():
        linked.append('notification')
    if user.safe_location_suggestions.exists():
        linked.append('safe location suggestion')
    if user.reviewed_safe_location_suggestions.exists():
        linked.append('safe location review')

    if linked:
        return JsonResponse({
            'error': (
                'This account still has linked records ('
                + ', '.join(sorted(set(linked)))
                + '). Deactivate the account instead so the records are '
                'preserved.'
            )
        }, status=400)

    username = user.username
    from apps.ofw.models import AuditLog

    _write_audit(
        request, AuditLog.Action.DELETE, 'User',
        object_id=user.pk, object_repr=username,
        changes={'username': username},
    )
    user.delete()
    return JsonResponse({
        'status': 'deleted',
        'message': f'User "{username}" has been deleted successfully.',
    })


# ---------------------------------------------------------------------------
# Agency management
# ---------------------------------------------------------------------------


def _agency_status_tabs(params, summary):
    """Build the All / Active / Inactive tabs for the Agencies page."""
    current = (params.get('status') or '').strip()
    tabs = (
        ('', 'All agencies', summary['agencies_total']),
        ('active', 'Active', summary['agencies_active']),
        ('inactive', 'Inactive', summary['agencies_inactive']),
    )
    result = []
    for value, label, count in tabs:
        query = params.copy()
        query.pop('page', None)
        if value:
            query['status'] = value
        else:
            query.pop('status', None)
        result.append({
            'value': value,
            'label': label,
            'count': count,
            'active': current == value,
            'querystring': query.urlencode(),
        })
    return result


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
def agency_list_page(request):
    agencies = _agency_base_queryset()

    query = (request.GET.get('q') or '').strip()
    if query:
        agencies = agencies.filter(
            Q(name__icontains=query)
            | Q(slug__icontains=query)
            | Q(category__icontains=query)
            | Q(address__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )

    status = (request.GET.get('status') or '').strip()
    if status == 'active':
        agencies = agencies.filter(is_active=True)
    elif status == 'inactive':
        agencies = agencies.filter(is_active=False)

    sort = (request.GET.get('sort') or 'name').strip()
    order = {
        'name': ('name',),
        'ofw_count': ('-ofw_count', 'name'),
        'staff_count': ('-staff_count', 'name'),
        'created': ('-created_at',),
    }.get(sort, ('name',))

    agencies = agencies.order_by(*order)
    paginator = Paginator(agencies, AGENCY_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    params = request.GET.copy()
    params.pop('page', None)

    staff = User.objects.filter(is_staff=True, is_superuser=False)
    summary = {
        'agencies_total': Agency.objects.count(),
        'agencies_active': Agency.objects.filter(is_active=True).count(),
        'agencies_inactive': Agency.objects.filter(is_active=False).count(),
        'assigned_staff': staff.filter(
            agency_staff__isnull=False
        ).distinct().count(),
        'unassigned_staff': staff.filter(agency_staff__isnull=True).count(),
    }
    return render(request, 'users/agencies.html', {
        'page_obj': page_obj,
        'query': query,
        'status_filter': status,
        'sort_filter': sort,
        'querystring': params.urlencode(),
        'summary': summary,
        'status_tabs': _agency_status_tabs(params, summary),
        'page_title': 'Agencies',
        'page_pretitle': 'Administration',
    })


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
def agency_detail(request, pk):
    agency = get_object_or_404(Agency, pk=pk)

    ofws = agency.ofws.select_related('user').order_by(
        'last_name', 'first_name', 'id'
    )
    staff = AgencyStaff.objects.filter(agency=agency).select_related('user').order_by(
        'user__username'
    )

    from apps.ofw.models import (
        Concern,
        WELFARE_ATTENTION_STATUSES,
        WelfareStatus,
    )

    concern_qs = Concern.objects.filter(ofw__agency_org=agency)
    open_concerns = concern_qs.filter(
        status__in=['open', 'in_progress', 'escalated']
    ).count()
    resolved_concerns = concern_qs.filter(
        status__in=['resolved', 'closed']
    ).count()

    welfare_rows = ofws.values('welfare_status').annotate(total=Count('id'))
    welfare_counts = {row['welfare_status']: row['total'] for row in welfare_rows}
    welfare_labels = dict(WelfareStatus.choices)
    welfare_items = [
        {
            'key': key,
            'label': label,
            'value': welfare_counts.get(key, 0),
        }
        for key, label in WelfareStatus.choices
    ]

    welfare_badges = {
        'active': 'bg-success-lt text-success',
        'needs_support': 'bg-warning-lt text-warning',
        'distressed': 'bg-danger-lt text-danger',
        'repatriated': 'bg-secondary-lt text-secondary',
        'missing': 'bg-dark-lt text-dark',
    }
    concern_badges = {
        'open': 'bg-danger-lt text-danger',
        'in_progress': 'bg-warning-lt text-warning',
        'escalated': 'bg-orange-lt text-orange',
        'resolved': 'bg-success-lt text-success',
        'closed': 'bg-secondary-lt text-secondary',
    }

    context = {
        'agency': agency,
        'ofw_rows': [
            {
                'profile': profile,
                'badge': welfare_badges.get(
                    profile.welfare_status, 'bg-secondary-lt text-secondary'
                ),
            }
            for profile in ofws[:25]
        ],
        'ofw_count': ofws.count(),
        'staff': staff,
        'staff_count': staff.count(),
        'active_staff_count': staff.filter(user__is_active=True).count(),
        'inactive_staff_count': staff.filter(user__is_active=False).count(),
        'open_concerns': open_concerns,
        'resolved_concerns': resolved_concerns,
        'concern_count': concern_qs.count(),
        'attention_count': ofws.filter(
            welfare_status__in=WELFARE_ATTENTION_STATUSES
        ).count(),
        'welfare_items': welfare_items,
        'recent_concerns': [
            {
                'concern': concern,
                'badge': concern_badges.get(
                    concern.status, 'bg-secondary-lt text-secondary'
                ),
            }
            for concern in concern_qs.select_related('ofw').order_by(
                '-reported_date', '-id'
            )[:5]
        ],
        'page_title': agency.name,
        'page_pretitle': 'Agency details',
    }
    return render(request, 'users/agency_detail.html', context)


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
def agency_get_ajax(request, pk):
    agency = get_object_or_404(Agency, pk=pk)
    return JsonResponse({
        'id': agency.pk,
        'name': agency.name,
        'slug': agency.slug,
        'website': agency.website,
        'category': agency.category,
        'address': agency.address,
        'phone': agency.phone,
        'email': agency.email,
        'description': agency.description,
        'is_active': agency.is_active,
    })


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
@require_POST
def agency_save_ajax(request):
    record_id = request.POST.get('id')
    if record_id:
        agency = get_object_or_404(Agency, pk=record_id)
        is_update = True
    else:
        agency = Agency()
        is_update = False

    before = {
        'name': agency.name if is_update else '',
        'slug': agency.slug if is_update else '',
        'website': agency.website if is_update else '',
        'category': agency.category if is_update else '',
        'address': agency.address if is_update else '',
        'phone': agency.phone if is_update else '',
        'email': agency.email if is_update else '',
        'is_active': agency.is_active if is_update else True,
    }

    form = AgencyForm(request.POST, instance=agency)
    if not form.is_valid():
        errors = [message for messages_ in form.errors.values() for message in messages_]
        return JsonResponse({'error': ' '.join(errors)}, status=400)

    try:
        agency = form.save()
    except IntegrityError:
        return JsonResponse({
            'error': 'An agency with this name or URL name already exists.'
        }, status=400)

    from apps.ofw.models import AuditLog

    after = {
        'name': agency.name,
        'slug': agency.slug,
        'website': agency.website,
        'category': agency.category,
        'address': agency.address,
        'phone': agency.phone,
        'email': agency.email,
        'is_active': agency.is_active,
    }
    if is_update:
        changed = {
            key: {'from': before.get(key, ''), 'to': value}
            for key, value in after.items()
            if str(before.get(key, '')) != str(value)
        }
        if changed:
            _write_audit(
                request, AuditLog.Action.UPDATE, 'Agency',
                object_id=agency.pk, object_repr=agency.name, changes=changed,
            )
    else:
        _write_audit(
            request, AuditLog.Action.CREATE, 'Agency',
            object_id=agency.pk, object_repr=agency.name, changes=after,
        )

    messages.success(
        request,
        f'Agency "{agency.name}" has been '
        f'{"updated" if is_update else "created"} successfully.',
    )
    return JsonResponse({
        'status': 'success',
        'id': agency.pk,
        'name': agency.name,
        'is_active': agency.is_active,
    })


@login_required(login_url='login')
@user_passes_test(_is_admin, login_url='dashboard')
@require_POST
def agency_toggle_ajax(request, pk):
    agency = get_object_or_404(Agency, pk=pk)
    previous = agency.is_active
    agency.is_active = not agency.is_active
    agency.save(update_fields=['is_active'])

    from apps.ofw.models import AuditLog

    _write_audit(
        request, AuditLog.Action.UPDATE, 'Agency',
        object_id=agency.pk, object_repr=agency.name,
        changes={'is_active': {'from': previous, 'to': agency.is_active}},
    )
    state = 'activated' if agency.is_active else 'deactivated'
    messages.success(request, f'Agency "{agency.name}" has been {state}.')
    return JsonResponse({
        'status': 'success',
        'id': agency.pk,
        'is_active': agency.is_active,
        'state': state,
    })
