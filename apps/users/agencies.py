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


def has_agency_assignment(user):
    """True when the account is linked to an AgencyStaff row.

    This is deliberately separate from ``agency_for_user``: an inactive agency
    still has an assignment, but returns ``None`` from ``agency_for_user``.  A
    deactivated agency must never fall back to the global management view.
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return False
    return getattr(user, 'agency_staff', None) is not None


def is_global_staff(user):
    """True only for superusers or legacy staff with no agency assignment."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser:
        return True
    return bool(user.is_staff and not has_agency_assignment(user))


def is_agency_staff(user):
    return agency_for_user(user) is not None


def active_agencies():
    return Agency.objects.filter(is_active=True)
