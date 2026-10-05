"""
The system scan behind the "Run system check" button.

Every check looks at the REAL system (settings, database, files, WhatsApp
server, accounts) and returns either None (all fine) or a message that says
what is wrong and how to fix it. The scan then:

  * raises a notification for a problem that is new,
  * refreshes the details of a problem that is already pending,
  * closes a pending notification automatically once the problem is gone,
  * stays quiet about settings-type problems (snooze) for a while after a
    person marked them as fixed, so the same thing is not nagged every time.

If a scan finds nothing new, the page says
"No new notification from the system."

Checks are grouped by the prefix of their title: Security / System / Data.
Every check is read-only, except that interrupted bulk imports are closed as
failed (they can never finish) so they stop being reported again and again.
One check failing never stops the others.
"""
import os
from collections import namedtuple
from datetime import date, timedelta

from django.conf import settings
from django.utils import timezone

from .services import notify_system_issue, resolve_system_issue

Check = namedtuple('Check', 'title func snooze_days auto_resolve')


def _list(items, limit=20):
    items = [str(i) for i in items]
    text = ", ".join(items[:limit])
    extra = len(items) - limit
    return text + (f" and {extra} more" if extra > 0 else "")


# ======================================================================
# SECURITY
# ======================================================================
def check_secret_key():
    key = getattr(settings, 'SECRET_KEY', '') or ''
    if len(key) >= 50 and len(set(key)) >= 5 and not key.startswith('django-insecure-'):
        return None
    return (
        "The SECRET_KEY in your .env file is short, simple, or still the sample key Django "
        "generated. It signs login sessions and password-reset links, so a guessable key "
        "lets an attacker forge them.\n"
        "Generate a long random one (50+ characters) and put it in .env as SECRET_KEY."
    )


def check_debug_exposed():
    if not settings.DEBUG:
        return None
    local = {'', '127.0.0.1', 'localhost', '[::1]', '::1'}
    exposed = [h.strip() for h in settings.ALLOWED_HOSTS if h.strip() not in local]
    if not exposed:
        return None
    return (
        f"DEBUG is ON while the system answers to: {_list(exposed, 5)}.\n"
        "Anyone on the network who causes an error is shown file paths, settings and code.\n"
        "Use config.settings.production (DEBUG=False) whenever other people use the system."
    )


def check_allowed_hosts():
    if '*' not in settings.ALLOWED_HOSTS:
        return None
    return (
        "ALLOWED_HOSTS contains \"*\", so the system accepts requests for any website name. "
        "That opens it to host-header attacks.\nList only the real addresses, "
        "e.g. ALLOWED_HOSTS=school.example.com,192.168.1.20 in .env."
    )


def check_https_settings():
    if settings.DEBUG:
        return None            # local/testing: HTTPS protections are not expected
    missing = [name for name in ('SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE')
               if not getattr(settings, name, False)]
    if not missing:
        return None
    return (
        f"These protections are off: {', '.join(missing)}.\n"
        "Without them, logins and session cookies can travel over plain HTTP where they can be "
        "intercepted. Serve the site over HTTPS and turn them on (config.settings.production does)."
    )


def check_database_account():
    db = settings.DATABASES.get('default', {})
    problems = []
    if (db.get('USER') or '').lower() == 'root':
        problems.append("the app connects to MySQL as the all-powerful 'root' user")
    if not db.get('PASSWORD'):
        problems.append("the database password is empty")
    if not problems:
        return None
    return (
        "Database login is unsafe: " + " and ".join(problems) + ".\n"
        "If the app is ever compromised, the attacker gets the whole MySQL server. Create a "
        "dedicated MySQL user with a strong password that only has access to this database, "
        "and put it in .env (DB_USER / DB_PASSWORD)."
    )


def check_guessable_usernames():
    from django.contrib.auth.models import User
    common = {'admin', 'administrator', 'root', 'superuser', 'test', 'user', 'demo', 'staff'}
    bad = [u.username for u in User.objects.filter(is_staff=True, is_active=True)
           if u.username.lower() in common]
    if not bad:
        return None
    return (
        f"These accounts with admin access have a very common username: {_list(bad)}.\n"
        "Attackers try these names first. Create a new account with a personal username, "
        "then disable the old one."
    )


