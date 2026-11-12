"""Views for the OFW monitoring and support information system."""

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import crud, osm_places
from .activity import refresh_activities_for_profiles
from .forms import (
    CheckInForm,
    ConcernForm,
    EmergencyContactForm,
    MonitoringReportForm,
    OFWProfileForm,
    WelfareAssessmentForm,
)
from .geo import reverse_geocode
from .hotlines import hotlines_for_country
from .locations import COUNTRY_GEO, canonical_country, cities_for_country
from .models import (
    AuditLog,
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyAlert,
    EmergencyContact,
    LocationTracker,
    MonitoringReport,
    Notification,
    OFWActivity,
    OFWLocationSharing,
    OFWProfile,
    PoliceReport,
    RiskLevel,
    SafeLocation,
    SafeLocationSuggestion,
    WelfareAssessment,
    WelfareStatus,
    WELFARE_ATTENTION_STATUSES,
    WELFARE_STALE_DAYS,
)
from .welfare import stale_cutoff
from .notifications import (
    mark_concern_read_by_management,
    notify,
    notify_managers,
)
from .ratelimit import rate_limit

_welfare_badge = {
    'active': 'bg-success-lt text-success',
    'needs_support': 'bg-warning-lt text-warning',
    'distressed': 'bg-danger-lt text-danger',
    'repatriated': 'bg-secondary-lt text-secondary',
    'missing': 'bg-dark-lt text-dark',
}

_risk_badge = {
    'low': 'bg-success-lt text-success',
    'medium': 'bg-warning-lt text-warning',
    'high': 'bg-orange-lt text-orange',
    'critical': 'bg-danger-lt text-danger',
}

_severity_badge = {
    'low': 'bg-success-lt text-success',
    'medium': 'bg-warning-lt text-warning',
    'high': 'bg-orange-lt text-orange',
    'critical': 'bg-danger-lt text-danger',
}

_concern_status_badge = {
    'open': 'bg-danger-lt text-danger',
    'in_progress': 'bg-warning-lt text-warning',
    'escalated': 'bg-orange-lt text-orange',
    'resolved': 'bg-success-lt text-success',
    'closed': 'bg-secondary-lt text-secondary',
}

_condition_badge = {
    'safe': 'bg-success-lt text-success',
    'needs_assistance': 'bg-warning-lt text-warning',
    'distressed': 'bg-danger-lt text-danger',
    'unreachable': 'bg-secondary-lt text-secondary',
}

_contact_type_badge = {
    'emergency': 'bg-red-lt text-red',
    'embassy': 'bg-azure-lt text-azure',
    'polo': 'bg-indigo-lt text-indigo',
    'owwa': 'bg-purple-lt text-purple',
    'dmw': 'bg-cyan-lt text-cyan',
    'police': 'bg-blue-lt text-blue',
    'fire': 'bg-orange-lt text-orange',
    'hospital': 'bg-red-lt text-red',
    'agency': 'bg-teal-lt text-teal',
    'employer': 'bg-orange-lt text-orange',
    'family': 'bg-green-lt text-green',
    'other': 'bg-secondary-lt text-secondary',
}

_contact_visibility_badge = {
    'national': 'bg-primary-lt text-primary',
    'local': 'bg-azure-lt text-azure',
    'private': 'bg-secondary-lt text-secondary',
    'unassigned': 'bg-warning-lt text-warning',
}

_report_status_badge = {
    'draft': 'bg-secondary-lt text-secondary',
    'submitted': 'bg-warning-lt text-warning',
    'approved': 'bg-success-lt text-success',
}


def _json_for_script(value):
    """Serialize data for a ``<script>`` block without allowing tag breakout."""
    return (
        json.dumps(value)
        .replace('<', '\\u003c')
        .replace('>', '\\u003e')
        .replace('&', '\\u0026')
    )


def _notify_assessment_saved(obj, created, actor, previous):
    recipient = obj.ofw.user
    if recipient is None or recipient.pk == actor.pk:
        return
    if not created and previous.get('status') == obj.status:
        return
    level = {
        WelfareStatus.DISTRESSED: Notification.Level.DANGER,
        WelfareStatus.NEEDS_SUPPORT: Notification.Level.WARNING,
        WelfareStatus.MISSING: Notification.Level.DANGER,
        WelfareStatus.ACTIVE: Notification.Level.SUCCESS,
        WelfareStatus.REPATRIATED: Notification.Level.INFO,
    }.get(obj.status, Notification.Level.INFO)
    notify(
        recipient,
        'Welfare status updated' if not created else 'New welfare assessment',
        f'Your welfare status is now "{obj.get_status_display()}" '
        f'(risk level: {obj.get_risk_level_display()}).',
        url=reverse('ofw:portal'),
        level=level,
    )


def _notify_checkin_saved(obj, created, actor, previous):
    recipient = obj.ofw.user
    if recipient is None or recipient.pk == actor.pk:
        return
    if not created and previous.get('condition') == obj.condition:
        return
    level = {
        CheckIn.Condition.SAFE: Notification.Level.SUCCESS,
        CheckIn.Condition.NEEDS_ASSISTANCE: Notification.Level.WARNING,
        CheckIn.Condition.DISTRESSED: Notification.Level.DANGER,
        CheckIn.Condition.UNREACHABLE: Notification.Level.WARNING,
    }.get(obj.condition, Notification.Level.INFO)
    message = (
        f'Management logged a check-in for you: {obj.get_condition_display()} '
        f'({obj.get_method_display()}).'
    )
    if obj.contact_person:
        message += f' Contact person: {obj.contact_person}.'
    notify(
        recipient,
        'New check-in recorded',
        message,
        url=reverse('ofw:portal_checkins'),
        level=level,
    )


def _notify_concern_saved(obj, created, actor, previous):
    recipient = obj.ofw.user
    if recipient is None or recipient.pk == actor.pk:
        return
    if created:
        notify(
            recipient,
            'Concern recorded',
            f'A concern has been recorded for you: "{obj.title}" '
            f'({obj.get_severity_display()} severity).',
            url=reverse('ofw:portal_concerns'),
            level=Notification.Level.WARNING,
        )
        return

    old_status = previous.get('status')
    if old_status == obj.status:
        return
    level = {
        Concern.Status.OPEN: Notification.Level.WARNING,
        Concern.Status.IN_PROGRESS: Notification.Level.INFO,
        Concern.Status.ESCALATED: Notification.Level.DANGER,
        Concern.Status.RESOLVED: Notification.Level.SUCCESS,
        Concern.Status.CLOSED: Notification.Level.INFO,
    }.get(obj.status, Notification.Level.INFO)
    notify(
        recipient,
        'Concern status updated',
        f'Your concern "{obj.title}" is now marked as '
        f'"{obj.get_status_display()}".',
        url=reverse('ofw:portal_concerns'),
        level=level,
    )


def _stale_profile_filter(_value):
    """Select profiles whose welfare status has not been reviewed recently."""
    return (
        Q(welfare_status_updated_at__lt=stale_cutoff())
        & ~Q(welfare_status=WelfareStatus.REPATRIATED)
    )


def _agency_choices(user):
    """Agency filter choices limited to the agencies the user may see."""
    from apps.users.agencies import agency_for_user
    from apps.users.models import Agency

    agencies = Agency.objects.order_by('name')
    if not user.is_superuser:
        agency = agency_for_user(user)
        agencies = agencies.filter(pk=agency.pk) if agency else agencies.none()
    return [
        (
            str(agency.pk),
            agency.name + ('' if agency.is_active else ' (inactive)'),
        )
        for agency in agencies
    ]


def _profile_filter_fields(request=None):
    """Agency choices for the global OFW list filter."""
    return [
        {
            'name': 'agency',
            'label': 'Agency',
            'choices': _agency_choices(request.user) if request else [],
        },
    ]


# The generic CRUD page renders a filter control for every entry below.  The
# matching query parameters are declared again in each ``make_crud`` call so the
# same rules also work from a URL or an export link.
_concern_filter_fields = [
    {'name': 'status', 'label': 'Status', 'choices': Concern.Status.choices},
    {'name': 'category', 'label': 'Category', 'choices': Concern.Category.choices},
    {'name': 'severity', 'label': 'Severity', 'choices': Concern.Severity.choices},
    {'name': 'date_from', 'label': 'Reported from', 'type': 'date'},
    {'name': 'date_to', 'label': 'Reported to', 'type': 'date'},
]

_assessment_filter_fields = [
    {'name': 'status', 'label': 'Status', 'choices': WelfareStatus.choices},
    {'name': 'risk_level', 'label': 'Risk level', 'choices': RiskLevel.choices},
    {'name': 'date_from', 'label': 'Assessed from', 'type': 'date'},
    {'name': 'date_to', 'label': 'Assessed to', 'type': 'date'},
]

_checkin_filter_fields = [
    {'name': 'condition', 'label': 'Condition', 'choices': CheckIn.Condition.choices},
    {'name': 'date_from', 'label': 'Check-in from', 'type': 'date'},
    {'name': 'date_to', 'label': 'Check-in to', 'type': 'date'},
]

_contact_filter_fields = [
    {
        'name': 'contact_type',
        'label': 'Contact type',
        'choices': EmergencyContact.ContactType.choices,
    },
]


def _report_filter_fields(request=None):
    """Agency choices for the reports list."""
    return [
        {
            'name': 'agency',
            'label': 'Agency',
            'choices': _agency_choices(request.user) if request else [],
        },
    ]


_profiles = crud.make_crud(
    model=OFWProfile,
    form_class=OFWProfileForm,
    columns=[
        {'field': 'profile_picture', 'label': 'Photo', 'type': 'image',
         'url_name': 'ofw:profile_detail'},
        {'field': 'full_name', 'label': 'Name', 'url_name': 'ofw:profile_detail'},
        {'field': 'passport_number', 'label': 'Passport'},
        {'field': 'age', 'label': 'Age'},
        {'field': 'country', 'label': 'Country'},
        {'field': 'agency_org', 'label': 'Agency'},
        {'field': 'employer_name', 'label': 'Employer'},
        {'field': 'occupation', 'label': 'Occupation'},
        {'field': 'get_welfare_status_display', 'label': 'Welfare Status',
         'badge': _welfare_badge, 'raw_field': 'welfare_status'},
    ],
    search_fields=['first_name', 'middle_name', 'last_name', 'suffix', 'passport_number', 'country',
                   'agency_org__name', 'employer_name', 'occupation'],
    order_by=['last_name', 'first_name'],
    title='OFW Profiles',
    entity='OFW profile',
    add_label='Add OFW',
    search_placeholder='Search by name, passport, country, or employer...',
    detail_url_name='ofw:profile_detail',
    filters={
        'welfare_status': ('welfare_status__in', crud.csv_list),
        'country': ('country__iexact', str),
        'stale': ('welfare_status_updated_at__lt', _stale_profile_filter),
        'agency': ('agency_org_id', int),
    },
    filter_fields=_profile_filter_fields,
)

_assessments = crud.make_crud(
    model=WelfareAssessment,
    form_class=WelfareAssessmentForm,
    columns=[
        {'field': 'ofw', 'label': 'OFW'},
        {'field': 'get_status_display', 'label': 'Status', 'badge': _welfare_badge,
         'raw_field': 'status'},
        {'field': 'get_risk_level_display', 'label': 'Risk Level', 'badge': _risk_badge,
         'raw_field': 'risk_level'},
        {'field': 'assessment_date', 'label': 'Assessment Date', 'type': 'date'},
        {'field': 'assessor', 'label': 'Assessor'},
    ],
    search_fields=['ofw__first_name', 'ofw__last_name', 'assessor'],
    title='Welfare Assessments',
    entity='Welfare assessment',
    add_label='Add Assessment',
    search_placeholder='Search by OFW or assessor...',
    filters={
        'status': ('status__in', crud.csv_list),
        'risk_level': ('risk_level__in', crud.csv_list),
        'date_from': ('assessment_date__gte', crud.date_value),
        'date_to': ('assessment_date__lte', crud.date_value),
    },
    filter_fields=_assessment_filter_fields,
    on_save=_notify_assessment_saved,
)

_checkins = crud.make_crud(
    model=CheckIn,
    form_class=CheckInForm,
    columns=[
        {'field': 'ofw', 'label': 'OFW'},
        {'field': 'checkin_date', 'label': 'Date & Time', 'type': 'datetime'},
        {'field': 'get_method_display', 'label': 'How'},
        {'field': 'contact_person', 'label': 'Contact person', 'truncate': 30},
        {'field': 'get_condition_display', 'label': 'Status', 'badge': _condition_badge,
         'raw_field': 'condition'},
        {'field': 'notes', 'label': 'Notes', 'truncate': 40},
    ],
    search_fields=['ofw__first_name', 'ofw__last_name', 'contact_person', 'notes'],
    title='Check-ins',
    entity='Check-in',
    add_label='Log Check-in',
    search_placeholder='Search by OFW, contact person, or notes...',
    detail_url_name='ofw:checkin_detail',
    filters={
        'condition': ('condition__in', crud.csv_list),
        'date_from': ('checkin_date__date__gte', crud.date_value),
        'date_to': ('checkin_date__date__lte', crud.date_value),
    },
    filter_fields=_checkin_filter_fields,
    on_save=_notify_checkin_saved,
)


