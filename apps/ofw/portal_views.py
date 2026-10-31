"""Self-service views for the OFW portal.

These are the friendly, card-based pages an OFW sees after signing in.  Every
record an OFW creates here is owned by their account, so the management
console (which sees all records) automatically stays in sync.  Conversely,
check-ins, assessments and concerns logged by management against an OFW's
profile are surfaced back here because they are linked through the profile.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (
    FamilyContactForm,
    OFWPortalProfileForm,
    OFWSelfCheckInForm,
    OFWSelfConcernForm,
    SafeLocationSuggestionForm,
)
from .hotlines import automatic_local_hotlines, philippine_national_hotlines
from .locations import COUNTRY_CHOICES, canonical_country, cities_for_country
from .models import (
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyAlert,
    EmergencyContact,
    Notification,
    OFWActivity,
    OFWProfile,
    PoliceReport,
    SafeLocationSuggestion,
    WelfareAssessment,
)
from .notifications import notify, notify_managers
from .roles import is_ofw
from .views import (
    _concern_status_badge,
    _condition_badge,
    _severity_badge,
    _welfare_badge,
)


def _concern_title(concern):
    """Build a short title from an OFW's description.

    OFWs no longer type a title, but the management console and database still
    expect one, so derive it from the report itself.
    """
    text = ' '.join((concern.description or '').split())
    if text:
        return text[:200]
    return f'{concern.get_category_display()} concern'


def _guard(request):
    """Redirect management users away from the OFW portal (returns None if OK)."""
    if is_ofw(request.user):
        return None
    return redirect('dashboard')


def _profile_for(user):
    return OFWProfile.objects.filter(user=user).order_by('id').first()


def _hotline_number(contact):
    return contact.dial_number or (contact.phone or '').strip()


def _dedupe_hotlines(contacts, key_func):
    """Keep the first row for each key while preserving priority order."""
    seen = set()
    result = []
    for contact in contacts:
        key = key_func(contact)
        if key and key in seen:
            continue
        seen.add(key)
        result.append(contact)
    return result


def _hotlines_for(location_country):
    """Public hotlines for the OFW's deployment country plus the PH national ones.

    Database entries are authoritative and come first.  Bundled country data
    fills in local emergency numbers when management has not added any, so an
    OFW always has at least one local number plus the Philippine hotlines.
    Returns a ``(local_hotlines, national_hotlines)`` tuple.
    """
    country = canonical_country(location_country)
    public_contacts = list(
        EmergencyContact.objects
        .filter(contact_type__in=EmergencyContact.PUBLIC_TYPES)
        .order_by('country', 'contact_type', 'name')
    )

    db_local = []
    db_national = []
    for contact in public_contacts:
        contact_country = canonical_country(contact.country)
        if country and country != 'Philippines' and contact_country == country:
            db_local.append(contact)
        elif contact_country == 'Philippines':
            db_national.append(contact)

    local = _dedupe_hotlines(
        db_local + automatic_local_hotlines(country),
        _hotline_number,
    )
    national = _dedupe_hotlines(
        db_national + philippine_national_hotlines(),
        _hotline_number,
    )
    return local, national


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

    # Inactive status: is the OFW's account flagged inactive (3+ days no login)?
    activity = OFWActivity.objects.filter(user=request.user).first()
    is_inactive = (
        activity is not None
        and not activity.is_account_active
        and activity.days_inactive >= OFWActivity.INACTIVE_THRESHOLD_DAYS
    )
    inactive_days = activity.days_inactive if activity else 0

    # Police report status: any open/submitted police report for this OFW?
    police_reports = PoliceReport.objects.filter(ofw=profile).order_by('-reported_at') if profile else []
    latest_police_report = police_reports.first() if police_reports else None

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
        'is_inactive': is_inactive,
        'inactive_days': inactive_days,
        'latest_police_report': latest_police_report,
    }
    return render(request, 'ofw/portal/home.html', context)


@login_required(login_url='login')
def portal_profile(request):
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)

    if request.method == 'POST':
        if request.POST.get('remove_profile_picture') == '1' and profile:
            if profile.profile_picture:
                profile.profile_picture.delete(save=False)
            profile.profile_picture = None
            profile.save(update_fields=['profile_picture'])
            notify_managers(
                title=f'Profile updated: {profile.full_name}',
                message='The OFW has removed their profile picture.',
                url=reverse('ofw:profile_detail', args=[profile.pk]),
                level=Notification.Level.INFO,
                exclude_user=request.user,
                agency=profile.agency_org,
            )
            messages.success(request, 'Profile picture removed.')
            return redirect('ofw:portal_profile')

        form = OFWPortalProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.user = request.user
            obj.save()
            notify_managers(
                title=f'Profile updated: {obj.full_name}',
                message='The OFW has updated their profile information.',
                url=reverse('ofw:profile_detail', args=[obj.pk]),
                level=Notification.Level.INFO,
                exclude_user=request.user,
                agency=obj.agency_org,
            )
            if request.FILES.get('profile_picture'):
                messages.success(request, 'Profile picture updated successfully.')
            else:
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
    })


@login_required(login_url='login')
def portal_cities(request):
    """City datalist options for one country (fetched as the country changes)."""
    guard = _guard(request)
    if guard:
        return guard

    country = (request.GET.get('country') or '').strip()
    return JsonResponse({'cities': cities_for_country(country)})


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
            detail = (
                f'{checkin.get_condition_display()} via '
                f'{checkin.get_method_display()}.'
            )
            if checkin.contact_person:
                detail += f' Contact person: {checkin.contact_person}.'

            # If the OFW reports distressed, raise an emergency alert so
            # management and agency staff see it in the Emergency Alerts console.
            alert = None
            if checkin.condition == CheckIn.Condition.DISTRESSED:
                alert, created = EmergencyAlert.objects.get_or_create(
                    ofw=profile,
                    status=EmergencyAlert.Status.OPEN,
                    defaults={
                        'title': f'Distressed check-in from {profile.full_name}',
                        'message': (
                            f'{profile.full_name} reported a distressed condition '
                            f'via {checkin.get_method_display()}. {detail}'
                        ),
                        'level': EmergencyAlert.Level.DANGER,
                    },
                )
                if not created:
                    alert.level = EmergencyAlert.Level.DANGER
                    alert.message = (
                        f'{profile.full_name} reported another distressed check-in '
                        f'via {checkin.get_method_display()}. {detail}'
                    )
                    alert.save(update_fields=['level', 'message', 'updated_at'])

            # If the OFW reports SAFE and there is an open emergency alert,
            # resolve it so management knows the OFW is okay.
            if checkin.condition == CheckIn.Condition.SAFE:
                open_alerts = EmergencyAlert.objects.filter(
                    ofw=profile,
                    status=EmergencyAlert.Status.OPEN,
                )
                for open_alert in open_alerts:
                    open_alert.status = EmergencyAlert.Status.RESOLVED
                    open_alert.message = (
                        f'{open_alert.message}\n\nResolved: {profile.full_name} '
                        f'checked in as SAFE via {checkin.get_method_display()}. '
                        f'{detail}'
                    )
                    open_alert.save(update_fields=['status', 'message', 'updated_at'])

            notify_managers(
                title=f'New check-in from {profile.full_name}',
                message=detail,
                url=reverse('ofw:checkin_detail', args=[checkin.pk]),
                level=(
                    Notification.Level.DANGER
                    if checkin.condition == CheckIn.Condition.DISTRESSED
                    else Notification.Level.WARNING
                    if checkin.condition != CheckIn.Condition.SAFE
                    else Notification.Level.SUCCESS
                ),
                exclude_user=request.user,
                agency=profile.agency_org,
            )
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
            concern.title = _concern_title(concern)
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
            notify_managers(
                title=f'New concern from {profile.full_name}',
                message=(
                    f'{concern.get_category_display()}: "{concern.title}" '
                    f'({concern.get_severity_display()} severity).'
                ),
                url=reverse('ofw:concern_detail', args=[concern.pk]),
                level=(
                    Notification.Level.DANGER
                    if concern.severity in (Concern.Severity.HIGH, Concern.Severity.CRITICAL)
                    else Notification.Level.WARNING
                ),
                exclude_user=request.user,
                agency=profile.agency_org,
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
    location_country = canonical_country(profile.country) if profile and profile.country else ''
    location_city = profile.city_abroad.strip() if profile and profile.city_abroad else ''

    if request.method == 'POST':
        form = FamilyContactForm(request.POST)
        if form.is_valid():
            contact = form.save(commit=False)
            contact.user = request.user
            contact.save()
            notify_managers(
                title=f'Emergency contact added: {contact.name}',
                message=f'{profile.full_name} added "{contact.name}" as an emergency contact.',
                url=reverse('ofw:contact_list'),
                level=Notification.Level.INFO,
                exclude_user=request.user,
                agency=profile.agency_org,
            )
            messages.success(
                request,
                f'"{contact.name}" has been added to your family emergency contacts.',
            )
            return redirect('ofw:portal_contacts')
    else:
        form = FamilyContactForm()

    local_hotlines, national_hotlines = _hotlines_for(location_country)

    my_contacts = (
        EmergencyContact.objects
        .filter(user=request.user)
        .exclude(contact_type__in=EmergencyContact.PUBLIC_TYPES)
        .order_by('contact_type', 'name')
    )

    return render(request, 'ofw/portal/contacts.html', {
        'profile': profile,
        'location_country': location_country,
        'location_city': location_city,
        'local_hotlines': local_hotlines,
        'national_hotlines': national_hotlines,
        'my_contacts': my_contacts,
        'form': form,
    })


@login_required(login_url='login')
def portal_sos(request):
    """One-tap emergency page: every reachable number in one place."""
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    location_country = canonical_country(profile.country) if profile and profile.country else ''
    location_city = profile.city_abroad.strip() if profile and profile.city_abroad else ''

    local_hotlines, national_hotlines = _hotlines_for(location_country)

    # The SOS hero already has one-tap buttons for these numbers.  Avoid
    # repeating the *automatic* copies below; database entries are still kept
    # because they may carry a more specific office name or extra details.
    quick_numbers = {'911', '1348', '+63285511545'}
    national_hotlines = [
        contact for contact in national_hotlines
        if not (
            getattr(contact, 'automatic', False)
            and contact.dial_number in quick_numbers
        )
    ]

    family_contacts = (
        EmergencyContact.objects
        .filter(user=request.user)
        .exclude(contact_type__in=EmergencyContact.PUBLIC_TYPES)
        .order_by('contact_type', 'name')
    )

    return render(request, 'ofw/portal/sos.html', {
        'profile': profile,
        'location_country': location_country,
        'location_city': location_city,
        'local_hotlines': local_hotlines,
        'national_hotlines': national_hotlines,
        'family_contacts': family_contacts,
    })


@login_required(login_url='login')
def portal_contact_edit(request, pk):
    guard = _guard(request)
    if guard:
        return guard

    contact = get_object_or_404(
        EmergencyContact.objects.exclude(
            contact_type__in=EmergencyContact.PUBLIC_TYPES
        ),
        pk=pk, user=request.user,
    )

    if request.method == 'POST':
        form = FamilyContactForm(request.POST, instance=contact)
        if form.is_valid():
            form.save()
            profile = _profile_for(request.user)
            notify_managers(
                title=f'Emergency contact updated: {contact.name}',
                message=f'{profile.full_name if profile else request.user.username} updated "{contact.name}".',
                url=reverse('ofw:contact_list'),
                level=Notification.Level.INFO,
                exclude_user=request.user,
                agency=profile.agency_org if profile else None,
            )
            messages.success(request, f'"{contact.name}" has been updated.')
            return redirect('ofw:portal_contacts')
    else:
        form = FamilyContactForm(instance=contact)

    return render(request, 'ofw/portal/contact_form.html', {
        'form': form,
        'contact': contact,
    })


@login_required(login_url='login')
def portal_contact_delete(request, pk):
    guard = _guard(request)
    if guard:
        return guard

    contact = get_object_or_404(
        EmergencyContact.objects.exclude(
            contact_type__in=EmergencyContact.PUBLIC_TYPES
        ),
        pk=pk, user=request.user,
    )

    if request.method == 'POST':
        name = contact.name
        profile = _profile_for(request.user)
        contact.delete()
        notify_managers(
            title=f'Emergency contact removed: {name}',
            message=f'{profile.full_name if profile else request.user.username} removed "{name}" from emergency contacts.',
            url=reverse('ofw:contact_list'),
            level=Notification.Level.INFO,
            exclude_user=request.user,
            agency=profile.agency_org if profile else None,
        )
        return redirect('ofw:portal_contacts')


@login_required(login_url='login')
def portal_suggest_safe_place(request):
    """OFW suggests a new safe place for admin approval."""
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    if profile is None:
        messages.info(request, 'Please complete your profile before suggesting a safe place.')
        return redirect('ofw:portal_profile')

    if request.method == 'POST':
        form = SafeLocationSuggestionForm(request.POST)
        if form.is_valid():
            suggestion = form.save(commit=False)
            suggestion.submitted_by = request.user
            suggestion.save()
            notify_managers(
                title=f'New safe place suggestion: {suggestion.name}',
                message=(
                    f'{profile.full_name} suggested a new safe place: {suggestion.name} '
                    f'({suggestion.get_location_type_display()}) in {suggestion.city}, {suggestion.country}.'
                ),
                url=reverse('admin:kabayan_safelocationsuggestion_changelist'),
                level=Notification.Level.INFO,
                exclude_user=request.user,
                agency=profile.agency_org,
            )
            messages.success(
                request,
                f'Your suggestion "{suggestion.name}" has been submitted for admin approval.'
            )
            return redirect('ofw:portal_suggest_safe_place')
    else:
        form = SafeLocationSuggestionForm(initial={'country': profile.country or ''})

    my_suggestions = SafeLocationSuggestion.objects.filter(
        submitted_by=request.user
    ).order_by('-created_at')

    return render(request, 'ofw/portal/suggest_safe_place.html', {
        'form': form,
        'profile': profile,
        'my_suggestions': my_suggestions,
    })
