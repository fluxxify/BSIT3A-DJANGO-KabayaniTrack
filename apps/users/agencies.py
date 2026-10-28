"""Helpers for resolving the agency attached to a management account."""

from .models import Agency


def agency_for_user(user):
    """Return the active agency assigned to ``user``, or ``None``.

    Superusers are intentionally global.  Legacy staff accounts that have no
    ``AgencyStaff`` row also keep the old global view so existing installations
    continue to work.
    """
    if not getattr(user, 'is_authenticated', False):
        return None
    if user.is_superuser:
        return None
    staff = getattr(user, 'agency_staff', None)
    if staff is None:
        return None
    agency = staff.agency
    return agency if agency and agency.is_active else None


def is_agency_staff(user):
    return agency_for_user(user) is not None


def active_agencies():
    return Agency.objects.filter(is_active=True)