def _concern_proof_cell(obj):
    """Compact photo/video indicator for the concern list."""
    proofs = list(obj.proofs.all())
    if not proofs:
        return '<span class="text-muted">—</span>'
    count = len(proofs)
    has_video = any(proof.is_video for proof in proofs)
    icon = 'fas fa-video' if has_video else 'fas fa-image'
    label = f'{count} proof file' + ('' if count == 1 else 's')
    return (
        f'<span class="text-nowrap text-muted" title="{label}">'
        f'<i class="{icon} me-1"></i>{count}</span>'
    )


_concerns = crud.make_crud(
    model=Concern,
    form_class=ConcernForm,
    columns=[
        {'field': 'title', 'label': 'Concern', 'url_name': 'ofw:concern_detail',
         'truncate': 60, 'nowrap': True,
         'meta_fields': ['get_category_display']},
        {'field': 'ofw', 'label': 'OFW', 'truncate': 22, 'nowrap': True},
        {'field': 'get_severity_display', 'label': 'Severity', 'badge': _severity_badge,
         'raw_field': 'severity', 'nowrap': True},
        {'field': 'get_status_display', 'label': 'Status', 'badge': _concern_status_badge,
         'raw_field': 'status', 'nowrap': True},
        {'field': 'proofs', 'label': 'Proof', 'render': _concern_proof_cell,
         'url_name': 'ofw:concern_detail'},
        {'field': 'reported_date', 'label': 'Reported', 'type': 'date',
         'nowrap': True},
    ],
    search_fields=['ofw__first_name', 'ofw__last_name', 'title', 'description'],
    title='Reported Concerns',
    entity='Concern',
    add_label='Report Concern',
    search_placeholder='Search by OFW or description...',
    detail_url_name='ofw:concern_detail',
    prefetch_related=['proofs'],
    show_index=False,
    page_help=[
        'Concerns are labelled automatically from the description (or the '
        'category when the description is empty), so staff no longer type a '
        'Title. The label is what OFWs see in their own portal. The second '
        'line under each label shows its category.',
    ],
    filters={
        'status': ('status__in', crud.csv_list),
        'category': ('category__in', crud.csv_list),
        'severity': ('severity__in', crud.csv_list),
        'date_from': ('reported_date__gte', crud.date_value),
        'date_to': ('reported_date__lte', crud.date_value),
    },
    filter_fields=_concern_filter_fields,
    on_save=_notify_concern_saved,
)

def _contact_row_actions(obj):
    """Call / Open-Website actions for an Emergency Contact row."""
    actions = []
    phone = (obj.phone or '').replace(' ', '')
    if phone:
        actions.append({
            'title': f'Emergency hotline call: {obj.phone}',
            'icon': 'fas fa-phone',
            'icon_class': 'text-success',
            'href': f'tel:{phone}',
            'target': None,
        })
    url = obj.website_url()
    if url:
        actions.append({
            'title': f'Open Website: {url}',
            'icon': 'fas fa-globe',
            'icon_class': 'text-primary',
            'href': url,
            'target': '_blank',
        })
    return actions


_contacts = crud.make_crud(
    model=EmergencyContact,
    form_class=EmergencyContactForm,
    columns=[
        {'field': 'name', 'label': 'Contact', 'truncate': 38, 'nowrap': True},
        {'field': 'owner_label', 'label': 'Owner', 'truncate': 26,
         'nowrap': True},
        {'field': 'type_label', 'label': 'Type', 'badge': _contact_type_badge,
         'raw_field': 'type_key'},
        {'field': 'location_label', 'label': 'Location', 'truncate': 30,
         'nowrap': True},
        {'field': 'visibility_label', 'label': 'Shown to OFWs',
         'badge': _contact_visibility_badge, 'raw_field': 'visibility'},
        {'field': 'phone', 'label': 'Phone', 'nowrap': True},
        {'field': 'email', 'label': 'Email', 'truncate': 30, 'nowrap': True},
    ],
    search_fields=['name', 'country', 'city', 'phone', 'email'],
    title='Emergency Contacts',
    entity='Emergency contact',
    add_label='Add Contact',
    search_placeholder='Search by name, country, city, or phone...',
    row_actions=_contact_row_actions,
    filters={'contact_type': ('contact_type__in', crud.csv_list)},
    filter_fields=_contact_filter_fields,
    allow_delete_all=False,
    page_help=[
        'Public hotlines (Emergency, Embassy, POLO, OWWA, DMW, Police, Fire, '
        'Hospital) appear in the OFW portal based on Country: Philippines = '
        'National Hotlines for everyone; any other country = Local Hotlines '
        'for OFWs deployed there.',
        'Private contacts (Family, Agency, Employer, Other) stay in this '
        'dashboard only. Attach a contact to a specific OFW so it appears in '
        'their own portal. Private contacts without an OFW owner are visible '
        'only to the agency that created them and to administrators.',
        'The "Shown to OFWs" badge tells you where each contact goes. '
        '"No country" means it is not visible to any OFW yet.',
    ],
)

_reports = crud.make_crud(
    model=MonitoringReport,
    form_class=MonitoringReportForm,
    columns=[
        {'field': 'title', 'label': 'Report Title'},
        {'field': 'agency', 'label': 'Agency'},
        {'field': 'get_report_type_display', 'label': 'Type'},
        {'field': 'period_start', 'label': 'From', 'type': 'date'},
        {'field': 'period_end', 'label': 'To', 'type': 'date'},
        {'field': 'country', 'label': 'Country'},
        {'field': 'get_status_display', 'label': 'Status', 'badge': _report_status_badge,
         'raw_field': 'status'},
    ],
    search_fields=['title', 'country', 'summary', 'agency__name'],
    title='Reports',
    entity='Report',
    add_label='Add Report',
    search_placeholder='Search by title, country, or agency...',
    filters={
        'status': ('status__in', crud.csv_list),
        'report_type': ('report_type__in', crud.csv_list),
        'agency': ('agency_id', int),
    },
    filter_fields=_report_filter_fields,
    page_help=[
        'Reports created by an agency account are automatically tagged with '
        'that agency and stay inside its workspace. Administrators see every '
        'agency and can filter by agency here.',
    ],
)


def profile_list_page(request):
    return _profiles['page'](request)


def profile_list_ajax(request):
    return _profiles['list_ajax'](request)


def profile_get_ajax(request, pk):
    return _profiles['get_ajax'](request, pk)


def profile_save_ajax(request):
    return _profiles['save_ajax'](request)


def profile_delete_ajax(request, pk):
    return _profiles['delete_ajax'](request, pk)


@login_required(login_url='login')
def profile_delete_all_ajax(request):
    return _profiles['delete_all_ajax'](request)


@rate_limit('export', 30, 60, methods=('GET',), as_json=False)
def profile_export_ajax(request):
    return _profiles['export_ajax'](request)


@login_required(login_url='login')
def profile_detail(request, pk):
    profile = get_object_or_404(crud._scoped(request.user, OFWProfile), pk=pk)
    assessments = profile.assessments.all()
    latest_assessment = assessments.first()
    welfare_mismatch = bool(
        latest_assessment is not None
        and latest_assessment.status != profile.welfare_status
    )
    context = {
        'profile': profile,
        'welfare_badge': _welfare_badge.get(profile.welfare_status, 'bg-secondary-lt text-secondary'),
        'assessments': assessments,
        'latest_assessment': latest_assessment,
        'welfare_mismatch': welfare_mismatch,
        'checkins': profile.checkins.all(),
        'concerns': profile.concerns.all(),
    }
    return render(request, 'ofw/profile_detail.html', context)


@login_required(login_url='login')
def checkin_detail(request, pk):
    checkin = get_object_or_404(crud._scoped(request.user, CheckIn), pk=pk)
    context = {
        'checkin': checkin,
        'condition_badge': _condition_badge.get(
            checkin.condition, 'bg-secondary-lt text-secondary'
        ),
    }
    return render(request, 'ofw/checkin_detail.html', context)


@login_required(login_url='login')
def concern_detail(request, pk):
    concern = get_object_or_404(crud._scoped(request.user, Concern), pk=pk)
    mark_concern_read_by_management(concern, request.user)

    context = {
        'concern': concern,
        'severity_badge': _severity_badge.get(
            concern.severity, 'bg-secondary-lt text-secondary'
        ),
        'status_badge': _concern_status_badge.get(
            concern.status, 'bg-secondary-lt text-secondary'
        ),
        'status_choices': Concern.Status.choices,
    }
    return render(request, 'ofw/concern_detail.html', context)


def _admin_only(request, message):
    if request.user.is_superuser:
        return None
    return JsonResponse({'error': message}, status=403)


@login_required(login_url='login')
@require_POST
def concern_proof_delete(request, pk):
    denied = _admin_only(request, 'Only administrators can delete proof files.')
    if denied:
        return denied

    proof = get_object_or_404(ConcernProof, pk=pk)
    label = proof.display_name
    if proof.file:
        proof.file.delete(save=False)
    proof.delete()
    messages.success(request, f'Proof file "{label}" has been deleted successfully.')
    return JsonResponse({'status': 'deleted'})


@login_required(login_url='login')
@require_POST
def concern_status_ajax(request, pk):
    """Transition a concern's status (management only)."""
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'Management accounts only.'}, status=403)
    concern = get_object_or_404(crud._scoped(request.user, Concern), pk=pk)
    new_status = (request.POST.get('status') or '').strip()
    valid = dict(Concern.Status.choices)
    if new_status not in valid:
        return JsonResponse({'error': 'Invalid status.'}, status=400)
    if concern.status == new_status:
        return JsonResponse({
            'status': 'ok',
            'status_display': concern.get_status_display(),
            'status_class': _concern_status_badge.get(
                concern.status, 'bg-secondary-lt text-secondary'
            ),
        })
    old_status = concern.status
    concern.status = new_status
    if new_status == Concern.Status.RESOLVED:
        if not concern.resolved_date:
            concern.resolved_date = timezone.localdate()
    else:
        # Reopening a concern must not leave a stale resolution date behind.
        concern.resolved_date = None
    concern.save(update_fields=['status', 'resolved_date', 'updated_at'])

    from .notifications import notify
    if new_status == Concern.Status.RESOLVED:
        # Notify the OFW who owns the concern, not the staff account that
        # happened to record it on their behalf.
        recipient = concern.ofw.user if concern.ofw_id else None
        if recipient is not None:
            notify(
                recipient,
                'Your concern has been resolved',
                f'Your concern "{concern.title}" has been marked as resolved '
                f'by your agency.',
                url=reverse('ofw:portal_concerns'),
                level=Notification.Level.SUCCESS,
            )
        notify_managers(
            f'Concern resolved: {concern.title}',
            f'{request.user.get_full_name() or request.user.username} marked '
            f'{concern.title} as resolved.',
            url=reverse('ofw:concern_list'),
            level=Notification.Level.SUCCESS,
            agency=concern.ofw.agency_org,
            exclude_user=request.user,
        )
    messages.success(
        request,
        f'Concern "{concern.title}" is now {concern.get_status_display()}.',
    )
    return JsonResponse({
        'status': 'ok',
        'status_display': concern.get_status_display(),
        'status_class': _concern_status_badge.get(
            concern.status, 'bg-secondary-lt text-secondary'
        ),
        'old_status': old_status,
    })


@login_required(login_url='login')
@require_POST
def police_report_status_ajax(request, pk):
    """Transition a police report's status (management only)."""
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'Management accounts only.'}, status=403)
    report = get_object_or_404(
        crud._scoped(request.user, PoliceReport), pk=pk
    )
    new_status = (request.POST.get('status') or '').strip()
    valid = dict(PoliceReport.Status.choices)
    if new_status not in valid:
        return JsonResponse({'error': 'Invalid status.'}, status=400)
    if report.status == new_status:
        return JsonResponse({
            'status': 'ok', 'status_display': report.get_status_display(),
        })
    old_status = report.status
    report.status = new_status
    update_fields = ['status', 'updated_at']
    if new_status == PoliceReport.Status.CLOSED:
        note = (request.POST.get('resolution_note') or '').strip()
        if note:
            report.resolution_note = note
            update_fields.append('resolution_note')
    report.save(update_fields=update_fields)

    from .notifications import notify, notify_managers
    if new_status == PoliceReport.Status.RESPONDED:
        notify(
            report.ofw.user,
            'Police have responded to your report',
            f'The police station recorded for your report (“{report.title}”) '
            f'has responded. Coordinate with your agency for next steps.',
            url=reverse('ofw:portal_police_reports'),
            level=Notification.Level.INFO,
        )
    elif new_status == PoliceReport.Status.CLOSED:
        notify(
            report.ofw.user,
            'Your police report has been closed',
            f'Your police report (“{report.title}”) has been closed by your '
            f'agency. Contact them if you need further help.',
            url=reverse('ofw:portal_police_reports'),
            level=Notification.Level.INFO,
        )
    notify_managers(
        f'Police report status changed: {report.title}',
        f'{request.user.get_full_name() or request.user.username} changed the '
        f'status of {report.title} to {report.get_status_display()}.',
        url=reverse('ofw:police_reports'),
        level=Notification.Level.INFO,
        agency=report.ofw.agency_org,
        exclude_user=request.user,
    )
    messages.success(
        request,
        f'Police report “{report.title}” is now {report.get_status_display()}.',
    )
    return JsonResponse({
        'status': 'ok',
        'status_display': report.get_status_display(),
        'old_status': old_status,
    })


