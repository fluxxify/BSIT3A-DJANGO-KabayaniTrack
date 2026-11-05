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
from django.views.decorators.http import require_POST

from .activity import refresh_activity_for_user
from .forms import (
    FamilyContactForm,
    OFWPortalProfileForm,
    OFWSelfCheckInForm,
    OFWSelfConcernForm,
    SafeLocationSuggestionForm,
)
from .hotlines import automatic_local_hotlines, philippine_national_hotlines
from .locations import (
    COUNTRY_CHOICES,
    COUNTRY_GEO,
    canonical_country,
    cities_for_country,
)
from .models import (
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyAlert,
    EmergencyContact,
    Notification,
    LocationTracker,
    OFWActivity,
    OFWLocationSharing,
    OFWProfile,
    PoliceReport,
    SafeLocation,
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
    location_tracker_ping,
    nearest_safe_places,
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


def _latest_ping(profile):
    if profile is None:
        return None
    return (
        LocationTracker.objects
        .filter(ofw=profile)
        .order_by('-recorded_at')
        .first()
    )


def _country_places(profile):
    """Active safe places for the OFW's deployment country (all if unset)."""
    country = canonical_country(profile.country) if profile and profile.country else ''
    places = SafeLocation.objects.filter(is_active=True)
    if country:
        country_places = places.filter(country__iexact=country)
        if country_places.exists():
            places = country_places
    return places.order_by('location_type', 'name')


def _place_row(place):
    """A template-friendly safe-place row (with coordinates when available)."""
    has_coords = place.has_coords
    return {
        'id': place.pk,
        'name': place.name,
        'type': place.get_location_type_display(),
        'type_key': place.location_type,
        'city': place.city,
        'country': place.country,
        'address': place.address,
        'phone': place.phone,
        'tel': ''.join(
            char for char in (place.phone or '') if char.isdigit() or char == '+'
        ),
        'latitude': float(place.latitude) if has_coords else None,
        'longitude': float(place.longitude) if has_coords else None,
        'distance_km': None,
        'distance_text': '',
        'walking_minutes': None,
        'bearing': None,
        'direction': '',
        'maps_url': (
            'https://www.google.com/maps/dir/?api=1&destination='
            f'{place.latitude},{place.longitude}'
            if has_coords else ''
        ),
    }


def _safety_places(profile, latest_ping=None, limit=6):
    """Nearest safe places from the last ping, or the country's saved places."""
    latest_ping = latest_ping if latest_ping is not None else _latest_ping(profile)
    if latest_ping is not None:
        rows = nearest_safe_places(
            latest_ping.latitude,
            latest_ping.longitude,
            limit=limit,
        )
        if rows:
            return rows
    return [_place_row(place) for place in _country_places(profile)[:limit]]


def _map_places(profile, latest_ping=None):
    """Safe-place markers for the OFW's own map, nearest first when known."""
    latest_ping = latest_ping if latest_ping is not None else _latest_ping(profile)
    places = list(_country_places(profile))
    if latest_ping is not None:
        ordered = nearest_safe_places(
            latest_ping.latitude,
            latest_ping.longitude,
            limit=None,
            locations=places,
        )
        by_id = {place.pk: place for place in places}
        places = [by_id[row['id']] for row in ordered if row['id'] in by_id]

    markers = []
    for place in places:
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
            'maps_url': (
                'https://www.google.com/maps/dir/?api=1&destination='
                f'{place.latitude},{place.longitude}'
            ),
        })
    return markers[:80]


def _map_center(profile, latest_ping=None):
    """Best map centre: the last shared point, then the country, then PH."""
    latest_ping = latest_ping if latest_ping is not None else _latest_ping(profile)
    if latest_ping is not None:
        return {
            'lat': float(latest_ping.latitude),
            'lng': float(latest_ping.longitude),
            'zoom': 14,
        }
    country = canonical_country(profile.country) if profile and profile.country else ''
    if country in COUNTRY_GEO:
        _iso2, lat, lng = COUNTRY_GEO[country]
        return {'lat': float(lat), 'lng': float(lng), 'zoom': 5}
    return {'lat': 12.8797, 'lng': 121.7740, 'zoom': 5}


