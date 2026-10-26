"""Views for the shared in-app notification centre."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Notification

PER_PAGE = 20

_LEVEL_META = {
    Notification.Level.INFO: ('fas fa-circle-info', 'text-azure', 'bg-azure-lt'),
    Notification.Level.SUCCESS: ('fas fa-circle-check', 'text-success', 'bg-success-lt'),
    Notification.Level.WARNING: ('fas fa-triangle-exclamation', 'text-warning', 'bg-warning-lt'),
    Notification.Level.DANGER: ('fas fa-circle-exclamation', 'text-danger', 'bg-danger-lt'),
}


def _back_url(request):
    """Return a safe next URL, falling back to the notification centre."""
    next_url = request.POST.get('next') or request.GET.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse('ofw:notifications')


@login_required(login_url='login')
def notifications_page(request):
    queryset = Notification.objects.filter(recipient=request.user)
    unread_count = queryset.filter(is_read=False).count()

    only_unread = request.GET.get('filter') == 'unread'
    if only_unread:
        queryset = queryset.filter(is_read=False)

    paginator = Paginator(queryset, PER_PAGE)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    rows = []
    for notification in page_obj.object_list:
        icon, icon_class, background = _LEVEL_META.get(
            notification.level,
            _LEVEL_META[Notification.Level.INFO],
        )
        rows.append({
            'obj': notification,
            'icon': icon,
            'icon_class': icon_class,
            'background': background,
        })

    return render(request, 'ofw/notifications.html', {
        'rows': rows,
        'page_obj': page_obj,
        'unread_count': unread_count,
        'only_unread': only_unread,
        'total_count': Notification.objects.filter(recipient=request.user).count(),
    })


@login_required(login_url='login')
def notification_open(request, pk):
    notification = get_object_or_404(
        Notification, pk=pk, recipient=request.user,
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])

    target = notification.url
    if target and url_has_allowed_host_and_scheme(
        target,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(target)
    return redirect('ofw:notifications')


@login_required(login_url='login')
@require_POST
def notification_mark_read(request, pk):
    notification = get_object_or_404(
        Notification, pk=pk, recipient=request.user,
    )
    if not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=['is_read'])
    return redirect(_back_url(request))


@login_required(login_url='login')
@require_POST
def notifications_mark_all_read(request):
    updated = Notification.objects.filter(
        recipient=request.user, is_read=False,
    ).update(is_read=True)
    if updated:
        messages.success(request, f'Marked {updated} notification{"s" if updated != 1 else ""} as read.')
    else:
        messages.info(request, 'You have no unread notifications.')
    return redirect(_back_url(request))


@login_required(login_url='login')
@require_POST
def notification_delete(request, pk):
    notification = get_object_or_404(
        Notification, pk=pk, recipient=request.user,
    )
    notification.delete()
    messages.success(request, 'Notification deleted successfully.')
    return redirect(_back_url(request))


@login_required(login_url='login')
@require_POST
def notifications_delete_all(request):
    queryset = Notification.objects.filter(recipient=request.user)
    count = queryset.count()
    if count == 0:
        messages.info(request, 'No notifications to delete.')
        return redirect(_back_url(request))
    queryset.delete()
    messages.success(request, f'All notifications ({count}) have been deleted successfully.')
    return redirect(_back_url(request))