def assessment_list_page(request):
    return _assessments['page'](request)


def assessment_list_ajax(request):
    return _assessments['list_ajax'](request)


def assessment_get_ajax(request, pk):
    return _assessments['get_ajax'](request, pk)


def assessment_save_ajax(request):
    return _assessments['save_ajax'](request)


def assessment_delete_ajax(request, pk):
    return _assessments['delete_ajax'](request, pk)


@login_required(login_url='login')
def assessment_delete_all_ajax(request):
    return _assessments['delete_all_ajax'](request)


@rate_limit('export', 30, 60, methods=('GET',), as_json=False)
def assessment_export_ajax(request):
    return _assessments['export_ajax'](request)


def checkin_list_page(request):
    return _checkins['page'](request)


def checkin_list_ajax(request):
    return _checkins['list_ajax'](request)


def checkin_get_ajax(request, pk):
    return _checkins['get_ajax'](request, pk)


def checkin_save_ajax(request):
    return _checkins['save_ajax'](request)


def checkin_delete_ajax(request, pk):
    return _checkins['delete_ajax'](request, pk)


@login_required(login_url='login')
def checkin_delete_all_ajax(request):
    return _checkins['delete_all_ajax'](request)


@rate_limit('export', 30, 60, methods=('GET',), as_json=False)
def checkin_export_ajax(request):
    return _checkins['export_ajax'](request)


def concern_list_page(request):
    return _concerns['page'](request)


def concern_list_ajax(request):
    return _concerns['list_ajax'](request)


def concern_get_ajax(request, pk):
    concern = get_object_or_404(crud._scoped(request.user, Concern), pk=pk)
    mark_concern_read_by_management(concern, request.user)
    return _concerns['get_ajax'](request, pk)


def concern_save_ajax(request):
    return _concerns['save_ajax'](request)


def concern_delete_ajax(request, pk):
    return _concerns['delete_ajax'](request, pk)


@login_required(login_url='login')
def concern_delete_all_ajax(request):
    return _concerns['delete_all_ajax'](request)


@rate_limit('export', 30, 60, methods=('GET',), as_json=False)
def concern_export_ajax(request):
    return _concerns['export_ajax'](request)


def contact_list_page(request):
    return _contacts['page'](request)


def contact_list_ajax(request):
    return _contacts['list_ajax'](request)


def contact_get_ajax(request, pk):
    return _contacts['get_ajax'](request, pk)


@login_required(login_url='login')
def contact_cities(request):
    """City suggestions for the country selected in the contact form."""
    country = (request.GET.get('country') or '').strip()
    return JsonResponse({'cities': cities_for_country(country)})


def contact_save_ajax(request):
    return _contacts['save_ajax'](request)


def contact_delete_ajax(request, pk):
    return _contacts['delete_ajax'](request, pk)


@login_required(login_url='login')
def contact_delete_all_ajax(request):
    return _contacts['delete_all_ajax'](request)


@rate_limit('export', 30, 60, methods=('GET',), as_json=False)
def contact_export_ajax(request):
    return _contacts['export_ajax'](request)


def report_list_page(request):
    return _reports['page'](request)


def report_list_ajax(request):
    return _reports['list_ajax'](request)


def report_get_ajax(request, pk):
    return _reports['get_ajax'](request, pk)


def report_save_ajax(request):
    return _reports['save_ajax'](request)


def report_delete_ajax(request, pk):
    return _reports['delete_ajax'](request, pk)


@login_required(login_url='login')
def report_delete_all_ajax(request):
    return _reports['delete_all_ajax'](request)


@rate_limit('export', 30, 60, methods=('GET',), as_json=False)
def report_export_ajax(request):
    return _reports['export_ajax'](request)


def dashboard_stats(user):
    """Aggregate monitoring metrics shown on the dashboard."""
    profiles = crud._scoped(user, OFWProfile)
    refresh_activities_for_profiles(profiles)
    checkins = crud._scoped(user, CheckIn)
    concerns = crud._scoped(user, Concern)
    contacts = crud._scoped(user, EmergencyContact)
    reports = crud._scoped(user, MonitoringReport)

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    at_risk = profiles.filter(welfare_status__in=WELFARE_ATTENTION_STATUSES)
    open_concerns = concerns.filter(status__in=['open', 'in_progress', 'escalated'])
    recent_ofws = profiles.select_related('user').order_by('-created_at', '-id')[:5]
    new_ofws_month = profiles.filter(created_at__gte=month_start).count()
    incomplete_profiles = profiles.filter(country='').count()

    # Inactive OFW accounts (no successful login for 3+ days)
    inactive_activities = OFWActivity.objects.filter(
        user__ofw_profiles__in=profiles,
        is_account_active=False,
        days_inactive__gte=OFWActivity.INACTIVE_THRESHOLD_DAYS,
    ).distinct()
    inactive_ofw_count = inactive_activities.count()
    inactive_3_5_count = inactive_activities.filter(days_inactive__lte=5).count()
    inactive_6_plus_count = inactive_activities.filter(days_inactive__gt=5).count()

    # Open emergency alerts
    open_alerts = EmergencyAlert.objects.filter(status=EmergencyAlert.Status.OPEN)
    if not user.is_superuser:
        from apps.users.agencies import agency_for_user
        agency = agency_for_user(user)
        if agency is not None:
            open_alerts = open_alerts.filter(ofw__agency_org=agency)
        else:
            open_alerts = open_alerts.none()
    open_alerts_count = open_alerts.count()

    welfare_rows = profiles.values('welfare_status').annotate(total=Count('id'))
    welfare_labels = dict(WelfareStatus.choices)
    welfare_counts = {row['welfare_status']: row['total'] for row in welfare_rows}
    welfare_chart = [
        {
            'key': row['welfare_status'],
            'label': welfare_labels.get(row['welfare_status'], row['welfare_status']),
            'value': row['total'],
        }
        for row in welfare_rows
    ] or [{'key': '', 'label': 'No data', 'value': 0}]

    # The dashboard groups the five stored values into three readable buckets so
    # managers do not compare a welfare level with a location or contact state.
    welfare_groups = [
        {
            'key': 'attention',
            'label': 'Needs attention',
            'value': sum(welfare_counts.get(k, 0) for k in WELFARE_ATTENTION_STATUSES),
            'filter': ','.join(WELFARE_ATTENTION_STATUSES),
            'items': [
                {
                    'key': key,
                    'label': welfare_labels[key],
                    'value': welfare_counts.get(key, 0),
                }
                for key in WELFARE_ATTENTION_STATUSES
            ],
        },
        {
            'key': WelfareStatus.ACTIVE,
            'label': welfare_labels[WelfareStatus.ACTIVE],
            'value': welfare_counts.get(WelfareStatus.ACTIVE, 0),
            'filter': WelfareStatus.ACTIVE,
            'items': [],
        },
        {
            'key': WelfareStatus.REPATRIATED,
            'label': welfare_labels[WelfareStatus.REPATRIATED],
            'value': welfare_counts.get(WelfareStatus.REPATRIATED, 0),
            'filter': WelfareStatus.REPATRIATED,
            'items': [],
        },
    ]

    stale_welfare_count = (
        profiles.exclude(welfare_status=WelfareStatus.REPATRIATED)
        .filter(welfare_status_updated_at__lt=stale_cutoff())
        .count()
    )

    category_labels = dict(Concern.Category.choices)
    category_rows = concerns.values('category').annotate(total=Count('id')).order_by('-total')[:6]
    concern_chart = [
        {'label': category_labels.get(row['category'], row['category']), 'value': row['total']}
        for row in category_rows
    ] or [{'label': 'No data', 'value': 0}]

    six_months_ago = month_start - timedelta(days=150)
    trend_rows = (
        checkins.filter(checkin_date__gte=six_months_ago)
        .values('checkin_date__year', 'checkin_date__month')
        .annotate(total=Count('id'))
        .order_by('checkin_date__year', 'checkin_date__month')
    )
    trend = [
        {
            'label': f"{row['checkin_date__year']}-{row['checkin_date__month']:02d}",
            'value': row['total'],
        }
        for row in trend_rows
    ] or [{'label': 'No data', 'value': 0}]

    # Deployment map: OFW counts per country of assignment, joined with the
    # known coordinates so the dashboard can shade and pin them on the world map.
    country_rows = (
        profiles.exclude(country='')
        .values('country')
        .annotate(total=Count('id'))
        .order_by('-total', 'country')
    )
    deployment_countries = []
    map_regions = {}
    map_markers = []
    for row in country_rows:
        country = row['country'].strip()
        count = row['total']
        geo = COUNTRY_GEO.get(country)
        deployment_countries.append({
            'country': country,
            'count': count,
            'link': reverse('ofw:profile_list') + '?' + urlencode({'country': country}),
        })
        if geo:
            iso2, lat, lng = geo
            map_regions[iso2] = count
            map_markers.append({
                'name': country,
                'lat': lat,
                'lng': lng,
                'count': count,
            })

    # One pin per OFW so the map shows exactly where each person is assigned.
    # People sharing a country are spread with a small deterministic offset so
    # their pins do not sit on top of one another.
    map_ofws = []
    seen_per_country = {}
    for profile in profiles.exclude(country='').order_by('country', 'last_name', 'first_name'):
        country = profile.country.strip()
        geo = COUNTRY_GEO.get(country)
        if not geo:
            continue
        iso2, lat, lng = geo
        slot = seen_per_country.get(country, 0)
        seen_per_country[country] = slot + 1
        if slot:
            ring = (slot + 1) // 2
            angle = (slot % 2 * 2 - 1) * (ring * 1.1)
            lat += (ring * 0.9) * (1 if slot % 2 else -1)
            lng += angle
        map_ofws.append({
            'name': profile.full_name,
            'country': country,
            'city': profile.city_abroad,
            'iso2': iso2,
            'lat': round(lat, 4),
            'lng': round(lng, 4),
            'status': profile.get_welfare_status_display(),
            'link': reverse('ofw:profile_detail', args=[profile.pk]),
        })

    country_links = {row['country']: row['link'] for row in deployment_countries}

    # Administrator-only overview: one row per agency so the dashboard answers
    # "which agency needs attention?" without opening each workspace.
    admin_overview = None
    if user.is_superuser:
        from django.contrib.auth import get_user_model

        from apps.users.models import Agency, AgencyStaff

        agency_rows = (
            Agency.objects.annotate(
                ofw_total=Count('ofws', distinct=True),
                staff_total=Count('staff', distinct=True),
                attention_total=Count(
                    'ofws',
                    filter=Q(
                        ofws__welfare_status__in=WELFARE_ATTENTION_STATUSES
                    ),
                    distinct=True,
                ),
                open_concern_total=Count(
                    'ofws__concerns',
                    filter=Q(
                        ofws__concerns__status__in=[
                            'open', 'in_progress', 'escalated',
                        ]
                    ),
                    distinct=True,
                ),
            ).order_by('-ofw_total', 'name')
        )
        admin_overview = {
            'agencies_total': Agency.objects.count(),
            'agencies_active': Agency.objects.filter(is_active=True).count(),
            'agency_users_total': AgencyStaff.objects.count(),
            'unassigned_staff_total': get_user_model().objects.filter(
                is_staff=True,
                is_superuser=False,
                agency_staff__isnull=True,
            ).count(),
            'resolved_concerns_total': concerns.filter(
                status__in=['resolved', 'closed']
            ).count(),
            'agency_rows': [
                {
                    'agency': row,
                    'ofw_total': row.ofw_total,
                    'staff_total': row.staff_total,
                    'attention_total': row.attention_total,
                    'open_concern_total': row.open_concern_total,
                    'url': reverse('users:agency_detail', args=[row.pk]),
                    'ofw_url': (
                        reverse('ofw:profile_list')
                        + '?'
                        + urlencode({'agency': row.pk})
                    ),
                }
                for row in agency_rows
            ],
        }

    return {
        'welfare_groups': welfare_groups,
        'welfare_stale_days': WELFARE_STALE_DAYS,
        'kpi': {
            'ofw_total': profiles.count(),
            'ofw_at_risk': at_risk.count(),
            'welfare_stale': stale_welfare_count,
            'checkins_month': checkins.filter(checkin_date__gte=month_start).count(),
            'open_concerns': open_concerns.count(),
            'contacts_total': contacts.count(),
            'reports_total': reports.count(),
            'inactive_ofws': inactive_ofw_count,
            'inactive_3_5_days': inactive_3_5_count,
            'inactive_6_plus_days': inactive_6_plus_count,
            'open_emergency_alerts': open_alerts_count,
        },
        'links': {
            'ofw_total': reverse('ofw:profile_list'),
            'ofw_at_risk': (
                reverse('ofw:profile_list')
                + '?welfare_status=' + ','.join(WELFARE_ATTENTION_STATUSES)
            ),
            'welfare_review': reverse('ofw:profile_list') + '?stale=1',
            'checkins_month': (
                reverse('ofw:checkin_list')
                + f'?date_from={month_start.date()}&date_to={timezone.localdate()}'
            ),
            'open_concerns': (
                reverse('ofw:concern_list')
                + '?status=open,in_progress,escalated'
            ),
            'contacts_total': reverse('ofw:contact_list'),
            'reports_total': reverse('ofw:report_list'),
            'welfare_status': reverse('ofw:profile_list'),
            'inactive_ofws': reverse('ofw:inactive_ofws'),
            'emergency_alerts': reverse('ofw:emergency_alerts'),
        },
        'recent_ofws': recent_ofws,
        'new_ofws_month': new_ofws_month,
        'incomplete_profiles': incomplete_profiles,
        'recent_checkins': checkins.select_related('ofw').order_by('-checkin_date')[:5],
        'recent_concerns': concerns.select_related('ofw').order_by('-reported_date')[:5],
        'welfare_chart': welfare_chart,
        'concern_chart': concern_chart,
        'trend_chart': trend,
        'risk_labels': dict(RiskLevel.choices),
        'deployment_countries': deployment_countries,
        'map_regions': map_regions,
        'map_markers': map_markers,
        'map_regions_json': _json_for_script(map_regions),
        'map_markers_json': _json_for_script(map_markers),
        'map_ofws_json': _json_for_script(map_ofws),
        'country_links_json': _json_for_script(country_links),
        'admin_overview': admin_overview,
    }