def check_dormant_staff():
    from django.contrib.auth.models import User
    now = timezone.now()
    stale = []
    for u in User.objects.filter(is_staff=True, is_active=True).order_by('username'):
        if u.last_login is None:
            if u.date_joined < now - timedelta(days=14):
                stale.append(f"{u.username} (never logged in)")
        elif u.last_login < now - timedelta(days=90):
            stale.append(f"{u.username} (last login {u.last_login:%d %b %Y})")
    if not stale:
        return None
    return (
        f"These staff accounts still have access but are not being used: {_list(stale)}.\n"
        "Unused accounts are an easy way in. If the person has left, disable the account "
        "(Django admin > Users > untick Active)."
    )


def check_superuser_count():
    from django.contrib.auth.models import User
    count = User.objects.filter(is_superuser=True, is_active=True).count()
    if count <= 3:
        return None
    return (
        f"There are {count} active superuser accounts. Superusers can do everything, including "
        "deleting the audit log and money records.\nKeep as few as possible and give everyone "
        "else the Admin or Clerk role."
    )


# ======================================================================
# SYSTEM
# ======================================================================
def check_database_schema():
    from django.apps import apps
    from django.db import connection
    from django.db.migrations.autodetector import MigrationAutodetector
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.state import ProjectState

    executor = MigrationExecutor(connection)
    problems = []

    plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
    if plan:
        names = [f"{migration.app_label}.{migration.name}" for migration, _backwards in plan]
        problems.append(
            f"{len(names)} migration(s) have not been applied to the database: {_list(names, 8)}.\n"
            "Run: python manage.py migrate"
        )

    try:
        autodetector = MigrationAutodetector(executor.loader.project_state(), ProjectState.from_apps(apps))
        changes = autodetector.changes(graph=executor.loader.graph)
        if changes:
            problems.append(
                "The code has model changes that have no migration yet (apps: "
                + ", ".join(sorted(changes)) + ").\nRun: python manage.py makemigrations, "
                "then python manage.py migrate"
            )
    except SystemExit:
        problems.append(
            "The code has model changes that need a migration (a new required field needs a default).\n"
            "Run: python manage.py makemigrations, then python manage.py migrate"
        )

    return "\n\n".join(problems) if problems else None


def check_stuck_imports():
    from apps.students.models import ImportJob

    cutoff = timezone.now() - timedelta(hours=2)
    stuck = list(ImportJob.objects.filter(status__in=['pending', 'processing'], created_at__lt=cutoff))
    if not stuck:
        return None
    ids = [f"#{job.pk}" for job in stuck]
    # A background import cannot survive a server restart, so these can never finish.
    # Close them so they are reported once, not on every scan.
    ImportJob.objects.filter(pk__in=[job.pk for job in stuck]).update(
        status='failed',
        error_message='Interrupted: the server restarted or the import crashed before it finished.',
        finished_at=timezone.now(),
    )
    return (
        f"These bulk imports never finished: {_list(ids)}. They were interrupted, usually because the "
        "server restarted or crashed while importing.\nThey have now been closed as failed so they "
        "are not reported again.\nCheck whether the students from those files were created, and "
        "re-import the missing ones."
    )


def check_disk_space():
    import shutil
    path = str(settings.MEDIA_ROOT)
    if not os.path.exists(path):
        path = str(settings.BASE_DIR)
    usage = shutil.disk_usage(path)
    free_gb = usage.free / (1024 ** 3)
    percent = usage.free * 100 / usage.total
    if free_gb >= 1 and percent >= 10:
        return None
    return (
        f"Only {free_gb:.1f} GB ({percent:.0f}%) is free on the disk that holds the media folder.\n"
        "When it fills up, new photos and QR codes cannot be saved. Free some space or move the media folder."
    )


