"""Views for the OFW monitoring and support information system."""

import json
from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import crud
from .forms import (
    CheckInForm,
    ConcernForm,
    EmergencyContactForm,
    MonitoringReportForm,
    OFWProfileForm,
    WelfareAssessmentForm,
)
from .locations import COUNTRY_GEO
from .models import (
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyContact,
    MonitoringReport,
    Notification,
    OFWProfile,
    RiskLevel,
    WelfareAssessment,
    WelfareStatus,
)
from .notifications import mark_concern_read_by_management, notify

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

_report_status_badge = {
    'draft': 'bg-secondary-lt text-secondary',
    'submitted': 'bg-warning-lt text-warning',
    'approved': 'bg-success-lt text-success',
}


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


_profiles = crud.make_crud(
    model=OFWProfile,
    form_class=OFWProfileForm,
    columns=[
        {'field': 'full_name', 'label': 'Name', 'url_name': 'ofw:profile_detail'},
        {'field': 'passport_number', 'label': 'Passport'},
        {'field': 'age', 'label': 'Age'},
        {'field': 'country', 'label': 'Country'},
        {'field': 'employer_name', 'label': 'Employer'},
        {'field': 'occupation', 'label': 'Occupation'},
        {'field': 'get_welfare_status_display', 'label': 'Welfare Status',
         'badge': _welfare_badge, 'raw_field': 'welfare_status'},
    ],
    search_fields=['first_name', 'last_name', 'passport_number', 'country',
                   'employer_name', 'occupation'],
    order_by=['last_name', 'first_name'],
    title='OFW Profiles',
    entity='OFW profile',
    add_label='Add OFW',
    search_placeholder='Search by name, passport, country, or employer...',
    detail_url_name='ofw:profile_detail',
    filters={
        'welfare_status': ('welfare_status__in', crud.csv_list),
        'country': ('country__iexact', str),
    },
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
    title='Welfare Status',
    entity='Welfare assessment',
    add_label='Add Assessment',
    search_placeholder='Search by OFW or assessor...',
    filters={
        'status': ('status__in', crud.csv_list),
        'risk_level': ('risk_level__in', crud.csv_list),
    },
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
        'date_from': ('checkin_date__date__gte', str),
        'date_to': ('checkin_date__date__lte', str),
    },
    on_save=_notify_checkin_saved,
)

_concerns = crud.make_crud(
    model=Concern,
    form_class=ConcernForm,
    columns=[
        {'field': 'ofw', 'label': 'OFW'},
        {'field': 'title', 'label': 'Concern', 'url_name': 'ofw:concern_detail'},
        {'field': 'description', 'label': 'Description', 'truncate': 50},
        {'field': 'get_category_display', 'label': 'Category'},
        {'field': 'get_severity_display', 'label': 'Severity', 'badge': _severity_badge,
         'raw_field': 'severity'},
        {'field': 'get_status_display', 'label': 'Status', 'badge': _concern_status_badge,
         'raw_field': 'status'},
        {'field': 'reported_date', 'label': 'Reported', 'type': 'date'},
    ],
    search_fields=['ofw__first_name', 'ofw__last_name', 'title', 'description'],
    title='Reported Concerns',
    entity='Concern',
    add_label='Report Concern',
    search_placeholder='Search by OFW, title, or description...',
    detail_url_name='ofw:concern_detail',
    filters={
        'status': ('status__in', crud.csv_list),
        'category': ('category__in', crud.csv_list),
        'severity': ('severity__in', crud.csv_list),
        'date_from': ('reported_date__gte', str),
        'date_to': ('reported_date__lte', str),
    },
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
        {'field': 'name', 'label': 'Contact'},
        {'field': 'get_contact_type_display', 'label': 'Type', 'badge': _contact_type_badge,
         'raw_field': 'contact_type'},
        {'field': 'country', 'label': 'Country'},
        {'field': 'city', 'label': 'City'},
        {'field': 'phone', 'label': 'Phone'},
        {'field': 'email', 'label': 'Email'},
    ],
    search_fields=['name', 'country', 'city', 'phone', 'email'],
    title='Emergency Contacts',
    entity='Emergency contact',
    add_label='Add Contact',
    search_placeholder='Search by name, country, city, or phone...',
    row_actions=_contact_row_actions,
    filters={'contact_type': ('contact_type__in', crud.csv_list)},
)