# ---------------------------------------------------------------------------
# Inactive OFW detection & emergency warning views (Admin / Agency)
# ---------------------------------------------------------------------------


def _management_scope(user):
    """Return OFWProfiles visible to this management user."""
    from apps.users.agencies import agency_for_user, has_agency_assignment

    if user.is_superuser:
        return OFWProfile.objects.all()
    agency = agency_for_user(user)
    if agency is not None:
        return OFWProfile.objects.filter(agency_org=agency)
    if user.is_staff and not has_agency_assignment(user):
        return OFWProfile.objects.all()
    return OFWProfile.objects.none()


def _management_alert_scope(user):
    """Return emergency alerts visible to this management account."""
    if not (user.is_superuser or user.is_staff):
        return EmergencyAlert.objects.none()
    return EmergencyAlert.objects.filter(ofw__in=_management_scope(user))


def _management_police_report_scope(user):
    """Return police reports visible to this management account."""
    if not (user.is_superuser or user.is_staff):
        return PoliceReport.objects.none()
    return PoliceReport.objects.filter(ofw__in=_management_scope(user))


@login_required(login_url='login')
def inactive_ofws_page(request):
    """List OFWs whose accounts have been inactive for 3+ days.

    Admin sees all; agency staff see only their agency's OFWs.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('dashboard')

    profiles = _management_scope(request.user).select_related('user', 'agency_org')
    refresh_activities_for_profiles(profiles)
    activities = OFWActivity.objects.select_related('user').filter(
        user__ofw_profiles__in=profiles
    ).distinct()
    activity_map = {a.user_id: a for a in activities}

    inactive_rows = []
    for profile in profiles:
        activity = activity_map.get(profile.user_id)
        if activity is None:
            continue
        if not activity.is_account_active and activity.days_inactive >= OFWActivity.INACTIVE_THRESHOLD_DAYS:
            inactive_rows.append({
                'profile': profile,
                'activity': activity,
                'user': profile.user,
                'age_band': '3–5 days' if activity.days_inactive <= 5 else '6+ days',
            })

    inactive_rows.sort(key=lambda r: r['activity'].days_inactive, reverse=True)

    return render(request, 'ofw/inactive_ofws.html', {
        'inactive_rows': inactive_rows,
        'offline_count': sum(
            1 for row in inactive_rows
            if row['activity'].offline_notice_active
        ),
        'page_title': 'Inactive OFWs',
        'page_pretitle': 'No login or portal activity for 3 or more days',
    })


@login_required(login_url='login')
def inactive_police_contacts_page(request):
    """Show the closest registered police station for inactive agency OFWs."""
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('dashboard')

    profiles_qs = _management_scope(request.user).select_related(
        'user', 'agency_org'
    )
    refresh_activities_for_profiles(profiles_qs)
    profiles = list(profiles_qs)
    activities = OFWActivity.objects.filter(
        user__ofw_profiles__in=profiles
    ).distinct()
    activity_by_user = {activity.user_id: activity for activity in activities}

    all_stations = list(SafeLocation.objects.filter(
        is_active=True,
        location_type=SafeLocation.LocationType.POLICE_STATION,
    ).order_by('country', 'city', 'name'))
    now = timezone.now()
    rows = []

    for profile in profiles:
        activity = activity_by_user.get(profile.user_id)
        if (
            activity is None
            or activity.is_account_active
            or activity.days_inactive < OFWActivity.INACTIVE_THRESHOLD_DAYS
        ):
            continue

        country = canonical_country(profile.country)
        country_stations = [
            station for station in all_stations
            if canonical_country(station.country).casefold() == country.casefold()
        ] if country else []
        city = (profile.city_abroad or '').strip()
        city_stations = [
            station for station in country_stations
            if city and station.city.strip().casefold() == city.casefold()
        ]
        latest_ping = profile.location_pings.order_by('-recorded_at').first()
        saved_area = ', '.join(
            part for part in (city, (profile.country or '').strip()) if part
        ) or 'Location not set in profile'
        if latest_ping is not None:
            geocoded = reverse_geocode(latest_ping.latitude, latest_ping.longitude)
            last_location_label = geocoded.get('label') or saved_area
            last_location_note = (
                'Area from the last GPS ping.' if geocoded.get('label')
                else 'GPS place name unavailable; showing the saved profile area.'
            )
        else:
            last_location_label = saved_area
            last_location_note = 'No GPS ping is on record; showing the saved profile area.'
        station_options = []
        station_note = ''

        if latest_ping is not None:
            nearest = nearest_safe_places(
                latest_ping.latitude,
                latest_ping.longitude,
                limit=3,
                locations=[station for station in country_stations if station.has_coords],
            )
            if nearest:
                for station in nearest:
                    phone = (station.get('phone') or '').strip()
                    station['tel'] = ''.join(
                        char for char in phone if char.isdigit() or char == '+'
                    )
                station_options = nearest
                station_note = 'Sorted by distance from the OFW\'s last recorded location.'

        if not station_options and city_stations:
            for station in city_stations[:3]:
                phone = (station.phone or '').strip()
                station_options.append({
                    'name': station.name,
                    'city': station.city,
                    'country': station.country,
                    'address': station.address,
                    'phone': phone,
                    'tel': ''.join(char for char in phone if char.isdigit() or char == '+'),
                    'distance_text': '',
                    'maps_url': '',
                })
            station_note = 'Matched by the OFW\'s saved city; exact distance is unavailable.'

        if not station_options:
            station_note = (
                'No registered police station matches this OFW\'s last known location. '
                'Add a police station in Safe Places with its phone and coordinates.'
            )

        ping_age_days = (
            max(0, (now - latest_ping.recorded_at).days)
            if latest_ping is not None else 0
        )
        rows.append({
            'profile': profile,
            'activity': activity,
            'latest_ping': latest_ping,
            'ping_age_days': ping_age_days,
            'last_location_label': last_location_label,
            'last_location_note': last_location_note,
            'station_options': station_options,
            'station_note': station_note,
        })

    rows.sort(key=lambda row: (-row['activity'].days_inactive, row['profile'].full_name.casefold()))
    return render(request, 'ofw/inactive_police_contacts.html', {
        'rows': rows,
        'page_title': 'Police Contact',
        'page_pretitle': 'Registered police stations near inactive OFWs',
    })


@login_required(login_url='login')
@require_POST
def request_ofw_location(request, pk):
    """Ask an OFW to share their location (consent-based)."""
    from django.utils.http import url_has_allowed_host_and_scheme

    profile = get_object_or_404(_management_scope(request.user), pk=pk)
    next_url = request.POST.get('next', '').strip()
    if not (
        next_url
        and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
    ):
        next_url = ''

    if profile.user is None:
        messages.error(request, 'This OFW has no linked login account.')
        return redirect(next_url or 'ofw:inactive_ofws')

    notify(
        profile.user,
        'Your agency is checking on you',
        'Please open Emergency SOS and tap Send My Location so we know you are safe.',
        url=reverse('ofw:portal_emergency_sos'),
        level=Notification.Level.WARNING,
    )
    messages.success(
        request,
        f'Location request sent to {profile.full_name}. They must allow it on their phone.',
    )
    return redirect(next_url or 'ofw:inactive_ofws')


@login_required(login_url='login')
def emergency_alerts_page(request):
    """List open emergency alerts for inactive or distressed OFWs."""
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('dashboard')

    from apps.users.agencies import agency_for_user

    alerts_qs = EmergencyAlert.objects.select_related('ofw__user', 'ofw__agency_org', 'acknowledged_by')

    if not request.user.is_superuser:
        agency = agency_for_user(request.user)
        if agency is not None:
            alerts_qs = alerts_qs.filter(ofw__agency_org=agency)
        else:
            alerts_qs = alerts_qs.none()

    status_filter = request.GET.get('status', 'open')
    if status_filter == 'open':
        alerts_qs = alerts_qs.filter(status=EmergencyAlert.Status.OPEN)
    elif status_filter == 'all':
        pass
    else:
        alerts_qs = alerts_qs.filter(status=status_filter)

    return render(request, 'ofw/emergency_alerts.html', {
        'alerts': alerts_qs.order_by('-created_at'),
        'status_filter': status_filter,
        'page_title': 'Emergency SOS Calls',
        'page_pretitle': 'OFW Emergency Calls to Agency',
    })


@login_required(login_url='login')
@require_POST
def acknowledge_alert(request, pk):
    """Mark an alert as acknowledged (management called the OFW)."""
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden('Management accounts only.')
    alert = get_object_or_404(_management_alert_scope(request.user), pk=pk)
    if alert.status != EmergencyAlert.Status.OPEN:
        messages.info(request, 'This emergency alert is no longer awaiting acknowledgment.')
        return redirect('ofw:emergency_alerts')
    alert.status = EmergencyAlert.Status.ACKNOWLEDGED
    alert.acknowledged_by = request.user
    alert.acknowledged_at = timezone.now()
    alert.save(update_fields=['status', 'acknowledged_by', 'acknowledged_at', 'updated_at'])

    notify(
        alert.ofw.user,
        'Your emergency has been acknowledged',
        f'Your agency acknowledged your emergency alert and is trying to '
        f'reach you. Keep your phone reachable and stay on the SOS page.',
        url=reverse('ofw:portal_emergency_sos'),
        level=Notification.Level.WARNING,
    )
    messages.success(
        request,
        f'Alert acknowledged for {alert.ofw.full_name}. The OFW has been notified.',
    )
    return redirect('ofw:emergency_alerts')


@login_required(login_url='login')
@require_POST
def escalate_to_police(request, pk):
    """Escalate an alert to a police report when the OFW does not respond."""
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden('Management accounts only.')
    alert = get_object_or_404(_management_alert_scope(request.user), pk=pk)

    if alert.status in (EmergencyAlert.Status.ESCALATED, EmergencyAlert.Status.RESOLVED):
        messages.info(request, 'This emergency alert has already been closed or escalated.')
        return redirect('ofw:emergency_alerts')

    # Create the police report
    report = PoliceReport.objects.create(
        ofw=alert.ofw,
        title=f'Missing / Unresponsive OFW — {alert.ofw.full_name}',
        description=(
            f'OFW {alert.ofw.full_name} has been inactive for '
            f'{getattr(getattr(alert.ofw, "ofw_activity", None), "days_inactive", 0)} days. '
            f'Management called but received no response. '
            f'Last known country: {alert.ofw.country or "not set"}, '
            f'city: {alert.ofw.city_abroad or "not set"}. '
            f'Employer: {alert.ofw.employer_name or "not set"}.'
        ),
        police_station='',
        police_contact='',
        status=PoliceReport.Status.DRAFT,
        reported_by=request.user,
    )

    alert.status = EmergencyAlert.Status.ESCALATED
    alert.escalated_to_police = True
    alert.police_report = report
    alert.save(update_fields=['status', 'escalated_to_police', 'police_report', 'updated_at'])

    activity = getattr(alert.ofw, 'ofw_activity', None)
    if activity:
        activity.escalated_to_police_at = timezone.now()
        activity.save(update_fields=['escalated_to_police_at', 'updated_at'])

    notify_managers(
        title=f'Escalated to Police: {alert.ofw.full_name}',
        message=(
            f'No response from OFW after inactivity warning. '
            f'A police report has been drafted for {alert.ofw.full_name}. '
            f'Review and submit to local police.'
        ),
        url=reverse('ofw:police_reports'),
        level=Notification.Level.DANGER,
        agency=alert.ofw.agency_org,
    )

    notify(
        alert.ofw.user,
        'Your case was escalated to the police',
        'Your agency could not reach you, so a police report was started. '
        'If you are safe, open Emergency SOS and cancel the alert or contact '
        'your agency immediately.',
        url=reverse('ofw:portal_emergency_sos'),
        level=Notification.Level.DANGER,
    )
    messages.success(
        request,
        f'Escalated {alert.ofw.full_name} to the police and notified the OFW.',
    )

    return redirect('ofw:police_reports')


@login_required(login_url='login')
@require_POST
def resolve_alert(request, pk):
    """Close an emergency alert once the OFW is confirmed safe."""
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden('Management accounts only.')
    alert = get_object_or_404(_management_alert_scope(request.user), pk=pk)

    if alert.status == EmergencyAlert.Status.RESOLVED:
        messages.info(request, 'This emergency alert is already resolved.')
        return redirect('ofw:emergency_alerts')

    alert.status = EmergencyAlert.Status.RESOLVED
    alert.message = (
        f'{alert.message}\n\nResolved by '
        f'{request.user.get_full_name() or request.user.username}: OFW confirmed safe.'
    )
    alert.save(update_fields=['status', 'message', 'updated_at'])

    notify(
        alert.ofw.user,
        'Your emergency alert was resolved',
        'Your agency confirmed you are safe and closed the emergency alert. '
        'You can still call them if you need help.',
        url=reverse('ofw:portal_emergency_alerts'),
        level=Notification.Level.SUCCESS,
    )
    notify_managers(
        title=f'Alert resolved: {alert.ofw.full_name}',
        message=(
            f'{request.user.get_full_name() or request.user.username} marked '
            f'{alert.ofw.full_name} as safe and closed the emergency alert.'
        ),
        url=reverse('ofw:emergency_alerts'),
        level=Notification.Level.SUCCESS,
        exclude_user=request.user,
        agency=alert.ofw.agency_org,
    )
    messages.success(
        request,
        f'Emergency alert for {alert.ofw.full_name} resolved. The OFW was notified.',
    )
    return redirect('ofw:emergency_alerts')


@login_required(login_url='login')
def police_reports_page(request):
    """List police reports for unresponsive OFWs."""
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('dashboard')

    from apps.users.agencies import agency_for_user

    reports_qs = PoliceReport.objects.select_related('ofw__user', 'reported_by')

    if not request.user.is_superuser:
        agency = agency_for_user(request.user)
        if agency is not None:
            reports_qs = reports_qs.filter(ofw__agency_org=agency)
        else:
            reports_qs = reports_qs.none()

    return render(request, 'ofw/police_reports.html', {
        'reports': reports_qs.order_by('-reported_at'),
        'status_choices': PoliceReport.Status.choices,
        'page_title': 'Police Escalation',
        'page_pretitle': 'Escalate Unresponsive OFWs to Police',
    })


@login_required(login_url='login')
@require_POST
def police_report_submit(request, pk):
    """Submit a drafted police report to local police."""
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden('Management accounts only.')
    report = get_object_or_404(_management_police_report_scope(request.user), pk=pk)
    if report.status != PoliceReport.Status.DRAFT:
        messages.info(request, 'Only draft police reports can be submitted.')
        return redirect('ofw:police_reports')
    report.status = PoliceReport.Status.SUBMITTED
    report.police_station = request.POST.get('police_station', '').strip()
    if not report.police_station:
        messages.error(request, 'Enter the police station before recording contact.')
        return redirect('ofw:police_reports')
    report.police_contact = request.POST.get('police_contact', '').strip()
    report.report_number = request.POST.get('report_number', '').strip()
    report.officer_name = request.POST.get('officer_name', '').strip()
    follow_up = request.POST.get('follow_up_on', '').strip()
    if follow_up:
        from django.utils.dateparse import parse_date

        report.follow_up_on = parse_date(follow_up)
    report.save(update_fields=[
        'status', 'police_station', 'police_contact', 'report_number',
        'officer_name', 'follow_up_on', 'updated_at',
    ])

    notify(
        report.ofw.user,
        'Police contact recorded for your report',
        f'Your agency recorded contact with {report.police_station}. '
        f'Case number: {report.report_number or "not provided"}. '
        f'This app does not transmit reports to the police.',
        url=reverse('ofw:portal_police_report_detail', args=[report.pk]),
        level=Notification.Level.INFO,
    )

    messages.success(
        request,
        f'Contact with {report.police_station} was recorded in KabayaniTrack. '
        'This app does not transmit the report to the police.',
    )
    return redirect('ofw:police_reports')


# ---------------------------------------------------------------------------
# Safe Locations (police stations, hospitals, embassies near OFW work areas)
# ---------------------------------------------------------------------------


@login_required(login_url='login')
def safe_locations_page(request):
    """List safe places near OFW deployment locations.

    Management accounts see the console list (scoped to their agency).  OFWs
    see every active safe place and the page sorts them by their live GPS
    position, so turning on location shows the nearest ones first.
    """
    from apps.users.agencies import agency_for_user
    from .roles import is_ofw

    near_me = is_ofw(request.user)

    locations = SafeLocation.objects.filter(is_active=True).order_by('country', 'city', 'name')

    if not near_me and not request.user.is_superuser:
        agency = agency_for_user(request.user)
        if agency is not None:
            # Only show safe locations in countries where this agency has OFWs.
            agency_countries = OFWProfile.objects.filter(
                agency_org=agency
            ).exclude(country='').values_list('country', flat=True).distinct()
            locations = locations.filter(country__in=agency_countries)
        else:
            locations = locations.none()

    country_filter = request.GET.get('country', '').strip()
    if country_filter:
        locations = locations.filter(country__iexact=country_filter)

    countries = SafeLocation.objects.filter(is_active=True).values_list('country', flat=True).distinct().order_by('country')

    # Staff-only coverage check: a country where the agency has OFWs but no
    # embassy / POLO / OWWA office is a real gap during an emergency. The
    # portal can only show what has been registered.
    coverage_gaps = []
    if not near_me:
        deployed = {
            canonical_country(country)
            for country in _management_scope(request.user)
            .exclude(country='')
            .values_list('country', flat=True)
            if canonical_country(country)
        }
        covered = {
            canonical_country(country)
            for country in SafeLocation.objects.filter(
                is_active=True,
                location_type__in=[
                    SafeLocation.LocationType.EMBASSY,
                    SafeLocation.LocationType.POLO,
                    SafeLocation.LocationType.OWWA,
                ],
            ).values_list('country', flat=True)
            if canonical_country(country)
        }
        coverage_gaps = sorted(deployed - covered)

    return render(request, 'ofw/safe_locations.html', {
        'locations': locations,
        'countries': countries,
        'country_filter': country_filter,
        'near_me': near_me,
        'coverage_gaps': coverage_gaps,
        'page_title': 'Safe Place Guide',
        'page_pretitle': 'Guide OFW to Nearest Safe Place',
    })


@login_required(login_url='login')
@require_POST
def safe_location_save(request):
    """Create or update a safe location entry."""
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('dashboard')

    loc_id = request.POST.get('id')
    if loc_id:
        location = get_object_or_404(SafeLocation, pk=loc_id)
    else:
        location = SafeLocation()

    location.name = request.POST.get('name', '').strip()
    location.location_type = request.POST.get('location_type', 'other')
    location.country = request.POST.get('country', '').strip()
    if location.location_type not in dict(SafeLocation.LocationType.choices):
        messages.error(request, 'Choose a valid safe-place type.')
        return redirect('ofw:safe_locations')
    if not location.name or not location.country:
        messages.error(request, 'A safe-place name and country are required.')
        return redirect('ofw:safe_locations')
    location.city = request.POST.get('city', '').strip()
    location.address = request.POST.get('address', '').strip()
    location.phone = request.POST.get('phone', '').strip()
    lat = request.POST.get('latitude', '').strip()
    lng = request.POST.get('longitude', '').strip()
    if bool(lat) != bool(lng):
        messages.error(request, 'Enter both coordinates, or leave both blank.')
        return redirect('ofw:safe_locations')
    if lat and lng:
        try:
            latitude, longitude = Decimal(lat), Decimal(lng)
        except InvalidOperation:
            messages.error(request, 'Enter valid latitude and longitude values.')
            return redirect('ofw:safe_locations')
        if not latitude.is_finite() or not longitude.is_finite():
            messages.error(request, 'Enter finite latitude and longitude values.')
            return redirect('ofw:safe_locations')
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            messages.error(request, 'Coordinates are outside valid ranges.')
            return redirect('ofw:safe_locations')
        location.latitude, location.longitude = latitude, longitude
    else:
        location.latitude = location.longitude = None
    location.is_active = request.POST.get('is_active') == 'on'
    location.save()

    return redirect('ofw:safe_locations')


@login_required(login_url='login')
@require_POST
def safe_location_delete(request, pk):
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden('Management accounts only.')
    location = get_object_or_404(SafeLocation, pk=pk)
    location.is_active = False
    location.save(update_fields=['is_active', 'updated_at'])
    return redirect('ofw:safe_locations')


# ---------------------------------------------------------------------------
# Location Tracker (OFW opt-in and SOS location pings)
# ---------------------------------------------------------------------------


@login_required(login_url='login')
def location_tracker_page(request):
    """Live map and list of every OFW and their latest shared location.

    Every OFW in the management scope appears once. OFWs who have never shared
    a location are still listed with a "No location" status, so management can
    call them or request a location instead of wondering whether they exist.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('dashboard')

    from apps.users.agencies import agency_for_user

    profiles = list(
        _management_scope(request.user).select_related('user', 'agency_org')
    )

    pings_qs = LocationTracker.objects.select_related(
        'ofw__user', 'ofw__agency_org'
    ).order_by('-recorded_at')

    if not request.user.is_superuser:
        agency = agency_for_user(request.user)
        if agency is not None:
            pings_qs = pings_qs.filter(ofw__agency_org=agency)

    emergency_only = request.GET.get('emergency') == '1'
    if emergency_only:
        pings_qs = pings_qs.filter(is_emergency=True)

    history = list(pings_qs[:400])

    latest_by_ofw = {}
    sharing_enabled = set(OFWLocationSharing.objects.filter(
        ofw__in=profiles,
        is_enabled=True,
    ).values_list('ofw_id', flat=True))
    now = timezone.now()
    for ping in history:
        if ping.ofw_id in latest_by_ofw:
            continue
        age_seconds = max(0, int((now - ping.recorded_at).total_seconds()))
        ping.age_seconds = age_seconds
        ping.age_minutes = age_seconds // 60
        if age_seconds <= 600:
            ping.freshness = 'live'
            ping.freshness_label = 'Live now'
        elif age_seconds <= 3600:
            ping.freshness = 'recent'
            ping.freshness_label = f'{age_seconds // 60} min ago'
        elif age_seconds <= 86400:
            ping.freshness = 'stale'
            ping.freshness_label = f'{age_seconds // 3600} hr ago'
        else:
            ping.freshness = 'old'
            ping.freshness_label = f'{age_seconds // 86400} day(s) ago'
        latest_by_ofw[ping.ofw_id] = ping

    rows = []
    for profile in profiles:
        ping = latest_by_ofw.get(profile.pk)
        if emergency_only and ping is None:
            continue
        rows.append({
            'profile': profile,
            'ping': ping,
            'is_emergency': bool(ping and ping.is_emergency),
            'freshness': ping.freshness if ping else 'none',
            'freshness_label': ping.freshness_label if ping else 'No location',
            'sharing_enabled': profile.pk in sharing_enabled,
        })

    # OFWs with a location first (newest first), then the rest alphabetically.
    rows.sort(key=lambda row: (
        row['ping'] is None,
        -(row['ping'].recorded_at.timestamp() if row['ping'] else 0),
        (row['profile'].full_name or '').lower(),
    ))

    located_rows = [row for row in rows if row['ping'] is not None]

    # Map setup: show every safe place (the dataset is small) and start at a
    # useful view instead of an empty world map. If any OFW has a ping the map
    # fits them; otherwise it opens on the first deployment country in scope.
    map_center = {'lat': 12.8797, 'lng': 121.7740, 'zoom': 4}
    if located_rows:
        first_ping = located_rows[0]['ping']
        map_center = {
            'lat': float(first_ping.latitude),
            'lng': float(first_ping.longitude),
            'zoom': 8,
        }
    else:
        for profile in profiles:
            country = canonical_country(profile.country or '')
            if country in COUNTRY_GEO:
                _iso2, lat, lng = COUNTRY_GEO[country]
                map_center = {'lat': float(lat), 'lng': float(lng), 'zoom': 6}
                break

    return render(request, 'ofw/location_tracker.html', {
        'rows': rows,
        'pings': history[:50],
        'located_rows': located_rows,
        'emergency_only': emergency_only,
        'map_places': safe_place_markers(),
        'map_center': map_center,
        'live_count': sum(1 for row in rows if row['freshness'] == 'live'),
        'no_location_count': sum(1 for row in rows if row['ping'] is None),
        'page_title': 'Live Location Map',
        'page_pretitle': 'Every OFW at a glance',
    })