def check_media_files():
    from apps.qrcodes.models import IDCard
    from apps.students.models import Student

    missing_qr, missing_photo = [], []
    cards = (IDCard.objects.filter(qr_image__isnull=False).exclude(qr_image='')
             .select_related('student')[:5000])
    for card in cards:
        try:
            if not os.path.exists(card.qr_image.path):
                missing_qr.append(card.student.student_number)
        except Exception:
            continue
    for student in Student.objects.filter(photo__isnull=False).exclude(photo='')[:5000]:
        try:
            if not os.path.exists(student.photo.path):
                missing_photo.append(student.student_number)
        except Exception:
            continue

    parts = []
    if missing_qr:
        parts.append(f"{len(missing_qr)} QR image file(s) are recorded but missing from disk: {_list(missing_qr)}.\n"
                     "Press \"Regenerate QR codes\" to rebuild them.")
    if missing_photo:
        parts.append(f"{len(missing_photo)} student photo file(s) are recorded but missing from disk: "
                     f"{_list(missing_photo)}.\nRe-upload those photos.")
    if not parts:
        return None
    return "\n\n".join(parts) + "\nThis usually happens when the media folder was moved, cleaned, or not copied during a backup restore."


def check_whatsapp_connection():
    base = getattr(settings, 'WAHA_BASE_URL', '')
    if not base:
        return None                      # reported separately by check_whatsapp_off
    try:
        import requests
    except ImportError:
        return "The 'requests' package is not installed, so WhatsApp messages cannot be sent.\nRun: pip install requests"

    headers = {}
    api_key = getattr(settings, 'WAHA_API_KEY', '')
    if api_key:
        headers['X-Api-Key'] = api_key

    try:
        response = requests.get(base.rstrip('/') + '/api/sessions', headers=headers, timeout=3)
    except Exception as exc:
        return (f"The WhatsApp server (WAHA) at {base} cannot be reached ({exc.__class__.__name__}).\n"
                "Parents are not receiving WhatsApp messages. Check that Docker is running and the WAHA container is started.")

    if response.status_code in (401, 403):
        return "WAHA refused the API key. Check WAHA_API_KEY in .env matches the key WAHA was started with."
    if response.status_code >= 400:
        return f"WAHA answered with an error (HTTP {response.status_code}). Check the WAHA container logs."

    try:
        sessions = response.json()
    except ValueError:
        return None
    wanted = getattr(settings, 'WAHA_SESSION', 'default')
    if isinstance(sessions, list):
        for session in sessions:
            if isinstance(session, dict) and session.get('name') == wanted:
                status = session.get('status')
                if status and status != 'WORKING':
                    return (f"The WhatsApp session '{wanted}' is not connected (status: {status}).\n"
                            "Open the WAHA dashboard and scan the QR code with the school's WhatsApp again.")
                return None
        return f"WAHA is running but has no session called '{wanted}'. Start it from the WAHA dashboard."
    return None


def check_whatsapp_off():
    if getattr(settings, 'WAHA_BASE_URL', ''):
        return None
    return (
        "WAHA_BASE_URL is empty, so WhatsApp messages (parent login details, pocket money updates, "
        "lost-item reports) are NOT being sent. The system keeps working, but parents get nothing.\n"
        "Start WAHA and set WAHA_BASE_URL in the .env file to switch them on."
    )


def check_rollover():
    from apps.students.models import RolloverLog, Student

    first = Student.objects.order_by('created_at').values_list('created_at', flat=True).first()
    if first is None:
        return None
    first_day = timezone.localtime(first).date()
    today = timezone.localdate()

    missed = []
    for event, month, label in (('january', 1, 'January'), ('june', 6, 'June')):
        due = date(today.year, month, 2)               # the task runs on the 1st; allow a day of slack
        had_students_then = first_day < date(today.year, month, 1)
        if today >= due and had_students_then and not RolloverLog.objects.filter(event=event, year=today.year).exists():
            missed.append(f"{label} {today.year}")
    if not missed:
        return None
    return (
        f"The automatic class promotion has not run for: {', '.join(missed)}.\n"
        "Students are still in their old class and their ID cards keep the old expiry date.\n"
        "Run python manage.py promote_students now, and make sure the scheduled task that runs it every day is working."
    )


def check_temporary_numbers():
    from apps.students.models import Student
    rows = list(Student.objects.filter(student_number__startswith='TMP-').order_by('last_name', 'first_name'))
    if not rows:
        return None
    names = [s.full_name for s in rows]
    return (
        f"{len(rows)} student(s) still have a temporary number (TMP-...) because numbering did not finish: {_list(names)}.\n"
        "Open any student, press Save, and the whole school is renumbered."
    )


