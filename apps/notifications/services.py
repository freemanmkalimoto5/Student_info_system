from .models import Notification


def notify_duplicate(title, message, existing_student=None):
    """Create a pending duplicate-student notification. Never raises -- a
    notification failing to save should never block registration/import."""
    try:
        Notification.objects.create(
            notif_type='duplicate_student',
            title=title,
            message=message,
            existing_student=existing_student,
        )
    except Exception as exc:
        print("NOTIFICATION ERROR:", exc)