@never_cache
def location_tracker_live(request):
    """JSON of latest location per OFW for the admin live map to poll."""
    # Always answer JSON (never a login redirect/HTML), so the map's fetch()
    # can show a useful message instead of a JSON parse failure.
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Login required.'}, status=401)
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'Management accounts only.'}, status=403)

    from apps.users.agencies import agency_for_user

    profiles = list(
        _management_scope(request.user).select_related('user', 'agency_org')
    )

    latest_qs = LocationTracker.objects.select_related(
        'ofw__user', 'ofw__agency_org'
    ).order_by('ofw_id', '-recorded_at')

    if not request.user.is_superuser:
        agency = agency_for_user(request.user)
        if agency is not None:
            latest_qs = latest_qs.filter(ofw__agency_org=agency)
        # Agency-less staff are already covered by _management_scope (all OFWs).

    if request.GET.get('emergency') == '1':
        latest_qs = latest_qs.filter(is_emergency=True)

    # Keep only the latest ping per OFW (Django doesn't have distinct on ofw_id easily,
    # so do it in Python from the ordered queryset).
    seen = set()
    results = []
    now = timezone.now()
    sharing = set(
        OFWLocationSharing.objects.filter(
            ofw__in=profiles, is_enabled=True
        ).values_list('ofw_id', flat=True)
    )
    for ping in latest_qs:
        if ping.ofw_id in seen:
            continue
        seen.add(ping.ofw_id)
        age_seconds = max(0, int((now - ping.recorded_at).total_seconds()))
        if age_seconds <= 600:
            freshness = 'live'
            freshness_label = 'Live now'
        elif age_seconds <= 3600:
            freshness = 'recent'
            freshness_label = f'{age_seconds // 60} min ago'
        elif age_seconds <= 86400:
            freshness = 'stale'
            freshness_label = f'{age_seconds // 3600} hr ago'
        else:
            freshness = 'old'
            freshness_label = f'{age_seconds // 86400} day(s) ago'
        results.append({
            'ofw_id': ping.ofw_id,
            'name': ping.ofw.full_name,
            'country': ping.ofw.country or '',
            'city': ping.ofw.city_abroad or '',
            'agency': ping.ofw.agency_org.name if ping.ofw.agency_org else '',
            'contact': ping.ofw.contact_number or '',
            'label': ping.location_label or '',
            'lat': float(ping.latitude),
            'lng': float(ping.longitude),
            'accuracy': ping.accuracy_meters,
            'recorded_at': ping.recorded_at.isoformat(),
            'age_seconds': age_seconds,
            'freshness': freshness,
            'freshness_label': freshness_label,
            'is_emergency': bool(ping.is_emergency),
            'sharing_enabled': ping.ofw_id in sharing,
        })

    live_count = sum(1 for row in results if row['freshness'] == 'live')
    waiting_count = len(sharing - seen)
    # Sharing is on but the last ping is older than the "live" window: the OFW
    # closed the browser or lost signal. The admin map shows this as paused
    # instead of pretending the marker is current.
    live_sharing = sum(
        1 for row in results
        if row['sharing_enabled'] and row['freshness'] == 'live'
    )
    paused_count = max(0, len(sharing) - live_sharing)
    return JsonResponse({
        'ofws': results,
        'live_count': live_count,
        'sharing_count': len(sharing),
        'waiting_count': waiting_count,
        'paused_count': paused_count,
    })