# ======================================================================
# DATA
# ======================================================================
def check_duplicate_numbers():
    from django.db.models import Count
    from apps.students.models import Student
    dupes = list(Student.objects.order_by('student_number').values('student_number')
                 .annotate(n=Count('id')).filter(n__gt=1))
    if not dupes:
        return None
    return (
        f"{len(dupes)} student number(s) are used by more than one student: {_list([d['student_number'] for d in dupes])}.\n"
        "This should never happen and can break QR verification. Check these students and save one of them to renumber."
    )


def check_missing_qr():
    from django.db.models import Q
    from apps.students.models import Student
    numbers = list(
        Student.objects.exclude(status='graduated')
        .filter(Q(id_card__isnull=True) | Q(id_card__qr_image='') | Q(id_card__qr_image__isnull=True))
        .order_by('student_number').values_list('student_number', flat=True)
    )
    if not numbers:
        return None
    return (
        f"{len(numbers)} student(s) have no QR code image yet: {_list(numbers)}.\n"
        "Open QR Codes and press \"Regenerate QR codes\", or open each student's page."
    )


def check_expired_cards():
    from apps.students.models import Student
    today = timezone.localdate()
    numbers = list(
        Student.objects.exclude(status='graduated').filter(id_card__valid_until__lt=today)
        .order_by('student_number').values_list('student_number', flat=True)
    )
    if not numbers:
        return None
    return (
        f"{len(numbers)} student(s) are still at school but their ID card has expired: {_list(numbers)}.\n"
        "The yearly promotion may not have run. Check the scheduled 'promote_students' task, then regenerate their QR codes."
    )


def check_pocket_money():
    from django.db.models import Case, DecimalField, F, Sum, When
    from apps.pocketmoney.models import Transaction
    from apps.students.models import Student

    balances = (
        Transaction.objects.order_by().values('student_id')
        .annotate(balance=Sum(Case(
            When(transaction_type='deposit', then=F('amount')),
            When(transaction_type='withdrawal', then=-F('amount')),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )))
    )
    negative_ids = [row['student_id'] for row in balances if row['balance'] is not None and row['balance'] < 0]
    bad_amounts = Transaction.objects.filter(amount__lte=0).count()

    parts = []
    if negative_ids:
        numbers = Student.objects.filter(pk__in=negative_ids).values_list('student_number', flat=True)
        parts.append(f"{len(negative_ids)} student(s) have a NEGATIVE pocket money balance: {_list(numbers)}.")
    if bad_amounts:
        parts.append(f"{bad_amounts} transaction(s) have an amount of zero or less.")
    if not parts:
        return None
    return "\n".join(parts) + "\nBalances are worked out from the transaction history, so check those students' transactions."


def check_parent_logins():
    from django.db.models import Q
    from apps.students.models import Student

    def has(name, phone):
        return (Q(**{f'{name}__isnull': False}) & Q(**{f'{phone}__isnull': False})
                & ~Q(**{name: ''}) & ~Q(**{phone: ''}))

    rows = list(
        Student.objects.filter(parent_accounts__isnull=True)
        .filter(has('father_name', 'father_phone') | has('mother_name', 'mother_phone') | has('guardian_name', 'guardian_phone'))
        .exclude(status='graduated').order_by('student_number')
    )
    if not rows:
        return None
    return (
        f"{len(rows)} student(s) have a parent name and phone number but no parent login, so the parent cannot sign in: "
        f"{_list([s.student_number for s in rows])}.\nOpen the student and press Save to create the login."
    )


def check_no_contact():
    from django.db.models import Q
    from apps.students.models import Student

    def blank(field):
        return Q(**{f'{field}__isnull': True}) | Q(**{field: ''})

    numbers = list(
        Student.objects.exclude(status__in=['graduated', 'transferred'])
        .filter(blank('father_phone'), blank('mother_phone'), blank('guardian_phone'))
        .order_by('student_number').values_list('student_number', flat=True)
    )
    if not numbers:
        return None
    return (
        f"{len(numbers)} student(s) have no parent or guardian phone number at all: {_list(numbers)}.\n"
        "Nobody can be reached for them, and no WhatsApp or parent login is possible."
    )