def _police_hotline(local_hotlines, national_hotlines):
    """Pick the police row from the local or national hotline lists."""
    contacts = list(local_hotlines) + list(national_hotlines)
    for contact in contacts:
        if getattr(contact, 'contact_type', '') == 'police':
            return contact
    for contact in contacts:
        if 'police' in (getattr(contact, 'name', '') or '').lower():
            return contact
    return None


def _nearest_police_station(profile, latest_ping=None):
    """Closest registered police station, with a country fallback."""
    latest_ping = latest_ping if latest_ping is not None else _latest_ping(profile)
    places = [
        place for place in _country_places(profile)
        if place.location_type == SafeLocation.LocationType.POLICE_STATION
    ]
    if latest_ping is not None:
        rows = nearest_safe_places(
            latest_ping.latitude,
            latest_ping.longitude,
            limit=1,
            locations=places,
        )
        if rows:
            return rows[0]
    return _place_row(places[0]) if places else None


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

    # Keep the OFW's own portal status in sync with the successful login time.
    activity = refresh_activity_for_user(request.user)
    is_inactive = activity.days_inactive >= OFWActivity.INACTIVE_THRESHOLD_DAYS
    inactive_days = activity.days_inactive

    # Police report status: any open/submitted police report for this OFW?
    police_reports = PoliceReport.objects.filter(ofw=profile).order_by('-reported_at') if profile else []
    latest_police_report = police_reports.first() if police_reports else None

    # Connected safety modules: the OFW sees the same alert, location and
    # police information that management sees, but limited to their own case.
    latest_ping = _latest_ping(profile)
    active_alerts = (
        EmergencyAlert.objects.filter(ofw=profile)
        .exclude(status=EmergencyAlert.Status.RESOLVED)
        .order_by('-created_at')
        if profile else EmergencyAlert.objects.none()
    )
    latest_alert = active_alerts.first()
    sharing_enabled = bool(
        profile and OFWLocationSharing.objects.filter(
            ofw=profile, is_enabled=True
        ).exists()
    )
    nearest_place = None
    if profile is not None:
        places = _safety_places(profile, latest_ping=latest_ping, limit=1)
        nearest_place = places[0] if places else None
    nearest_police_station = _nearest_police_station(
        profile, latest_ping=latest_ping
    )
    warning_notifications = Notification.objects.filter(
        recipient=request.user,
        level__in=[Notification.Level.WARNING, Notification.Level.DANGER],
        is_read=False,
    )
    last_checkin = my_checkins.order_by('-checkin_date').first()

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
        'last_login_at': activity.last_login_at,
        'has_ever_logged_in': activity.last_login_at is not None,
        'latest_police_report': latest_police_report,
        'latest_ping': latest_ping,
        'latest_alert': latest_alert,
        'active_alert_count': active_alerts.count(),
        'sharing_enabled': sharing_enabled,
        'nearest_place': nearest_place,
        'nearest_police_station': nearest_police_station,
        'warning_count': warning_notifications.count(),
        'last_checkin': last_checkin,
    }
    return render(request, 'ofw/portal/home.html', context)