@login_required(login_url='login')
@require_POST
@rate_limit('location-ping', 40, 60)
def location_tracker_ping(request):
    """OFW or management submits a location ping during an emergency."""
    profile = OFWProfile.objects.filter(user=request.user).order_by('id').first()
    if profile is None:
        return JsonResponse({'error': 'No OFW profile found.'}, status=400)

    lat = request.POST.get('latitude', '').strip()
    lng = request.POST.get('longitude', '').strip()
    is_emergency = request.POST.get('is_emergency') == '1'
    accuracy = request.POST.get('accuracy', '').strip()

    if not lat or not lng:
        return JsonResponse({'error': 'Latitude and longitude are required.'}, status=400)

    try:
        latitude_value = Decimal(lat)
        longitude_value = Decimal(lng)
    except InvalidOperation:
        return JsonResponse({'error': 'Latitude and longitude must be valid numbers.'}, status=400)
    if not latitude_value.is_finite() or not longitude_value.is_finite():
        return JsonResponse({'error': 'Latitude and longitude must be finite numbers.'}, status=400)
    if not (-90 <= latitude_value <= 90 and -180 <= longitude_value <= 180):
        return JsonResponse({'error': 'Latitude or longitude is out of range.'}, status=400)

    try:
        accuracy_value = int(float(accuracy)) if accuracy else None
    except (TypeError, ValueError, OverflowError):
        return JsonResponse({'error': 'Accuracy must be a valid number.'}, status=400)
    if accuracy_value is not None and accuracy_value < 0:
        return JsonResponse({'error': 'Accuracy cannot be negative.'}, status=400)

    # Non-emergency (background) pings are only allowed while the OFW has
    # explicitly enabled live location sharing. Emergency SOS pings are
    # user-initiated taps, so they keep working even when sharing is off.
    if not is_emergency and not OFWLocationSharing.objects.filter(
        ofw=profile, is_enabled=True
    ).exists():
        return JsonResponse(
            {'error': 'Live location sharing is not enabled.'}, status=403
        )

    ping = LocationTracker.objects.create(
        ofw=profile,
        latitude=latitude_value,
        longitude=longitude_value,
        accuracy_meters=accuracy_value,
        is_emergency=is_emergency,
    )

    # Reverse-geocode for proof of where the OFW is (stored on the ping).
    try:
        from .geo import reverse_geocode
        geo = reverse_geocode(latitude_value, longitude_value)
        label = geo.get('label') or ''
        if label:
            ping.location_label = label
            ping.save(update_fields=['location_label'])
    except Exception:
        # Geocode failure must not block the ping.
        pass

    alert = None
    if is_emergency:
        nearest = nearest_safe_places(lat, lng, limit=1)
        hint = ''
        if nearest:
            place = nearest[0]
            hint = (
                f'Nearest safe place: {place["name"]} '
                f'({place["distance_text"]} {place["direction"]}) in '
                f'{place["city"] or place["country"]}. '
            )
        alert = profile.emergency_alerts.filter(
            status__in=[EmergencyAlert.Status.OPEN, EmergencyAlert.Status.ACKNOWLEDGED]
        ).order_by('-created_at').first()
        created = alert is None
        message = (
            f'{profile.full_name} sent an emergency location ping '
            f'(lat: {lat}, lng: {lng}). {hint}'
        )
        if created:
            alert = EmergencyAlert.objects.create(
                ofw=profile,
                title=f'Emergency SOS from {profile.full_name}',
                message=message,
                level=EmergencyAlert.Level.CRITICAL,
            )
        else:
            alert.level = EmergencyAlert.Level.CRITICAL
            alert.message = message
            alert.save(update_fields=['level', 'message', 'updated_at'])

        if created:
            notify_managers(
                title=f'Emergency SOS from {profile.full_name}',
                message=(
                    f'{profile.full_name} shared an emergency location. '
                    f'Nearest safe place: {hint or "not found; open the guide for options."}'
                ),
                url=reverse('ofw:emergency_guide', args=[profile.pk]),
                level=Notification.Level.DANGER,
                agency=profile.agency_org,
                exclude_user=request.user,
            )

    return JsonResponse({'status': 'ok', 'id': ping.pk, 'alert_id': alert.pk if alert else None})


_EMERGENCY_NUMBERS = {
    'Philippines': '911',
    'Hong Kong': '999',
    'Saudi Arabia': '999',
    'Kuwait': '112',
    'Qatar': '999',
    'United Arab Emirates': '999',
    'Switzerland': '112',
}


def safe_place_markers(locations=None, limit=300):
    """Serialize active safe places into the compact dicts Leaflet maps use.

    Kept small so the admin map and the OFW's own map can draw every place
    (the dataset is tiny) and then zoom to whichever ones are near the user.
    """
    if locations is None:
        locations = SafeLocation.objects.filter(is_active=True)

    markers = []
    for place in locations:
        if not place.has_coords:
            continue
        markers.append({
            'name': place.name,
            'type': place.get_location_type_display(),
            'type_key': place.location_type,
            'lat': float(place.latitude),
            'lng': float(place.longitude),
            'phone': place.phone,
            'address': place.address,
            'city': place.city,
            'country': place.country,
            'maps_url': (
                'https://www.google.com/maps/dir/?api=1&destination='
                f'{place.latitude},{place.longitude}'
            ),
        })
        if len(markers) >= limit:
            break
    return markers


def nearest_safe_places(lat, lng, limit=6, locations=None):
    """Return active safe places sorted by distance from a coordinate.

    Each row carries the prepared labels the templates and the live guide need,
    so the heavy maths stays on the server.
    """
    from .geo import (
        bearing_degrees,
        compass_direction,
        distance_km,
        format_distance,
        walking_minutes,
    )

    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        return []

    if locations is None:
        locations = SafeLocation.objects.filter(is_active=True)

    rows = []
    for place in locations:
        if not place.has_coords:
            continue
        place_lat = float(place.latitude)
        place_lng = float(place.longitude)
        km = distance_km(lat, lng, place_lat, place_lng)
        bearing = bearing_degrees(lat, lng, place_lat, place_lng)
        rows.append({
            'id': place.pk,
            'name': place.name,
            'type': place.get_location_type_display(),
            'type_key': place.location_type,
            'city': place.city,
            'country': place.country,
            'address': place.address,
            'phone': place.phone,
            'emergency_phone': _EMERGENCY_NUMBERS.get(
                canonical_country(place.country), ''
            ),
            'latitude': place_lat,
            'longitude': place_lng,
            'distance_km': round(km, 3),
            'distance_text': format_distance(km),
            'walking_minutes': walking_minutes(km),
            'bearing': round(bearing, 1),
            'direction': compass_direction(bearing),
            'maps_url': (
                'https://www.google.com/maps/dir/?api=1&destination='
                f'{place_lat},{place_lng}'
            ),
        })

    rows.sort(key=lambda row: (row['distance_km'], row['name'].lower()))
    if limit:
        rows = rows[:limit]
    return rows


@login_required(login_url='login')
def location_context(request):
    """Where am I, and which safe places are closest? (JSON for the portal)."""
    from .geo import reverse_geocode

    lat = request.GET.get('lat', '').strip()
    lng = request.GET.get('lng', '').strip()

    try:
        lat_value = float(lat)
        lng_value = float(lng)
    except (TypeError, ValueError):
        return JsonResponse(
            {'status': 'error', 'error': 'Valid lat and lng are required.'},
            status=400,
        )

    if not (-90 <= lat_value <= 90) or not (-180 <= lng_value <= 180):
        return JsonResponse(
            {'status': 'error', 'error': 'Coordinates are out of range.'},
            status=400,
        )

    here = reverse_geocode(lat_value, lng_value)
    nearest = nearest_safe_places(lat_value, lng_value, limit=8)

    # No registered place is close enough to be useful: fall back to live
    # OpenStreetMap data so the guide works anywhere in the world. Callers opt
    # in with ?live=1 so directories that only need registered places stay
    # fast and never wait on an external service.
    want_live = request.GET.get('live', '').lower() in ('1', 'true', 'yes')
    live_places = []
    if want_live and (not nearest or nearest[0]['distance_km'] > osm_places.LIVE_FALLBACK_KM):
        live_places = osm_places.nearby_safe_places(
            lat_value,
            lng_value,
            default_city=here.get('city') or '',
            default_country=here.get('country') or '',
        )

    return JsonResponse({
        'status': 'ok',
        'you_are_here': here.get('label') or '',
        'city': here.get('city') or '',
        'region': here.get('region') or '',
        'country': here.get('country') or '',
        'latitude': lat_value,
        'longitude': lng_value,
        'nearest': nearest,
        'live_places': live_places,
        'live_source': 'OpenStreetMap' if live_places else '',
        'live_fallback_km': osm_places.LIVE_FALLBACK_KM,
    })


