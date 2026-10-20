"""Self-service views for the OFW portal.

These are the friendly, card-based pages an OFW sees after signing in.  Every
record an OFW creates here is owned by their account, so the management
console (which sees all records) automatically stays in sync.  Conversely,
check-ins, assessments and concerns logged by management against an OFW's
profile are surfaced back here because they are linked through the profile.
"""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import (
    FamilyContactRequestForm,
    OFWPortalProfileForm,
    OFWSelfCheckInForm,
    OFWSelfConcernForm,
)
from .locations import CITIES_BY_COUNTRY, COUNTRY_CHOICES
from .models import (
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyContact,
    EmergencyContactRequest,
    OFWProfile,
    WelfareAssessment,
)
from .roles import is_ofw
from .views import (
    _concern_status_badge,
    _condition_badge,
    _request_status_badge,
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
        'country_options': COUNTRY_CHOICES,
        'cities_by_country_json': json.dumps(CITIES_BY_COUNTRY),
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
        form = OFWSelfConcernForm(request.POST, request.FILES)
        if form.is_valid():
            concern = form.save(commit=False)
            concern.ofw = profile
            concern.user = request.user
            concern.reported_date = timezone.localdate()
            concern.status = Concern.Status.OPEN
            concern.save()
            proof_files = form.cleaned_data.get('proof_files') or []
            for uploaded in proof_files:
                ConcernProof.objects.create(
                    concern=concern,
                    file=uploaded,
                    original_name=uploaded.name,
                )
            if proof_files:
                messages.success(
                    request,
                    'Your concern has been submitted to the management team '
                    f'with {len(proof_files)} proof file'
                    f'{"s" if len(proof_files) > 1 else ""} attached.',
                )
            else:
                messages.success(
                    request, 'Your concern has been submitted to the management team.'
                )
            return redirect('ofw:portal_concerns')
    else:
        form = OFWSelfConcernForm()

    concerns = (
        Concern.objects
        .filter(ofw__user=request.user)
        .prefetch_related('proofs')
        .order_by('-reported_date', '-id')
    )
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

    profile = _profile_for(request.user)
    location_country = profile.country.strip() if profile and profile.country else ''
    location_city = profile.city_abroad.strip() if profile and profile.city_abroad else ''

    if request.method == 'POST':
        form = FamilyContactRequestForm(request.POST)
        if form.is_valid():
            contact_request = form.save(commit=False)
            contact_request.user = request.user
            contact_request.ofw = profile
            contact_request.save()
            messages.success(
                request,
                'Your request has been submitted. The management team will review it shortly.',
            )
            return redirect('ofw:portal_contacts')
    else:
        form = FamilyContactRequestForm()

    # Public hotlines: the OFW's deployment country plus the national Philippine
    # hotlines (DMW / OWWA) that apply wherever they are posted.
    hotline_countries = {'Philippines'}
    if location_country:
        hotline_countries.add(location_country)

    hotlines = (
        EmergencyContact.objects
        .filter(
            contact_type__in=EmergencyContact.PUBLIC_TYPES,
            country__in=sorted(hotline_countries),
        )
        .order_by('country', 'contact_type', 'name')
    )
    local_hotlines = [
        c for c in hotlines if location_country and c.country == location_country
    ]
    national_hotlines = [c for c in hotlines if c.country == 'Philippines']

    my_contacts = (
        EmergencyContact.objects
        .filter(user=request.user)
        .order_by('contact_type', 'name')
    )
    request_rows = [
        {
            'obj': r,
            'status_badge': _request_status_badge.get(
                r.status, 'bg-secondary-lt text-secondary'
            ),
        }
        for r in EmergencyContactRequest.objects.filter(user=request.user)
    ]

    return render(request, 'ofw/portal/contacts.html', {
        'profile': profile,
        'location_country': location_country,
        'location_city': location_city,
        'local_hotlines': local_hotlines,
        'national_hotlines': national_hotlines,
        'my_contacts': my_contacts,
        'request_rows': request_rows,
        'form': form,
    })