@login_required(login_url='login')
def portal_location_sharing(request):
    """OFW-controlled, opt-in browser location sharing for their agency."""
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    if profile is None:
        messages.error(request, 'Complete your OFW profile before sharing your location.')
        return redirect('ofw:portal_profile')

    sharing, _ = OFWLocationSharing.objects.get_or_create(ofw=profile)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'enable':
            sharing.is_enabled = True
            sharing.enabled_at = timezone.now()
            sharing.save(update_fields=['is_enabled', 'enabled_at', 'updated_at'])
            messages.success(request, 'Live location sharing is enabled. Keep this page open for updates.')
        elif action == 'disable':
            sharing.is_enabled = False
            sharing.enabled_at = None
            sharing.save(update_fields=['is_enabled', 'enabled_at', 'updated_at'])
            messages.info(request, 'Live location sharing is off.')
        return redirect('ofw:portal_location_sharing')

    latest_ping = _latest_ping(profile)
    nearest_places = _safety_places(profile, latest_ping=latest_ping, limit=6)
    map_places = _map_places(profile, latest_ping=latest_ping)
    map_center = _map_center(profile, latest_ping=latest_ping)
    country = canonical_country(profile.country) if profile.country else ''
    return render(request, 'ofw/portal/location_sharing.html', {
        'profile': profile,
        'sharing': sharing,
        'latest_ping': latest_ping,
        'nearest_places': nearest_places,
        'map_places': map_places,
        'map_center': map_center,
        'location_country': country,
        'page_title': 'My Live Location',
        'page_pretitle': 'Live OFW Map',
    })


@login_required(login_url='login')
@require_POST
def portal_location_sharing_ping(request):
    """Accept a non-emergency location ping only while the OFW opted in."""
    if not is_ofw(request.user):
        return JsonResponse({'error': 'OFW accounts only.'}, status=403)
    profile = _profile_for(request.user)
    if profile is None or not OFWLocationSharing.objects.filter(
        ofw=profile, is_enabled=True
    ).exists():
        return JsonResponse({'error': 'Live location sharing is not enabled.'}, status=403)

    # Reuse the shared coordinate validation and ping creation, but never mark
    # opt-in background location updates as emergency SOS events.
    request.POST = request.POST.copy()
    request.POST['is_emergency'] = '0'
    return location_tracker_ping(request)


@login_required(login_url='login')
def portal_emergency_guidance(request):
    """OFW counterpart of the management Emergency Guidance console.

    Shows the OFW's own active alerts, the nearest registered safe place and
    the emergency numbers for their deployment country, then links to the live
    SOS guide that streams location updates to management.
    """
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    if profile is None:
        messages.info(request, 'Complete your profile so guidance can use your country.')
        return redirect('ofw:portal_profile')

    country = canonical_country(profile.country) if profile.country else ''
    city = profile.city_abroad.strip() if profile.city_abroad else ''
    latest_ping = _latest_ping(profile)
    nearest_places = _safety_places(profile, latest_ping=latest_ping, limit=4)
    alerts = EmergencyAlert.objects.filter(ofw=profile).order_by('-created_at')
    active_alerts = alerts.exclude(status=EmergencyAlert.Status.RESOLVED)
    open_alert = active_alerts.first()
    local_hotlines, national_hotlines = _hotlines_for(country)
    police_hotline = _police_hotline(local_hotlines, national_hotlines)
    if police_hotline is not None:
        # The police row gets its own prominent button, so drop the duplicate
        # from the general list to avoid showing the same number twice.
        local_hotlines = [
            contact for contact in local_hotlines
            if contact.dial_number != police_hotline.dial_number
        ]
        national_hotlines = [
            contact for contact in national_hotlines
            if contact.dial_number != police_hotline.dial_number
        ]
    family_contacts = (
        EmergencyContact.objects
        .filter(user=request.user)
        .exclude(contact_type__in=EmergencyContact.PUBLIC_TYPES)
        .order_by('contact_type', 'name')[:4]
    )

    return render(request, 'ofw/portal/emergency_guidance.html', {
        'profile': profile,
        'location_country': country,
        'location_city': city,
        'latest_ping': latest_ping,
        'nearest_places': nearest_places,
        'alerts': alerts[:10],
        'active_alert_count': active_alerts.count(),
        'open_alert': open_alert,
        'local_hotlines': local_hotlines,
        'national_hotlines': national_hotlines,
        'police_hotline': police_hotline,
        'family_contacts': family_contacts,
        'agency_phone': (
            profile.agency_org.phone
            if profile.agency_org_id and profile.agency_org.phone else ''
        ),
        'page_title': 'Emergency Guidance',
        'page_pretitle': 'OFW Portal',
    })