@login_required(login_url='login')
def ofw_location_history(request, pk):
    """Location history for one OFW — proof of where they've been."""
    if not (request.user.is_superuser or request.user.is_staff):
        return JsonResponse({'error': 'Management accounts only.'}, status=403)

    from apps.users.agencies import agency_for_user

    profiles = _management_scope(request.user)
    profile = get_object_or_404(profiles, pk=pk)

    pings = (
        LocationTracker.objects
        .filter(ofw=profile)
        .order_by('-recorded_at')[:100]
    )

    now = timezone.now()
    results = []
    for ping in pings:
        age_seconds = max(0, int((now - ping.recorded_at).total_seconds()))
        if age_seconds <= 600:
            freshness = 'live'
            freshness_label = 'Live now'
        elif age_seconds <= 3600:
            freshness = 'recent'
            freshness_label = f'{age_seconds // 60} min ago'
        elif age_seconds <= 86400:
            freshness = 'stale'
            freshness_label = f'{age_seconds // 3600} hr ago'
        else:
            freshness = 'old'
            freshness_label = f'{age_seconds // 86400} day(s) ago'
        results.append({
            'id': ping.pk,
            'lat': float(ping.latitude),
            'lng': float(ping.longitude),
            'label': ping.location_label or '',
            'accuracy': ping.accuracy_meters,
            'recorded_at': ping.recorded_at.isoformat(),
            'recorded_at_display': ping.recorded_at.strftime('%b %d, %Y %H:%M'),
            'age_seconds': age_seconds,
            'freshness': freshness,
            'freshness_label': freshness_label,
            'is_emergency': bool(ping.is_emergency),
        })

    return JsonResponse({
        'ofw_id': profile.pk,
        'ofw_name': profile.full_name,
        'pings': results,
    })


@login_required(login_url='login')
def emergency_guide(request, pk):
    """Call guide: where the OFW was last seen and the safest places nearby."""
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('dashboard')

    profile = get_object_or_404(_management_scope(request.user), pk=pk)
    latest = profile.location_pings.order_by('-recorded_at').first()

    nearest = []
    if latest is not None:
        nearest = nearest_safe_places(
            latest.latitude, latest.longitude, limit=6
        )

    fallback_locations = []
    if not nearest:
        country = canonical_country(profile.country) if profile.country else ''
        fallback_qs = SafeLocation.objects.filter(is_active=True)
        if country:
            fallback_qs = fallback_qs.filter(country__iexact=country)
        fallback_locations = list(fallback_qs.order_by('city', 'name')[:6])

    alert = profile.emergency_alerts.filter(
        status__in=[EmergencyAlert.Status.OPEN, EmergencyAlert.Status.ACKNOWLEDGED]
    ).order_by('-created_at').first()

    age_seconds = None
    age_label = ''
    age_minutes = None
    freshness = 'old'
    is_live = False
    if latest is not None:
        age_seconds = max(0, int((timezone.now() - latest.recorded_at).total_seconds()))
        age_minutes = age_seconds // 60
        is_live = age_seconds <= 600
        if is_live:
            freshness = 'live'
            age_label = 'Live now'
        elif age_seconds <= 3600:
            freshness = 'recent'
            age_label = f'{age_minutes} min ago'
        elif age_seconds <= 86400:
            freshness = 'stale'
            age_label = f'{age_seconds // 3600} hr ago'
        else:
            freshness = 'old'
            age_label = f'{age_seconds // 86400} day(s) ago'

    from .hotlines import automatic_local_hotlines, philippine_national_hotlines
    local_hotlines = automatic_local_hotlines(profile.country)
    national_hotlines = philippine_national_hotlines()

    return render(request, 'ofw/emergency_guide.html', {
        'profile': profile,
        'latest_ping': latest,
        'nearest_places': nearest,
        'fallback_locations': fallback_locations,
        'alert': alert,
        'age_seconds': age_seconds,
        'age_label': age_label,
        'age_minutes': age_minutes,
        'freshness': freshness,
        'is_live': is_live,
        'local_hotlines': local_hotlines,
        'national_hotlines': national_hotlines,
        'page_title': f'Emergency Guide - {profile.full_name}',
        'page_pretitle': 'Call the OFW and guide them to the nearest safe place',
    })


# ---------------------------------------------------------------------------
# OFW Emergency SOS (portal side - safe places guidance)
# ---------------------------------------------------------------------------


@login_required(login_url='login')
def ofw_emergency_sos(request):
    """OFW emergency page: shows nearby safe places and one-tap emergency actions."""
    from .roles import is_ofw
    if not is_ofw(request.user):
        return redirect('dashboard')

    profile = OFWProfile.objects.filter(user=request.user).order_by('id').first()
    location_country = canonical_country(profile.country) if profile and profile.country else ''
    location_city = profile.city_abroad.strip() if profile and profile.city_abroad else ''

    # Safe locations near the OFW's country/city.  Fall back to the Philippines
    # (then to every registered place) so the SOS page always has something
    # useful to show while testing or before an agency registers local sites.
    all_locations = list(
        SafeLocation.objects.filter(is_active=True).order_by('location_type', 'name')
    )
    safe_locations = [
        loc for loc in all_locations
        if location_country and canonical_country(loc.country) == location_country
    ] if location_country else all_locations

    if location_city and safe_locations:
        city_lower = location_city.strip().lower()
        city_matches = [
            loc for loc in safe_locations if (loc.city or '').strip().lower() == city_lower
        ]
        country_wide = [loc for loc in safe_locations if not (loc.city or '').strip()]
        safe_locations = city_matches or country_wide or safe_locations

    if not safe_locations:
        safe_locations = [
            loc for loc in all_locations
            if canonical_country(loc.country) == 'Philippines'
        ] or all_locations

    safe_locations = safe_locations[:60]

    # Recent emergency location pings for this OFW
    recent_pings = LocationTracker.objects.filter(ofw=profile).order_by('-recorded_at')[:5]

    # Latest open emergency alert for this OFW (so they see management has been alerted)
    open_alert = (
        EmergencyAlert.objects
        .filter(
            ofw=profile,
            status__in=[
                EmergencyAlert.Status.OPEN,
                EmergencyAlert.Status.ACKNOWLEDGED,
                EmergencyAlert.Status.ESCALATED,
            ],
        )
        .order_by('-created_at')
        .first()
    )

    # Country-aware hotlines: database rows first, bundled fallback second.
    local_hotlines, national_hotlines = hotlines_for_country(location_country)
    emergency_phone = next(
        (
            contact.dial_number
            for contact in local_hotlines
            if getattr(contact, 'contact_type', '') == 'emergency'
        ),
        '',
    ) or _EMERGENCY_NUMBERS.get(location_country, '112')

    return render(request, 'ofw/portal/emergency_sos.html', {
        'profile': profile,
        'location_country': location_country,
        'location_city': location_city,
        'safe_locations': safe_locations,
        'recent_pings': recent_pings,
        'open_alert': open_alert,
        'can_cancel_alert': bool(
            open_alert and open_alert.status in (
                EmergencyAlert.Status.OPEN,
                EmergencyAlert.Status.ACKNOWLEDGED,
            )
        ),
        'agency_phone': (
            profile.agency_org.phone
            if profile and profile.agency_org_id and profile.agency_org.phone else ''
        ),
        'local_hotlines': local_hotlines,
        'national_hotlines': national_hotlines,
        'emergency_phone': emergency_phone,
        'page_title': 'Emergency SOS',
    })


@login_required(login_url='login')
@require_POST
def portal_sos_alert(request):
    """Create or refresh an emergency alert before location is available.

    The OFW's SOS button calls this first, so management is alerted even when
    GPS permission is denied or the device cannot get a fix.  The follow-up
    ping endpoint attaches coordinates to the same alert.
    """
    from .roles import is_ofw
    if not is_ofw(request.user):
        return JsonResponse({'error': 'OFW accounts only.'}, status=403)

    profile = OFWProfile.objects.filter(user=request.user).order_by('id').first()
    if profile is None:
        return JsonResponse({'error': 'No OFW profile found.'}, status=400)

    alert = (
        EmergencyAlert.objects
        .filter(
            ofw=profile,
            status__in=[
                EmergencyAlert.Status.OPEN,
                EmergencyAlert.Status.ACKNOWLEDGED,
            ],
        )
        .order_by('-created_at')
        .first()
    )
    created = alert is None
    message = (
        f'{profile.full_name} pressed the emergency SOS button. '
        f'Location is being requested from the device.'
    )
    if created:
        alert = EmergencyAlert.objects.create(
            ofw=profile,
            title=f'Emergency SOS from {profile.full_name}',
            message=message,
            level=EmergencyAlert.Level.CRITICAL,
        )
        notify_managers(
            title=f'Emergency SOS from {profile.full_name}',
            message=(
                f'{profile.full_name} pressed SOS. Call the OFW now and open '
                f'the emergency guide for their last known location.'
            ),
            url=reverse('ofw:emergency_guide', args=[profile.pk]),
            level=Notification.Level.DANGER,
            agency=profile.agency_org,
            exclude_user=request.user,
        )
    else:
        alert.level = EmergencyAlert.Level.CRITICAL
        alert.message = (
            f'{alert.message}\n\nSOS pressed again — '
            f'location is being requested from the device.'
        )
        alert.save(update_fields=['level', 'message', 'updated_at'])

    return JsonResponse({
        'status': 'ok',
        'alert_id': alert.pk,
        'created': created,
        'status_label': alert.get_status_display(),
    })


@login_required(login_url='login')
@require_POST
def cancel_sos(request):
    """OFW cancels their open emergency alert and tells management they are safe."""
    from .roles import is_ofw
    if not is_ofw(request.user):
        return redirect('dashboard')

    profile = OFWProfile.objects.filter(user=request.user).order_by('id').first()
    if profile is None:
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'error': 'No OFW profile found.'}, status=400)
        messages.error(request, 'Complete your profile before cancelling an alert.')
        return redirect('ofw:portal_profile')

    alert_id = (request.POST.get('alert_id') or '').strip()
    alerts = EmergencyAlert.objects.filter(
        ofw=profile,
        status__in=[
            EmergencyAlert.Status.OPEN,
            EmergencyAlert.Status.ACKNOWLEDGED,
        ],
    ).order_by('-created_at')
    if alert_id.isdigit():
        # The alerts list has one Cancel button per alert; without the id every
        # button cancelled the newest alert instead of the one that was clicked.
        alert = alerts.filter(pk=int(alert_id)).first()
    else:
        alert = alerts.first()
    if alert is None:
        if request.headers.get('Accept') == 'application/json':
            return JsonResponse({'error': 'No open emergency alert to cancel.'}, status=400)
        messages.info(request, 'There is no open emergency alert to cancel.')
        return redirect('ofw:portal_emergency_sos')

    alert.status = EmergencyAlert.Status.RESOLVED
    alert.message = (
        f'{alert.message}\n\nCancelled by OFW (false alarm / safe now) — '
        f'{profile.full_name}.'
    )
    alert.save(update_fields=['status', 'message', 'updated_at'])

    notify_managers(
        title=f'SOS cancelled: {profile.full_name} is safe',
        message=(
            f'{profile.full_name} cancelled their emergency alert and marked '
            f'themselves safe. No police escalation is needed.'
        ),
        url=reverse('ofw:emergency_guide', args=[profile.pk]),
        level=Notification.Level.SUCCESS,
        agency=profile.agency_org,
    )
    notify(
        request.user,
        'Emergency alert cancelled',
        f'You cancelled the open emergency alert for {profile.full_name}. '
        f'Your agency has been notified that you are safe.',
        url=reverse('ofw:portal_emergency_sos'),
        level=Notification.Level.INFO,
    )
    if request.headers.get('Accept') == 'application/json':
        return JsonResponse({'status': 'cancelled'})
    messages.success(request, 'Emergency alert cancelled. Your agency knows you are safe.')
    return redirect('ofw:portal_emergency_sos')


# ---------------------------------------------------------------------------
# Safe Location Suggestions (OFW-submitted, admin-approved)
# ---------------------------------------------------------------------------


