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


def notify_system_issue(title, message):
    """
    Create a pending 'system_check' notification -- but only if a PENDING
    one with the exact same title doesn't already exist, so re-running the
    check every day doesn't spam the list with the same unresolved issue.
    """
    try:
        already_open = Notification.objects.filter(
            notif_type='system_check', title=title, status='pending'
        ).exists()
        if not already_open:
            Notification.objects.create(notif_type='system_check', title=title, message=message)
    except Exception as exc:
        print("NOTIFICATION ERROR:", exc)