def check_missing_photos():
    from django.db.models import Q
    from apps.students.models import Student
    numbers = list(
        Student.objects.exclude(status__in=['graduated', 'transferred'])
        .filter(Q(photo='') | Q(photo__isnull=True))
        .order_by('student_number').values_list('student_number', flat=True)
    )
    if not numbers:
        return None
    return (
        f"{len(numbers)} student(s) have no photo: {_list(numbers)}.\n"
        "Their ID cards and the scan page show no picture. Add a photo from the student's Edit page."
    )


def check_birth_dates():
    from apps.students.models import Student
    today = timezone.localdate()
    odd = []
    rows = (Student.objects.exclude(status='graduated').order_by('student_number')
            .values_list('student_number', 'date_of_birth'))
    for number, dob in rows:
        age = Student.calculate_age(dob)
        if dob > today or age < 9 or age > 25:
            odd.append(f"{number} (born {dob:%d %b %Y})")
    if not odd:
        return None
    return (
        f"{len(odd)} student(s) have a date of birth that looks wrong (in the future, or younger than 9 / older than 25): {_list(odd)}.\n"
        "Check for typing mistakes such as the wrong year."
    )


# ======================================================================
# REGISTRY + SCAN
# ======================================================================
def _c(title, func, snooze_days=0, auto_resolve=True):
    return Check(title, func, snooze_days, auto_resolve)


CHECKS = [
    # ---- security ----
    _c("Security: Weak secret key", check_secret_key, snooze_days=30),
    _c("Security: Debug mode is on while the system is open to the network", check_debug_exposed, snooze_days=14),
    _c("Security: Every host is allowed", check_allowed_hosts, snooze_days=30),
    _c("Security: HTTPS protections are switched off", check_https_settings, snooze_days=14),
    _c("Security: Database account is unsafe", check_database_account, snooze_days=30),
    _c("Security: Admin account with a guessable username", check_guessable_usernames, snooze_days=30),
    _c("Security: Unused staff accounts still have access", check_dormant_staff, snooze_days=14),
    _c("Security: Too many superuser accounts", check_superuser_count, snooze_days=30),
    # ---- system ----
    _c("System: Database is out of date", check_database_schema),
    _c("System: Bulk imports were interrupted", check_stuck_imports, auto_resolve=False),
    _c("System: Disk space is running low", check_disk_space),
    _c("System: Files are missing from the media folder", check_media_files),
    _c("System: WhatsApp (WAHA) is not working", check_whatsapp_connection),
    _c("System: WhatsApp messages are switched off", check_whatsapp_off, snooze_days=30),
    _c("System: Yearly class promotion did not run", check_rollover),
    _c("System: Students with temporary numbers", check_temporary_numbers),
    # ---- data ----
    _c("Data: Duplicate student numbers", check_duplicate_numbers),
    _c("Data: Students without a QR code", check_missing_qr),
    _c("Data: Active students with an expired card", check_expired_cards),
    _c("Data: Pocket money does not add up", check_pocket_money),
    _c("Data: Parents without a login", check_parent_logins),
    _c("Data: Students with no parent phone number", check_no_contact, snooze_days=7),
    _c("Data: Students without a photo", check_missing_photos, snooze_days=7),
    _c("Data: Suspicious dates of birth", check_birth_dates, snooze_days=7),
]


def scan_system():
    """
    Runs every check. Returns
      {'ran': int, 'failed': [titles], 'new': int, 'new_titles': [...],
       'resolved': int, 'open': int}
    where 'new' = notifications created by THIS scan.
    """
    ran, failed = 0, []
    new_titles, resolved, still_open = [], 0, 0

    for check in CHECKS:
        try:
            message = check.func()
        except (Exception, SystemExit) as exc:      # one broken check must never stop the scan
            print("SYSTEM CHECK ERROR:", check.title, repr(exc))
            failed.append(check.title)
            continue
        ran += 1

        if message:
            outcome = notify_system_issue(check.title, message, snooze_days=check.snooze_days)
            if outcome == 'new':
                new_titles.append(check.title)
            elif outcome in ('updated', 'known'):
                still_open += 1
        elif check.auto_resolve:
            resolved += resolve_system_issue(check.title)

    return {
        'ran': ran,
        'failed': failed,
        'new': len(new_titles),
        'new_titles': new_titles,
        'resolved': resolved,
        'open': still_open,
    }


def run_system_checks():
    """Older entry point: returns (checks_run, checks_failed)."""
    result = scan_system()
    return result['ran'], len(result['failed'])
