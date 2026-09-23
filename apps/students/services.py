"""
Student business logic: bulk CSV import and auto-numbering, kept
separate from views.py so they can be reused (management commands,
API endpoints, etc).
"""
import csv
import io
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .models import Student

# Class order used both for the dropdown (see Student.CLASS_CHOICES)
# and here for sorting students when auto-numbering.
CLASS_ORDER = [key for key, _label in Student.CLASS_CHOICES]

VALID_CLASS_KEYS = set(CLASS_ORDER)

# Roman-numeral prefix used in student numbers, e.g. "FI.25" (Form One,
# 25th student), "FIV.2" (Form Four, 2nd student). Each class restarts
# its own numbering at 1 — see renumber_students() below.
CLASS_ABBREVIATIONS = {
    'form one': 'FI',
    'form two': 'FII',
    'form three': 'FIII',
    'form four': 'FIV',
    'form five': 'FV',
    'form six': 'FVI',
}

# student_number is no longer supplied manually — it's assigned by
# renumber_students() based on class + alphabetical order. grade_class
# is required in CSV imports because numbering depends on knowing it.
# initial_pocket_money is handled separately below (not a Student field).
REQUIRED_COLUMNS = ['first_name', 'last_name', 'date_of_birth', 'grade_class']
POCKET_MONEY_COLUMN = 'initial_pocket_money'

OPTIONAL_COLUMNS = [
    'middle_name',
    'status',
    'father_name', 'father_phone', 'father_whatsapp',
    'mother_name', 'mother_phone', 'mother_whatsapp',
    'guardian_name', 'guardian_phone', 'guardian_relationship',
    'parish',
    'full_address', 'region', 'district', 'ward',
]

DATE_FORMATS = ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']


def _parse_date(value):
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _temp_student_number():
    """
    A placeholder unique value used only for the instant between
    creating a Student row (which requires a non-blank unique number)
    and renumber_students() assigning the real, ordered number.
    """
    return f"TMP-{uuid.uuid4().hex[:10]}"


def _regenerate_qr_codes(students):
    """
    Writes a fresh QR image for each student in the list. This is the
    slow part (image generation + disk writes) — kept as its own
    function so it can be run either synchronously or in a background
    thread (see renumber_students).
    """
    from django import db
    from apps.qrcodes.models import IDCard
    from apps.qrcodes.services import generate_id_card_qr

    try:
        for student in students:
            card, _ = IDCard.objects.get_or_create(student=student)
            card.qr_image.save(
                f"qr_{student.student_number}.png",
                generate_id_card_qr(student),
                save=True,
            )
    finally:
        # Only matters when run in a background thread — Django opens
        # a separate DB connection per thread, so close it explicitly
        # once this thread's work is done rather than leaking it.
        db.connections.close_all()


def renumber_students(background_qr=True):
    """
    Re-assigns every student's student_number based on:
      1. Class order: form one, two, three, four, five, six
      2. Alphabetical by first name, then last name, within each class

    Numbers are formatted as CLASS.NUMBER, e.g. "FI.25" (Form One,
    25th student) or "FIV.2" (Form Four, 2nd student) — each class
    restarts its own numbering at 1, rather than one long sequence
    shared across every class.

    Done in TWO PASSES to avoid unique-constraint collisions: if
    student A needs to become "FI.1" while student B currently holds
    "FI.1" (and is about to become "FI.2"), saving A first would crash
    against B's still-current value. So every student is first moved
    to a safe temporary number, then everyone is set to their real
    final number once nothing can collide. This part is always fast
    (plain database updates) regardless of how many students there are.

    Regenerating the actual QR images is the slow part (image drawing
    + disk writes, once per changed student). By default
    (background_qr=True) that work is handed off to a background
    thread so the page responds immediately instead of waiting on it —
    the affected QR images simply finish updating a moment later.
    Management commands / batch jobs pass background_qr=False so they
    wait for it to fully finish before the command exits (a daemon
    thread would otherwise get killed when the process ends).

    Returns the list of Student instances whose number changed.
    """
    order_index = {key: i for i, key in enumerate(CLASS_ORDER)}

    all_students = list(Student.objects.all())
    all_students.sort(
        key=lambda s: (
            order_index.get(s.grade_class, len(CLASS_ORDER)),  # unknown classes sort last
            s.first_name.lower(),
            s.last_name.lower(),
        )
    )

    # Work out final numbers first, without touching the database yet.
    # Each class gets its own counter, restarting at 1.
    final_numbers = {}
    class_counters = {}
    for student in all_students:
        prefix = CLASS_ABBREVIATIONS.get(
            student.grade_class,
            student.grade_class.upper().replace(' ', '')  # fallback for an unrecognized class
        )
        class_counters[prefix] = class_counters.get(prefix, 0) + 1
        final_numbers[student.pk] = f"{prefix}.{class_counters[prefix]}"

    needs_change = [s for s in all_students if s.student_number != final_numbers[s.pk]]

    # Pass 1: move everyone who needs to change onto a unique temporary
    # value, clearing the "FI.1", "FI.2"... namespace entirely.
    for student in needs_change:
        student.student_number = f"TMP-{student.pk}"
        student.save(update_fields=['student_number'])

    # Pass 2: now safely assign the real final numbers — no collisions
    # possible since nothing currently holds a plain numeric value.
    changed = []
    for student in needs_change:
        student.student_number = final_numbers[student.pk]
        student.save(update_fields=['student_number'])
        changed.append(student)

    if changed:
        if background_qr:
            import threading
            threading.Thread(target=_regenerate_qr_codes, args=(changed,), daemon=True).start()
        else:
            _regenerate_qr_codes(changed)

    return changed


