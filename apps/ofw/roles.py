"""Role helpers for separating OFW accounts from the management console.

Self-registered accounts are OFW users: they are authenticated, not staff and
not superusers.  Management users (administrators and staff) keep the full
console and can see every record.
"""

from django.contrib.auth.models import Group

OFW_GROUP_NAME = 'OFW'

ACCOUNT_ADMIN = 'admin'
ACCOUNT_OFW = 'ofw'
ACCOUNT_STAFF = 'staff'

ACCOUNT_TYPE_CHOICES = [
    (ACCOUNT_ADMIN, 'Administrator'),
    (ACCOUNT_OFW, 'OFW'),
    (ACCOUNT_STAFF, 'Staff'),
]


def account_role(user):
    """Return the account-type key ('admin', 'staff' or 'ofw') for a user."""
    if user.is_superuser:
        return ACCOUNT_ADMIN
    if user.is_staff:
        return ACCOUNT_STAFF
    return ACCOUNT_OFW


def account_role_label(role):
    """Return the human-readable label for an account-type key."""
    return dict(ACCOUNT_TYPE_CHOICES).get(role, 'account')


def is_ofw(user):
    """Return True when the user should land in the OFW self-service portal."""
    if not getattr(user, 'is_authenticated', False):
        return False
    if user.is_superuser or user.is_staff:
        return False
    return True


def is_management(user):
    """Return True when the user belongs to the management console."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return user.is_superuser or user.is_staff


def can_access_info(user):
    """Info records: administrators see all, OFWs see their own, staff is blocked."""
    if not getattr(user, 'is_authenticated', False):
        return False
    return user.is_superuser or not user.is_staff


def mark_as_ofw(user):
    """Tag a user as an OFW by adding them to the OFW group."""
    group, _ = Group.objects.get_or_create(name=OFW_GROUP_NAME)
    user.groups.add(group)
    return group
