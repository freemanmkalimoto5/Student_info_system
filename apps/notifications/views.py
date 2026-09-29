from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.accounts.decorators import admin_required   # matches the decorator used elsewhere in this project
from .models import Notification


@admin_required
def notification_list(request):
    pending = Notification.objects.filter(status='pending')
    fixed = Notification.objects.filter(status='fixed')[:50]   # most recent 50 only
    return render(request, 'notifications/list.html', {
        'pending': pending,
        'fixed': fixed,
        'pending_count': pending.count(),
    })


@admin_required
@require_POST
def mark_fixed(request, pk):
    notif = get_object_or_404(Notification, pk=pk)
    notif.mark_fixed(request.user)
    messages.success(request, "Notification marked as fixed.")
    return redirect('notifications:list')