def _parse_and_validate_rows(decoded_csv_text):
    """
    Parses the CSV text and validates every row, WITHOUT touching the
    database yet. Returns (valid_rows, skipped_details, error) where
    valid_rows is a list of dicts: {'student': Student(unsaved),
    'pocket_money': Decimal or None, 'row_data': original row dict}
    (row_data is kept so parent/pocket-money processing after the
    bulk insert doesn't need to re-read the CSV).

    error is set (a string) only for a fatal problem — empty file or
    missing required columns — in which case valid_rows/skipped are empty.
    """
    reader = csv.DictReader(io.StringIO(decoded_csv_text))

    if reader.fieldnames is None:
        return [], [], 'CSV file appears to be empty.'

    missing_required = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
    if missing_required:
        return [], [], f"Missing required column(s): {', '.join(missing_required)}"

    valid_rows = []
    skipped = []

    for row_number, row in enumerate(reader, start=2):  # row 1 = header
        first_name = (row.get('first_name') or '').strip()
        last_name = (row.get('last_name') or '').strip()
        dob_raw = (row.get('date_of_birth') or '').strip()
        grade_class = (row.get('grade_class') or '').strip().lower()

        if not first_name or not last_name or not dob_raw or not grade_class:
            skipped.append({
                'row': row_number,
                'reason': 'Missing one of: first_name, last_name, date_of_birth, grade_class.'
            })
            continue

        if grade_class not in VALID_CLASS_KEYS:
            skipped.append({
                'row': row_number,
                'reason': f'grade_class "{grade_class}" must be one of: {", ".join(CLASS_ORDER)}.'
            })
            continue

        date_of_birth = _parse_date(dob_raw)
        if not date_of_birth:
            skipped.append({
                'row': row_number,
                'reason': f'Could not parse date_of_birth "{dob_raw}" (use YYYY-MM-DD).'
            })
            continue

        data = {
            'student_number': _temp_student_number(),
            'first_name': first_name,
            'last_name': last_name,
            'date_of_birth': date_of_birth,
            'grade_class': grade_class,
            'age': Student.calculate_age(date_of_birth),  # bulk_create skips save(), so set it explicitly
        }
        for col in OPTIONAL_COLUMNS:
            value = (row.get(col) or '').strip()
            if value:
                data[col] = value

        pocket_money_amount = None
        pocket_money_raw = (row.get(POCKET_MONEY_COLUMN) or '').strip()
        if pocket_money_raw:
            try:
                amount = Decimal(pocket_money_raw)
                if amount > 0:
                    pocket_money_amount = amount
            except (InvalidOperation, ValueError):
                pass  # silently ignore a malformed money value; the student is still created

        valid_rows.append({
            'student': Student(**data),
            'pocket_money': pocket_money_amount,
        })

    return valid_rows, skipped, None


def run_import_job(job_id, decoded_csv_text):
    """
    Does the actual work behind an ImportJob, meant to be run in a
    background thread (see apps.students.views.student_import) so the
    upload request returns immediately and the import keeps running
    even if the person navigates away from the page.

    Two phases, for speed:
      1. Validate every row, then create all valid Student rows in a
         SINGLE bulk_create() call instead of one INSERT per row —
         this is the main speed win for large files.
      2. For each newly created student, sync parent login accounts
         and any initial pocket money deposit. This is done per-row
         since parent dedup needs a lookup each time, but WhatsApp
         notifications are skipped here (notify=False) to keep bulk
         imports fast — logins are still created normally.

    ImportJob.processed_rows is updated after each student in phase 2
    so the progress bar reflects real progress.
    """
    from django import db
    from apps.accounts.services import sync_all_parent_accounts
    from apps.pocketmoney.services import add_transaction
    from .models import ImportJob

    job = ImportJob.objects.get(pk=job_id)
    job.status = 'processing'
    job.save(update_fields=['status'])

    try:
        valid_rows, skipped, error = _parse_and_validate_rows(decoded_csv_text)

        if error:
            job.status = 'failed'
            job.error_message = error
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'finished_at'])
            return

        job.total_rows = len(valid_rows)
        job.skipped_details = skipped
        job.save(update_fields=['total_rows', 'skipped_details'])

        # Phase 1: one bulk INSERT for every valid student, instead of
        # one query per row — the main speed improvement for big files.
        students_to_create = [row['student'] for row in valid_rows]
        Student.objects.bulk_create(students_to_create)

        # bulk_create() doesn't reliably hand back objects with a real,
        # usable database primary key on every MySQL/MariaDB version —
        # so instead of trusting its return value, re-fetch the rows we
        # just inserted using the unique temp student_number we gave
        # each one beforehand. This guarantees every object below is
        # a proper, database-backed instance before we try to link it
        # to parent accounts (which failed before this fix).
        temp_numbers = [s.student_number for s in students_to_create]
        by_temp_number = {
            s.student_number: s
            for s in Student.objects.filter(student_number__in=temp_numbers)
        }
        created_students = [by_temp_number[s.student_number] for s in students_to_create]

        # Phase 2: per-student follow-up work (parent logins, pocket money).
        created_names = []
        for row, student in zip(valid_rows, created_students):
            sync_all_parent_accounts(student, notify=False)
            if row['pocket_money']:
                add_transaction(
                    student, 'deposit', row['pocket_money'],
                    note='Initial pocket money from CSV import',
                    user=job.created_by, notify=False
                )
            created_names.append(student.full_name)

            job.processed_rows += 1
            job.save(update_fields=['processed_rows'])

        renumber_students(background_qr=False)  # already off the request thread, safe to wait here

        job.status = 'done'
        job.created_count = len(created_students)
        job.created_names = created_names
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'created_count', 'created_names', 'finished_at'])

    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at'])
    finally:
        db.connections.close_all()
