from django.shortcuts import get_object_or_404

from apps.info.models import Info


def scoped_infos(user):
    """Info records visible to the user: everything for management, own for OFWs."""
    if user.is_superuser or user.is_staff:
        return Info.objects.all()
    return Info.objects.filter(user=user)


def scoped_info(user, pk):
    return get_object_or_404(scoped_infos(user), pk=pk)
