from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.accounts.decorators import admin_required
from .models import Notification
from .system_checks import run_system_checks


@admin_required
def notification_list(request):
    pending = Notification.objects.filter(status='pending')
    fixed = Notification.objects.filter(status='fixed')[:50]
    return render(request, 'notifications/list.html', {
        'pending': pending,
        'fixed': fixed,
        'pending_count': pending.count(),
        'fixed_count': Notification.objects.filter(status='fixed').count(),
    })


@admin_required
@require_POST
def mark_fixed(request, pk):
    notif = get_object_or_404(Notification, pk=pk)
    notif.mark_fixed(request.user)
    messages.success(request, "Notification marked as fixed.")
    return redirect('notifications:list')


@admin_required
@require_POST
def mark_all_fixed(request):
    """Bulk-resolve every pending notification at once (e.g. after
    re-checking a batch of 'possible duplicate' warnings)."""
    pending = Notification.objects.filter(status='pending')
    count = pending.count()
    for notif in pending:
        notif.mark_fixed(request.user)
    if count:
        messages.success(request, f"Marked {count} pending notification(s) as fixed.")
    else:
        messages.info(request, "There was nothing pending to mark as fixed.")
    return redirect('notifications:list')


@admin_required
@require_POST
def clear_fixed(request):
    """Deletes every notification already marked as Fixed. Pending
    notifications are never touched by this button."""
    count, _ = Notification.objects.filter(status='fixed').delete()
    if count:
        messages.success(request, f"Cleared {count} fixed notification(s).")
    else:
        messages.info(request, "There were no fixed notifications to clear.")
    return redirect('notifications:list')


@admin_required
@require_POST
def run_checks(request):
    """Scans the system for problems right now and files a notification
    for anything found (skipping issues already pending)."""
    ran, failed = run_system_checks()
    if failed:
        messages.warning(request, f"Ran {ran} check(s), {failed} failed -- see the server log.")
    else:
        messages.success(request, f"Ran {ran} system check(s). Any new problems are listed below.")
    return redirect('notifications:list')
