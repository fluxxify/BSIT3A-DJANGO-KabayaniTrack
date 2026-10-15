"""Self-service views for the OFW portal.

These are the friendly, card-based pages an OFW sees after signing in.  Every
record an OFW creates here is owned by their account, so the management
console (which sees all records) automatically stays in sync.  Conversely,
check-ins, assessments and concerns logged by management against an OFW's
profile are surfaced back here because they are linked through the profile.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import OFWPortalProfileForm, OFWSelfCheckInForm, OFWSelfConcernForm
from .models import CheckIn, Concern, EmergencyContact, OFWProfile, WelfareAssessment
from .roles import is_ofw
from .views import (
    _concern_status_badge,
    _condition_badge,
    _severity_badge,
    _welfare_badge,
)


def _guard(request):
    """Redirect management users away from the OFW portal (returns None if OK)."""
    if is_ofw(request.user):
        return None
    return redirect('dashboard')


def _profile_for(user):
    return OFWProfile.objects.filter(user=user).order_by('id').first()


@login_required(login_url='login')
def portal_home(request):
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    my_checkins = CheckIn.objects.filter(ofw__user=request.user)
    my_concerns = Concern.objects.filter(ofw__user=request.user)
    assessments = list(
        WelfareAssessment.objects.filter(ofw__user=request.user)
        .order_by('-assessment_date', '-id')[:5]
    )

    checkin_rows = [
        {'obj': c, 'badge': _condition_badge.get(c.condition, 'bg-secondary-lt text-secondary')}
        for c in my_checkins.select_related('ofw').order_by('-checkin_date')[:5]
    ]
    concern_rows = [
        {
            'obj': c,
            'status_badge': _concern_status_badge.get(c.status, 'bg-secondary-lt text-secondary'),
            'severity_badge': _severity_badge.get(c.severity, 'bg-secondary-lt text-secondary'),
        }
        for c in my_concerns.select_related('ofw').order_by('-reported_date')[:5]
    ]

    context = {
        'profile': profile,
        'welfare_badge': (
            _welfare_badge.get(profile.welfare_status, 'bg-secondary-lt text-secondary')
            if profile else 'bg-secondary-lt text-secondary'
        ),
        'latest_assessment': assessments[0] if assessments else None,
        'assessments': assessments,
        'checkin_rows': checkin_rows,
        'concern_rows': concern_rows,
        'checkin_count': my_checkins.count(),
        'concern_count': my_concerns.count(),
        'open_concerns': my_concerns.filter(
            status__in=['open', 'in_progress', 'escalated']
        ).count(),
    }
    return render(request, 'ofw/portal/home.html', context)


@login_required(login_url='login')
def portal_profile(request):
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)

    if request.method == 'POST':
        form = OFWPortalProfileForm(request.POST, instance=profile)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.save()
            messages.success(request, 'Your profile information has been saved.')
            return redirect('ofw:portal_profile')
    else:
        form = OFWPortalProfileForm(instance=profile)

    return render(request, 'ofw/portal/profile.html', {
        'form': form,
        'profile': profile,
        'welfare_badge': (
            _welfare_badge.get(profile.welfare_status, 'bg-secondary-lt text-secondary')
            if profile else 'bg-secondary-lt text-secondary'
        ),
    })


@login_required(login_url='login')
def portal_checkins(request):
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    if profile is None:
        messages.info(request, 'Please complete your profile before checking in.')
        return redirect('ofw:portal_profile')

    if request.method == 'POST':
        form = OFWSelfCheckInForm(request.POST)
        if form.is_valid():
            checkin = form.save(commit=False)
            checkin.ofw = profile
            checkin.user = request.user
            checkin.checkin_date = timezone.now()
            checkin.save()
            messages.success(request, 'Thank you! Your check-in has been recorded.')
            return redirect('ofw:portal_checkins')
    else:
        form = OFWSelfCheckInForm(initial={'method': CheckIn.Method.APP, 'condition': CheckIn.Condition.SAFE})

    checkins = CheckIn.objects.filter(ofw__user=request.user).order_by('-checkin_date')
    checkin_rows = [
        {'obj': c, 'badge': _condition_badge.get(c.condition, 'bg-secondary-lt text-secondary')}
        for c in checkins
    ]
    return render(request, 'ofw/portal/checkins.html', {
        'form': form,
        'profile': profile,
        'checkin_rows': checkin_rows,
    })


@login_required(login_url='login')
def portal_concerns(request):
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    if profile is None:
        messages.info(request, 'Please complete your profile before reporting a concern.')
        return redirect('ofw:portal_profile')

    if request.method == 'POST':
        form = OFWSelfConcernForm(request.POST)
        if form.is_valid():
            concern = form.save(commit=False)
            concern.ofw = profile
            concern.user = request.user
            concern.reported_date = timezone.localdate()
            concern.status = Concern.Status.OPEN
            concern.save()
            messages.success(request, 'Your concern has been submitted to the management team.')
            return redirect('ofw:portal_concerns')
    else:
        form = OFWSelfConcernForm()

    concerns = Concern.objects.filter(ofw__user=request.user).order_by('-reported_date', '-id')
    concern_rows = [
        {
            'obj': c,
            'status_badge': _concern_status_badge.get(c.status, 'bg-secondary-lt text-secondary'),
            'severity_badge': _severity_badge.get(c.severity, 'bg-secondary-lt text-secondary'),
        }
        for c in concerns
    ]
    return render(request, 'ofw/portal/concerns.html', {
        'form': form,
        'profile': profile,
        'concern_rows': concern_rows,
    })


@login_required(login_url='login')
def portal_contacts(request):
    guard = _guard(request)
    if guard:
        return guard

    contacts = (
        EmergencyContact.objects
        .filter(Q(user=request.user) | Q(user__isnull=True))
        .order_by('contact_type', 'name')
    )
    return render(request, 'ofw/portal/contacts.html', {'contacts': contacts})
