"""Views for the OFW monitoring and support information system."""

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from . import crud
from .forms import (
    CheckInForm,
    ConcernForm,
    MonitoringReportForm,
    OFWProfileForm,
    SupportRecordForm,
    WelfareAssessmentForm,
)
from .models import (
    CheckIn,
    Concern,
    MonitoringReport,
    OFWProfile,
    RiskLevel,
    SupportRecord,
    WelfareAssessment,
    WelfareStatus,
)

_welfare_badge = {
    'active': 'bg-success-lt text-success',
    'on_leave': 'bg-azure-lt text-azure',
    'needs_support': 'bg-warning-lt text-warning',
    'distressed': 'bg-danger-lt text-danger',
    'repatriated': 'bg-secondary-lt text-secondary',
    'missing': 'bg-dark-lt text-dark',
    'deceased': 'bg-dark-lt text-dark',
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

_support_status_badge = {
    'pending': 'bg-warning-lt text-warning',
    'approved': 'bg-azure-lt text-azure',
    'released': 'bg-success-lt text-success',
    'completed': 'bg-secondary-lt text-secondary',
}

_report_status_badge = {
    'draft': 'bg-secondary-lt text-secondary',
    'submitted': 'bg-warning-lt text-warning',
    'approved': 'bg-success-lt text-success',
}

_profiles = crud.make_crud(
    model=OFWProfile,
    form_class=OFWProfileForm,
    columns=[
        {'field': 'full_name', 'label': 'Name'},
        {'field': 'passport_number', 'label': 'Passport'},
        {'field': 'country', 'label': 'Country'},
        {'field': 'employer_name', 'label': 'Employer'},
        {'field': 'occupation', 'label': 'Occupation'},
        {'field': 'get_welfare_status_display', 'label': 'Welfare Status',
         'badge': _welfare_badge, 'raw_field': 'welfare_status'},
        {'field': 'contract_end_date', 'label': 'Contract End', 'type': 'date'},
    ],
    search_fields=['first_name', 'last_name', 'passport_number', 'country',
                   'employer_name', 'occupation'],
    order_by=['last_name', 'first_name'],
    title='OFW Profiles',
    entity='OFW profile',
    add_label='Add OFW',
    search_placeholder='Search by name, passport, country, or employer...',
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
)

_checkins = crud.make_crud(
    model=CheckIn,
    form_class=CheckInForm,
    columns=[
        {'field': 'ofw', 'label': 'OFW'},
        {'field': 'checkin_date', 'label': 'Check-in', 'type': 'datetime'},
        {'field': 'get_method_display', 'label': 'Method'},
        {'field': 'get_condition_display', 'label': 'Condition', 'badge': _condition_badge,
         'raw_field': 'condition'},
        {'field': 'location', 'label': 'Location'},
        {'field': 'contacted_person', 'label': 'Contacted'},
    ],
    search_fields=['ofw__first_name', 'ofw__last_name', 'location', 'contacted_person'],
    title='Check-ins',
    entity='Check-in',
    add_label='Log Check-in',
    search_placeholder='Search by OFW, location, or person...',
)

_concerns = crud.make_crud(
    model=Concern,
    form_class=ConcernForm,
    columns=[
        {'field': 'ofw', 'label': 'OFW'},
        {'field': 'title', 'label': 'Concern'},
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
)

_supports = crud.make_crud(
    model=SupportRecord,
    form_class=SupportRecordForm,
    columns=[
        {'field': 'ofw', 'label': 'OFW'},
        {'field': 'title', 'label': 'Support'},
        {'field': 'get_support_type_display', 'label': 'Type'},
        {'field': 'provider', 'label': 'Provider'},
        {'field': 'amount', 'label': 'Amount', 'type': 'money'},
        {'field': 'date_provided', 'label': 'Date Provided', 'type': 'date'},
        {'field': 'get_status_display', 'label': 'Status', 'badge': _support_status_badge,
         'raw_field': 'status'},
    ],
    search_fields=['ofw__first_name', 'ofw__last_name', 'title', 'provider'],
    title='Support Documentation',
    entity='Support record',
    add_label='Add Support',
    search_placeholder='Search by OFW, support, or provider...',
)

_reports = crud.make_crud(
    model=MonitoringReport,
    form_class=MonitoringReportForm,
    columns=[
        {'field': 'title', 'label': 'Report'},
        {'field': 'get_report_type_display', 'label': 'Type'},
        {'field': 'period_start', 'label': 'Period Start', 'type': 'date'},
        {'field': 'period_end', 'label': 'Period End', 'type': 'date'},
        {'field': 'country', 'label': 'Country'},
        {'field': 'get_status_display', 'label': 'Status', 'badge': _report_status_badge,
         'raw_field': 'status'},
    ],
    search_fields=['title', 'country', 'prepared_by'],
    title='Monitoring Reports',
    entity='Monitoring report',
    add_label='Add Report',
    search_placeholder='Search by title, country, or preparer...',
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


def concern_list_page(request):
    return _concerns['page'](request)


def concern_list_ajax(request):
    return _concerns['list_ajax'](request)


def concern_get_ajax(request, pk):
    return _concerns['get_ajax'](request, pk)


def concern_save_ajax(request):
    return _concerns['save_ajax'](request)


def concern_delete_ajax(request, pk):
    return _concerns['delete_ajax'](request, pk)


def support_list_page(request):
    return _supports['page'](request)


def support_list_ajax(request):
    return _supports['list_ajax'](request)


def support_get_ajax(request, pk):
    return _supports['get_ajax'](request, pk)


def support_save_ajax(request):
    return _supports['save_ajax'](request)


def support_delete_ajax(request, pk):
    return _supports['delete_ajax'](request, pk)


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


def dashboard_stats(user):
    """Aggregate monitoring metrics shown on the dashboard."""
    profiles = OFWProfile.objects.all() if user.is_superuser else OFWProfile.objects.filter(user=user)
    checkins = CheckIn.objects.all() if user.is_superuser else CheckIn.objects.filter(user=user)
    concerns = Concern.objects.all() if user.is_superuser else Concern.objects.filter(user=user)
    supports = SupportRecord.objects.all() if user.is_superuser else SupportRecord.objects.filter(user=user)
    reports = MonitoringReport.objects.all() if user.is_superuser else MonitoringReport.objects.filter(user=user)

    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    at_risk = profiles.filter(
        welfare_status__in=[WelfareStatus.DISTRESSED, WelfareStatus.NEEDS_SUPPORT]
    )
    open_concerns = concerns.filter(status__in=['open', 'in_progress', 'escalated'])

    welfare_rows = profiles.values('welfare_status').annotate(total=Count('id'))
    welfare_labels = dict(WelfareStatus.choices)
    welfare_chart = [
        {'label': welfare_labels.get(row['welfare_status'], row['welfare_status']), 'value': row['total']}
        for row in welfare_rows
    ] or [{'label': 'No data', 'value': 0}]

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

    total_support = supports.aggregate(total=Sum('amount'))['total']

    return {
        'kpi': {
            'ofw_total': profiles.count(),
            'ofw_at_risk': at_risk.count(),
            'checkins_month': checkins.filter(checkin_date__gte=month_start).count(),
            'open_concerns': open_concerns.count(),
            'support_total': supports.count(),
            'support_amount': total_support or 0,
            'reports_total': reports.count(),
        },
        'recent_checkins': checkins.select_related('ofw').order_by('-checkin_date')[:5],
        'recent_concerns': concerns.select_related('ofw').order_by('-reported_date')[:5],
        'recent_supports': supports.select_related('ofw').order_by('-date_provided')[:5],
        'welfare_chart': welfare_chart,
        'concern_chart': concern_chart,
        'trend_chart': trend,
        'risk_labels': dict(RiskLevel.choices),
    }
