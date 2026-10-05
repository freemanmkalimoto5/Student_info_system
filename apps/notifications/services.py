from datetime import timedelta

from django.utils import timezone

from .models import Notification


def notify_duplicate(title, message, existing_student=None):
    """Create a pending duplicate-student notification. Never raises."""
    try:
        Notification.objects.create(
            notif_type='duplicate_student',
            title=title,
            message=message,
            existing_student=existing_student,
        )
    except Exception as exc:
        print("NOTIFICATION ERROR:", exc)


def notify_system_issue(title, message, snooze_days=0):
    """
    Raise (or refresh) a 'system_check' notification. Never raises.

    Returns what happened, so the scan can tell the admin honestly:
      'new'      a notification was created
      'updated'  the same problem was already pending; its details were refreshed
      'known'    already pending, nothing changed
      'snoozed'  a person marked this same problem as fixed less than
                 `snooze_days` ago, so it is not raised again yet
      'error'    could not be saved
    """
    try:
        pending = Notification.objects.filter(
            notif_type='system_check', title=title, status='pending'
        ).first()
        if pending is not None:
            if pending.message != message:
                pending.message = message
                pending.save(update_fields=['message'])
                return 'updated'
            return 'known'

        if snooze_days:
            since = timezone.now() - timedelta(days=snooze_days)
            acknowledged = Notification.objects.filter(
                notif_type='system_check', title=title, status='fixed', fixed_at__gte=since
            ).exclude(fixed_by=None)          # only fixes made by a person count
            if acknowledged.exists():
                return 'snoozed'

        Notification.objects.create(notif_type='system_check', title=title, message=message)
        return 'new'
    except Exception as exc:
        print("NOTIFICATION ERROR:", exc)
        return 'error'


def resolve_system_issue(title):
    """The scan no longer finds this problem: close any pending notification for it.
    Returns how many were closed. Never raises."""
    try:
        pending = Notification.objects.filter(
            notif_type='system_check', title=title, status='pending'
        )
        count = pending.count()
        if count:
            pending.update(status='fixed', fixed_at=timezone.now())   # fixed_by stays empty = "automatically"
        return count
    except Exception as exc:
        print("NOTIFICATION ERROR:", exc)
        return 0
