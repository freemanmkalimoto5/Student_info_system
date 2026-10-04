"""
Looks the database over for things an admin should know about, and files
a Notification for each problem found (skipping ones already pending).
Safe to run often -- read-only, and every individual check is wrapped so
one failing check can't stop the others from running.
"""
from django.utils import timezone

from .services import notify_system_issue


def _check_missing_qr():
    from apps.students.models import Student

    students = (Student.objects.exclude(status='graduated')
               .filter(id_card__isnull=True) | Student.objects.exclude(status='graduated')
               .filter(id_card__qr_image=''))
    students = students.distinct().order_by('student_number')
    if not students:
        return
    numbers = ", ".join(s.student_number for s in students[:25])
    more = f" and {students.count() - 25} more" if students.count() > 25 else ""
    notify_system_issue(
        f"{students.count()} student(s) have no QR code yet",
        f"These students have no ID card / QR image generated: {numbers}{more}.\n"
        f"Open QR Codes and press \"Regenerate QR codes\", or open each student's page."
    )


def _check_expired_not_renewed():
    from apps.students.models import Student

    today = timezone.localdate()
    problem = []
    for s in Student.objects.exclude(status='graduated').select_related('id_card'):
        card = getattr(s, 'id_card', None)
        if card and card.valid_until and card.valid_until < today:
            problem.append(s)
    if not problem:
        return
    numbers = ", ".join(s.student_number for s in problem[:25])
    more = f" and {len(problem) - 25} more" if len(problem) > 25 else ""
    notify_system_issue(
        f"{len(problem)} active student(s) have an EXPIRED card",
        f"These students are still active/suspended but their card's valid_until date "
        f"has already passed (the yearly rollover may not have run): {numbers}{more}.\n"
        f"Check that the 'promote_students' scheduled task is running, then regenerate their QR codes."
    )


def _check_duplicate_numbers():
    from django.db.models import Count
    from apps.students.models import Student

    dupes = (Student.objects.values('student_number')
             .annotate(n=Count('id')).filter(n__gt=1))
    if not dupes:
        return
    numbers = ", ".join(d['student_number'] for d in dupes[:25])
    notify_system_issue(
        f"{len(dupes)} student_number value(s) are used more than once",
        f"These student numbers appear on more than one student record, which should "
        f"never happen: {numbers}.\nThis can break QR verification -- check these students manually."
    )


def _check_stuck_imports():
    from datetime import timedelta
    from apps.students.models import ImportJob

    cutoff = timezone.now() - timedelta(hours=2)
    stuck = ImportJob.objects.filter(status='processing', created_at__lt=cutoff)
    if not stuck:
        return
    ids = ", ".join(f"#{j.pk}" for j in stuck[:25])
    notify_system_issue(
        f"{stuck.count()} import job(s) seem stuck",
        f"These CSV/Excel import jobs have been \"processing\" for over 2 hours, which "
        f"usually means the background thread crashed or the server restarted mid-import: {ids}.\n"
        f"Check whether the students from that file were actually created, then re-import if needed."
    )


CHECKS = [
    _check_missing_qr,
    _check_expired_not_renewed,
    _check_duplicate_numbers,
    _check_stuck_imports,
]


def run_system_checks():
    """Runs every check; a failing one is printed and skipped, never raised."""
    ran, failed = 0, 0
    for check in CHECKS:
        try:
            check()
            ran += 1
        except Exception as exc:
            print("SYSTEM CHECK ERROR:", check.__name__, exc)
            failed += 1
    return ran, failed