@login_required(login_url='login')
def safe_location_suggestions_page(request):
    """List OFW-submitted safe place suggestions pending admin review.

    Admin sees all suggestions; agency staff see only their agency's OFWs'
    suggestions.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('dashboard')

    from apps.users.agencies import agency_for_user

    suggestions = SafeLocationSuggestion.objects.select_related(
        'submitted_by', 'reviewed_by'
    ).order_by('-created_at')

    if not request.user.is_superuser:
        agency = agency_for_user(request.user)
        if agency is not None:
            suggestions = suggestions.filter(
                submitted_by__ofw_profiles__agency_org=agency
            ).distinct()
        else:
            suggestions = suggestions.none()

    status_filter = request.GET.get('status', 'pending')
    if status_filter == 'all':
        pass
    else:
        suggestions = suggestions.filter(status=status_filter)

    return render(request, 'ofw/safe_location_suggestions.html', {
        'suggestions': suggestions,
        'status_filter': status_filter,
        'page_title': 'Safe Place Suggestions',
        'page_pretitle': 'Review OFW-submitted safe places',
    })


@login_required(login_url='login')
@require_POST
def safe_location_suggestion_approve(request, pk):
    """Approve a safe place suggestion and promote it to SafeLocation."""
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden('Management accounts only.')

    from apps.users.agencies import agency_for_user

    suggestion = get_object_or_404(
        SafeLocationSuggestion.objects.all(), pk=pk
    )

    # Agency staff can only approve suggestions from their own agency's OFWs.
    if not request.user.is_superuser:
        agency = agency_for_user(request.user)
        if agency is None:
            return HttpResponseForbidden('Agency assignment required.')
        if not suggestion.submitted_by.ofw_profiles.filter(
            agency_org=agency
        ).exists():
            return HttpResponseForbidden('Not your agency\'s suggestion.')

    if suggestion.status != SafeLocationSuggestion.Status.PENDING:
        messages.info(request, 'This suggestion has already been reviewed.')
        return redirect('ofw:safe_location_suggestions')

    location = SafeLocation.objects.create(
        name=suggestion.name,
        location_type=suggestion.location_type,
        country=suggestion.country,
        city=suggestion.city,
        address=suggestion.address,
        phone=suggestion.phone,
        latitude=suggestion.latitude,
        longitude=suggestion.longitude,
        is_active=True,
    )

    suggestion.status = SafeLocationSuggestion.Status.APPROVED
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save(update_fields=[
        'status', 'reviewed_by', 'reviewed_at', 'updated_at',
    ])

    notify(
        suggestion.submitted_by,
        'Safe place suggestion approved',
        f'Your suggested safe place "{location.name}" has been approved '
        f'and added to the Safe Places Near Me directory.',
        url=reverse('ofw:safe_locations'),
        level=Notification.Level.SUCCESS,
    )

    messages.success(
        request,
        f'Safe place "{location.name}" has been approved and added.'
    )
    return redirect('ofw:safe_location_suggestions')


@login_required(login_url='login')
@require_POST
def safe_location_suggestion_reject(request, pk):
    """Reject a safe place suggestion."""
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden('Management accounts only.')

    from apps.users.agencies import agency_for_user

    suggestion = get_object_or_404(
        SafeLocationSuggestion.objects.all(), pk=pk
    )

    if not request.user.is_superuser:
        agency = agency_for_user(request.user)
        if agency is None:
            return HttpResponseForbidden('Agency assignment required.')
        if not suggestion.submitted_by.ofw_profiles.filter(
            agency_org=agency
        ).exists():
            return HttpResponseForbidden('Not your agency\'s suggestion.')

    if suggestion.status != SafeLocationSuggestion.Status.PENDING:
        messages.info(request, 'This suggestion has already been reviewed.')
        return redirect('ofw:safe_location_suggestions')

    suggestion.status = SafeLocationSuggestion.Status.REJECTED
    suggestion.reviewed_by = request.user
    suggestion.reviewed_at = timezone.now()
    suggestion.save(update_fields=[
        'status', 'reviewed_by', 'reviewed_at', 'updated_at',
    ])

    notify(
        suggestion.submitted_by,
        'Safe place suggestion not approved',
        f'Your suggested safe place "{suggestion.name}" was not approved '
        f'by the management team.',
        url=reverse('ofw:portal_suggest_safe_place'),
        level=Notification.Level.INFO,
    )

    messages.info(
        request,
        f'Safe place suggestion "{suggestion.name}" has been rejected.'
    )
    return redirect('ofw:safe_location_suggestions')


# ---------------------------------------------------------------------------
# OFW Activity Log (inactive account detection + management oversight)
# ---------------------------------------------------------------------------


@login_required(login_url='login')
def ofw_activity_page(request):
    """List OFW account activity for management oversight.

    Admin sees all OFWs; agency staff see only their agency's OFWs.
    Shows login/activity timestamps and inactivity flags.
    """
    if not (request.user.is_superuser or request.user.is_staff):
        return redirect('dashboard')

    profiles = _management_scope(request.user).select_related('user')
    refresh_activities_for_profiles(profiles)
    activities = OFWActivity.objects.select_related('user').filter(
        user__ofw_profiles__in=profiles
    ).distinct().order_by('-last_login_at', '-updated_at')

    active_only = request.GET.get('active') == '1'
    inactive_only = request.GET.get('inactive') == '1'

    if active_only:
        activities = activities.filter(is_account_active=True)
    elif inactive_only:
        activities = activities.filter(is_account_active=False)

    return render(request, 'ofw/ofw_activity.html', {
        'activities': activities,
        'active_only': active_only,
        'inactive_only': inactive_only,
        'page_title': 'OFW Activity Log',
        'page_pretitle': 'OFW login and profile activity',
    })


@login_required(login_url='login')
def audit_log_page(request):
    """Administrator view of management actions recorded by the system."""
    if not request.user.is_superuser:
        return HttpResponseForbidden('Administrators only.')

    query = request.GET.get('q', '').strip()
    action = request.GET.get('action', '').strip()
    category = request.GET.get('category', '').strip()

    logs = AuditLog.objects.select_related('user')
    if action in AuditLog.Action.values:
        logs = logs.filter(action=action)
    if category == 'users':
        logs = logs.filter(model_name='User')
    elif category == 'agencies':
        logs = logs.filter(model_name='Agency')
    elif category == 'ofw':
        logs = logs.exclude(model_name__in=['User', 'Agency'])
    if query:
        logs = logs.filter(
            Q(object_repr__icontains=query)
            | Q(model_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
        )

    paginator = Paginator(logs, 25)
    page_obj = paginator.get_page(request.GET.get('page'))

    params = request.GET.copy()
    params.pop('page', None)

    category_counts = {
        '': AuditLog.objects.count(),
        'users': AuditLog.objects.filter(model_name='User').count(),
        'agencies': AuditLog.objects.filter(model_name='Agency').count(),
        'ofw': AuditLog.objects.exclude(
            model_name__in=['User', 'Agency']
        ).count(),
    }
    category_tabs = []
    for value, label in (
        ('', 'All entries'),
        ('users', 'User accounts'),
        ('agencies', 'Agencies'),
        ('ofw', 'OFW records'),
    ):
        tab_params = params.copy()
        if value:
            tab_params['category'] = value
        else:
            tab_params.pop('category', None)
        category_tabs.append({
            'value': value,
            'label': label,
            'count': category_counts[value],
            'active': category == value,
            'querystring': tab_params.urlencode(),
        })

    return render(request, 'ofw/audit_log.html', {
        'page_obj': page_obj,
        'query': query,
        'action': action,
        'category': category,
        'action_choices': AuditLog.Action.choices,
        'category_tabs': category_tabs,
        'querystring': params.urlencode(),
        'page_title': 'Audit Log',
        'page_pretitle': 'Administration',
    })


# ---------------------------------------------------------------------------
# All Activity feed (administrators)
# ---------------------------------------------------------------------------

ACTIVITY_PER_PAGE = 30
# The combined timeline merges two tables.  Each source contributes at most
# this many of its most recent rows, keeping the page fast while the
# per-source tabs still paginate through the complete history.
ACTIVITY_MERGE_LIMIT = 500

_ACTIVITY_LEVEL_BADGES = {
    Notification.Level.INFO: 'bg-azure-lt text-azure',
    Notification.Level.SUCCESS: 'bg-success-lt text-success',
    Notification.Level.WARNING: 'bg-warning-lt text-warning',
    Notification.Level.DANGER: 'bg-danger-lt text-danger',
}

_ACTIVITY_ACTION_BADGES = {
    AuditLog.Action.CREATE: 'bg-success-lt text-success',
    AuditLog.Action.UPDATE: 'bg-blue-lt text-blue',
    AuditLog.Action.DELETE: 'bg-danger-lt text-danger',
    AuditLog.Action.DELETE_ALL: 'bg-danger-lt text-danger',
    AuditLog.Action.EXPORT: 'bg-secondary-lt text-secondary',
}


def _activity_person(user):
    """Display name for a notification recipient or audit actor."""
    if user is None:
        return 'System'
    full_name = (user.get_full_name() or '').strip()
    return full_name or user.username


def _notification_activity_row(notification):
    return {
        'kind': 'notification',
        'when': notification.created_at,
        'title': notification.title,
        'detail': notification.message,
        'badge': notification.get_level_display(),
        'badge_class': _ACTIVITY_LEVEL_BADGES.get(
            notification.level, 'bg-secondary-lt text-secondary'
        ),
        'person_label': 'To',
        'person': _activity_person(notification.recipient),
        'url': notification.url,
        'is_unread': not notification.is_read,
    }


def _audit_activity_row(log):
    detail = ' · '.join(
        part for part in (log.model_name, log.change_summary()) if part
    )
    return {
        'kind': 'audit',
        'when': log.created_at,
        'title': log.object_repr or log.model_name or str(log),
        'detail': detail,
        'badge': log.get_action_display(),
        'badge_class': _ACTIVITY_ACTION_BADGES.get(
            log.action, 'bg-secondary-lt text-secondary'
        ),
        'person_label': 'By',
        'person': _activity_person(log.user),
        'url': '',
        'is_unread': False,
    }


@login_required(login_url='login')
def all_activity_page(request):
    """Administrator timeline of every notification and management action.

    The notification bell stays focused on each account's own alerts.  This
    page gives administrators one place to see all system activity, including
    routine events that were intentionally kept inside an agency.
    """
    if not request.user.is_superuser:
        return HttpResponseForbidden('Administrators only.')

    source = (request.GET.get('source') or 'all').strip()
    if source not in ('all', 'notifications', 'audit'):
        source = 'all'
    query = (request.GET.get('q') or '').strip()
    level = (request.GET.get('level') or '').strip()
    if level not in Notification.Level.values:
        level = ''

    notifications_qs = Notification.objects.select_related(
        'recipient'
    ).order_by('-created_at', '-id')
    if level:
        notifications_qs = notifications_qs.filter(level=level)
    if query:
        notifications_qs = notifications_qs.filter(
            Q(title__icontains=query)
            | Q(message__icontains=query)
            | Q(recipient__username__icontains=query)
            | Q(recipient__first_name__icontains=query)
            | Q(recipient__last_name__icontains=query)
        )

    audit_qs = AuditLog.objects.select_related('user').order_by(
        '-created_at', '-id'
    )
    if query:
        audit_qs = audit_qs.filter(
            Q(object_repr__icontains=query)
            | Q(model_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
        )

    notification_count = notifications_qs.count()
    audit_count = audit_qs.count()

    truncated = False
    if source == 'notifications':
        paginator = Paginator(notifications_qs, ACTIVITY_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get('page'))
        rows = [
            _notification_activity_row(item)
            for item in page_obj.object_list
        ]
    elif source == 'audit':
        paginator = Paginator(audit_qs, ACTIVITY_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get('page'))
        rows = [_audit_activity_row(item) for item in page_obj.object_list]
    else:
        truncated = (
            notification_count > ACTIVITY_MERGE_LIMIT
            or audit_count > ACTIVITY_MERGE_LIMIT
        )
        rows = [
            _notification_activity_row(item)
            for item in notifications_qs[:ACTIVITY_MERGE_LIMIT]
        ] + [
            _audit_activity_row(item)
            for item in audit_qs[:ACTIVITY_MERGE_LIMIT]
        ]
        rows.sort(key=lambda row: row['when'], reverse=True)
        paginator = Paginator(rows, ACTIVITY_PER_PAGE)
        page_obj = paginator.get_page(request.GET.get('page'))
        rows = list(page_obj.object_list)

    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    source_counts = {
        'all': notification_count + audit_count,
        'notifications': notification_count,
        'audit': audit_count,
    }
    source_tabs = []
    for value, label in (
        ('all', 'All activity'),
        ('notifications', 'Notifications'),
        ('audit', 'Management actions'),
    ):
        tab_params = params.copy()
        if value == 'all':
            tab_params.pop('source', None)
        else:
            tab_params['source'] = value
        source_tabs.append({
            'value': value,
            'label': label,
            'count': source_counts[value],
            'active': source == value,
            'querystring': tab_params.urlencode(),
        })

    return render(request, 'ofw/all_activity.html', {
        'page_obj': page_obj,
        'rows': rows,
        'query': query,
        'level': level,
        'source': source,
        'source_tabs': source_tabs,
        'level_choices': Notification.Level.choices,
        'querystring': querystring,
        'truncated': truncated,
        'merge_limit': ACTIVITY_MERGE_LIMIT,
        'page_title': 'All Activity',
        'page_pretitle': 'Administration',
    })
