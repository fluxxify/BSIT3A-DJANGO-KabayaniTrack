"""Role helpers for separating OFW accounts from the management console.

Self-registered accounts are OFW users: they are authenticated, not staff and
not superusers.  Management users (administrators and staff) keep the full
console and can see every record.
"""

from django.contrib.auth.models import Group

OFW_GROUP_NAME = 'OFW'


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


def mark_as_ofw(user):
    """Tag a user as an OFW by adding them to the OFW group."""
    group, _ = Group.objects.get_or_create(name=OFW_GROUP_NAME)
    user.groups.add(group)
    return group