@login_required(login_url='login')
def portal_login_warnings(request):
    """OFW counterpart of the management Login Warnings console.

    The OFW sees the same activity clock that management uses: last successful
    login, days inactive, the 3-day warning stage and the 6-day follow-up
    stage, plus any warning messages received from their agency.
    """
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    activity = refresh_activity_for_user(request.user)
    days_inactive = activity.days_inactive
    is_inactive = days_inactive >= OFWActivity.INACTIVE_THRESHOLD_DAYS
    if days_inactive > 5:
        warning_stage = 'followup'
        warning_label = 'Follow-up overdue'
    elif is_inactive:
        warning_stage = 'warning'
        warning_label = 'Welfare check needed'
    else:
        warning_stage = 'active'
        warning_label = 'Account active'

    warning_notifications = Notification.objects.filter(
        recipient=request.user,
        level__in=[Notification.Level.WARNING, Notification.Level.DANGER],
    ).order_by('-created_at')[:20]
    last_checkin = (
        CheckIn.objects.filter(ofw__user=request.user)
        .order_by('-checkin_date')
        .first()
    )
    agency_phone = (
        profile.agency_org.phone
        if profile and profile.agency_org_id and profile.agency_org.phone else ''
    )

    return render(request, 'ofw/portal/login_warnings.html', {
        'profile': profile,
        'activity': activity,
        'days_inactive': days_inactive,
        'is_inactive': is_inactive,
        'warning_stage': warning_stage,
        'warning_label': warning_label,
        'warning_notifications': warning_notifications,
        'last_checkin': last_checkin,
        'agency_phone': agency_phone,
        'threshold_days': OFWActivity.INACTIVE_THRESHOLD_DAYS,
        'page_title': 'Login Warnings',
        'page_pretitle': 'Account Activity',
    })


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


@login_required(login_url='login')
def portal_emergency_alerts(request):
    """OFW views their own emergency alerts."""
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    if profile is None:
        messages.info(request, 'Please complete your profile first.')
        return redirect('ofw:portal_profile')

    alerts = EmergencyAlert.objects.filter(ofw=profile).order_by('-created_at')
    active_alerts = alerts.exclude(status=EmergencyAlert.Status.RESOLVED)
    latest_ping = _latest_ping(profile)
    nearest_places = _safety_places(profile, latest_ping=latest_ping, limit=3)

    return render(request, 'ofw/portal/emergency_alerts.html', {
        'profile': profile,
        'alerts': alerts,
        'active_alert_count': active_alerts.count(),
        'open_alert': active_alerts.first(),
        'nearest_places': nearest_places,
        'page_title': 'My Emergency Alerts',
    })


@login_required(login_url='login')
def portal_police_reports(request):
    """OFW views police reports and the local police contact for their case."""
    guard = _guard(request)
    if guard:
        return guard

    profile = _profile_for(request.user)
    if profile is None:
        messages.info(request, 'Please complete your profile first.')
        return redirect('ofw:portal_profile')

    reports = PoliceReport.objects.filter(ofw=profile).order_by('-reported_at')
    latest_ping = _latest_ping(profile)
    country = canonical_country(profile.country) if profile.country else ''
    local_hotlines, national_hotlines = _hotlines_for(country)
    police_hotline = _police_hotline(local_hotlines, national_hotlines)
    nearest_station = _nearest_police_station(profile, latest_ping=latest_ping)
    agency_phone = (
        profile.agency_org.phone
        if profile.agency_org_id and profile.agency_org.phone else ''
    )

    return render(request, 'ofw/portal/police_reports.html', {
        'profile': profile,
        'reports': reports,
        'latest_report': reports.first(),
        'latest_ping': latest_ping,
        'police_hotline': police_hotline,
        'nearest_station': nearest_station,
        'agency_phone': agency_phone,
        'location_country': country,
        'page_title': 'Police Contact',
        'page_pretitle': 'OFW Portal',
    })