_reports = crud.make_crud(
    model=MonitoringReport,
    form_class=MonitoringReportForm,
    columns=[
        {'field': 'title', 'label': 'Report Title'},
        {'field': 'get_report_type_display', 'label': 'Type'},
        {'field': 'period_start', 'label': 'From', 'type': 'date'},
        {'field': 'period_end', 'label': 'To', 'type': 'date'},
        {'field': 'country', 'label': 'Country'},
        {'field': 'get_status_display', 'label': 'Status', 'badge': _report_status_badge,
         'raw_field': 'status'},
    ],
    search_fields=['title', 'country', 'summary'],
    title='Reports',
    entity='Report',
    add_label='Add Report',
    search_placeholder='Search by title or country...',
    filters={
        'status': ('status__in', crud.csv_list),
        'report_type': ('report_type__in', crud.csv_list),
    },
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


@login_required(login_url='login')
def profile_detail(request, pk):
    queryset = (
        OFWProfile.objects.all()
        if request.user.is_superuser or request.user.is_staff
        else OFWProfile.objects.filter(user=request.user)
    )
    profile = get_object_or_404(queryset, pk=pk)
    context = {
        'profile': profile,
        'welfare_badge': _welfare_badge.get(profile.welfare_status, 'bg-secondary-lt text-secondary'),
        'assessments': profile.assessments.all(),
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


def concern_list_page(request):
    return _concerns['page'](request)


def concern_list_ajax(request):
    return _concerns['list_ajax'](request)


def concern_get_ajax(request, pk):
    if request.user.is_staff or request.user.is_superuser:
        concern = get_object_or_404(Concern, pk=pk)
        mark_concern_read_by_management(concern, request.user)
    return _concerns['get_ajax'](request, pk)


def concern_save_ajax(request):
    return _concerns['save_ajax'](request)


def concern_delete_ajax(request, pk):
    return _concerns['delete_ajax'](request, pk)


@login_required(login_url='login')
def concern_delete_all_ajax(request):
    return _concerns['delete_all_ajax'](request)


def contact_list_page(request):
    return _contacts['page'](request)


def contact_list_ajax(request):
    return _contacts['list_ajax'](request)


def contact_get_ajax(request, pk):
    return _contacts['get_ajax'](request, pk)


def contact_save_ajax(request):
    return _contacts['save_ajax'](request)


def contact_delete_ajax(request, pk):
    return _contacts['delete_ajax'](request, pk)


@login_required(login_url='login')
def contact_delete_all_ajax(request):
    return _contacts['delete_all_ajax'](request)


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


def dashboard_stats(user):
    """Aggregate monitoring metrics shown on the dashboard."""
    sees_all = user.is_superuser or user.is_staff
    profiles = OFWProfile.objects.all() if sees_all else OFWProfile.objects.filter(user=user)
    checkins = CheckIn.objects.all() if sees_all else CheckIn.objects.filter(user=user)
    concerns = Concern.objects.all() if sees_all else Concern.objects.filter(user=user)
    contacts = EmergencyContact.objects.all() if sees_all else EmergencyContact.objects.filter(user=user)
    reports = MonitoringReport.objects.all() if sees_all else MonitoringReport.objects.filter(user=user)

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    at_risk = profiles.filter(
        welfare_status__in=[WelfareStatus.DISTRESSED, WelfareStatus.NEEDS_SUPPORT]
    )
    open_concerns = concerns.filter(status__in=['open', 'in_progress', 'escalated'])

    welfare_rows = profiles.values('welfare_status').annotate(total=Count('id'))
    welfare_labels = dict(WelfareStatus.choices)
    welfare_chart = [
        {
            'key': row['welfare_status'],
            'label': welfare_labels.get(row['welfare_status'], row['welfare_status']),
            'value': row['total'],
        }
        for row in welfare_rows
    ] or [{'key': '', 'label': 'No data', 'value': 0}]

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

    return {
        'kpi': {
            'ofw_total': profiles.count(),
            'ofw_at_risk': at_risk.count(),
            'checkins_month': checkins.filter(checkin_date__gte=month_start).count(),
            'open_concerns': open_concerns.count(),
            'contacts_total': contacts.count(),
            'reports_total': reports.count(),
        },
        'links': {
            'ofw_total': reverse('ofw:profile_list'),
            'ofw_at_risk': (
                reverse('ofw:profile_list')
                + f'?welfare_status={WelfareStatus.DISTRESSED},{WelfareStatus.NEEDS_SUPPORT}'
            ),
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
        },
        'recent_checkins': checkins.select_related('ofw').order_by('-checkin_date')[:5],
        'recent_concerns': concerns.select_related('ofw').order_by('-reported_date')[:5],
        'welfare_chart': welfare_chart,
        'concern_chart': concern_chart,
        'trend_chart': trend,
        'risk_labels': dict(RiskLevel.choices),
        'deployment_countries': deployment_countries,
        'map_regions': map_regions,
        'map_markers': map_markers,
        'map_regions_json': json.dumps(map_regions),
        'map_markers_json': json.dumps(map_markers),
        'map_ofws_json': json.dumps(map_ofws),
        'country_links_json': json.dumps(country_links),
    }
