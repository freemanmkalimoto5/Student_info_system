"""
Student business logic: bulk CSV import, auto-numbering, automatic yearly
promotions (1 Jan / 1 Jun), and duplicate-registration detection. Kept
separate from views.py so it can be reused (management commands, etc).
"""
import csv
import io
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import Student, RolloverLog

CLASS_ORDER = [key for key, _label in Student.CLASS_CHOICES]
CLASS_INDEX = {key: i for i, key in enumerate(CLASS_ORDER)}
VALID_CLASS_KEYS = set(CLASS_ORDER)

CLASS_ABBREVIATIONS = {
    'form one': 'FI',
    'form two': 'FII',
    'form three': 'FIII',
    'form four': 'FIV',
    'form five': 'FV',
    'form six': 'FVI',
}

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

PROMOTABLE = ['active', 'suspended']
O_LEVEL = ['form one', 'form two', 'form three', 'form four']


# ---------------------------------------------------------------------
# Sorting used by the Students page and the QR codes page
# ---------------------------------------------------------------------
def _number_part(student_number):
    """'FI.10' -> 10, 'GR2026-FIV.5' -> 5  (so FI.2 sorts BEFORE FI.10)."""
    match = re.search(r'(\d+)$', student_number or '')
    return int(match.group(1)) if match else 0


def student_sort_key(student):
    """Class first (form one -> form six), then alphabetically by name.
    Graduated students always sort last."""
    return (
        1 if student.status == 'graduated' else 0,
        CLASS_INDEX.get(student.grade_class, len(CLASS_ORDER)),
        student.first_name.strip().lower(),
        student.last_name.strip().lower(),
    )


def sort_students(students):
    """Returns a LIST ordered by class (form one -> form six) then alphabetically."""
    return sorted(students, key=student_sort_key)


# ---------------------------------------------------------------------
# Duplicate-registration detection
# ---------------------------------------------------------------------
def _norm(value):
    return (value or '').strip().lower()


def duplicate_key(first_name, last_name, date_of_birth):
    """The identity used to decide 'this is the same student': same first
    name, same last name, same date of birth (case/space-insensitive)."""
    return (_norm(first_name), _norm(last_name), date_of_birth)


def find_duplicate_student(first_name, last_name, date_of_birth, exclude_pk=None):
    """Returns the existing Student that matches this identity, or None.
    Only checks students who are not graduated -- a graduated student
    sharing a name with a genuinely new student is not unusual."""
    qs = Student.objects.exclude(status='graduated')
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    target = duplicate_key(first_name, last_name, date_of_birth)
    for s in qs.only('id', 'first_name', 'last_name', 'date_of_birth', 'student_number'):
        if duplicate_key(s.first_name, s.last_name, s.date_of_birth) == target:
            return s
    return None


def notify_duplicate(first_name, last_name, date_of_birth, grade_class, existing_student, source):
    """Raise a pending Notification about a duplicate registration attempt.
    Never blocks the caller if notifications app has a problem."""
    try:
        from apps.notifications.services import notify_duplicate as _create
        full = f"{first_name} {last_name}".strip()
        title = f"Possible duplicate: {full}"
        message = (
            f"{source} tried to register {full} (DOB {date_of_birth}, {grade_class}), "
            f"but a matching student already exists: {existing_student.full_name} "
            f"({existing_student.student_number}, {existing_student.get_grade_class_display()}).\n"
            f"Check both records, then mark this notification as fixed."
        )
        _create(title, message, existing_student=existing_student)
    except Exception as exc:
        print("DUPLICATE NOTIFY ERROR:", exc)


# ---------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------
def _parse_date(value):
    value = value.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _temp_student_number():
    return f"TMP-{uuid.uuid4().hex[:10]}"


def _regenerate_qr_codes(students):
    from apps.qrcodes.services import regenerate_cards
    regenerate_cards(students)


# ---------------------------------------------------------------------
# Numbering
# ---------------------------------------------------------------------
def _freeze_graduated_numbers(tag=''):
    legacy = list(
        Student.objects.filter(status='graduated').exclude(student_number__startswith='GR')
    )
    for s in legacy:
        s.student_number = f"GR{tag}-{s.student_number}"
    if legacy:
        Student.objects.bulk_update(legacy, ['student_number'], batch_size=500)
    return legacy


def renumber_students(background_qr=True, regenerate=True):
    changed = _freeze_graduated_numbers()

    all_students = list(Student.objects.exclude(status='graduated'))
    all_students.sort(key=lambda s: (
        CLASS_INDEX.get(s.grade_class, len(CLASS_ORDER)),
        s.first_name.lower(),
        s.last_name.lower(),
        s.pk,
    ))

    final_numbers = {}
    counters = {}
    for student in all_students:
        prefix = CLASS_ABBREVIATIONS.get(
            student.grade_class, student.grade_class.upper().replace(' ', '')
        )
        counters[prefix] = counters.get(prefix, 0) + 1
        final_numbers[student.pk] = f"{prefix}.{counters[prefix]}"

    needs_change = [s for s in all_students if s.student_number != final_numbers[s.pk]]

    if needs_change:
        for s in needs_change:
            s.student_number = f"TMP-{s.pk}"
        Student.objects.bulk_update(needs_change, ['student_number'], batch_size=500)
        for s in needs_change:
            s.student_number = final_numbers[s.pk]
        Student.objects.bulk_update(needs_change, ['student_number'], batch_size=500)
        changed += needs_change

    if changed and regenerate:
        if background_qr:
            import threading
            threading.Thread(target=_regenerate_qr_codes, args=(changed,), daemon=True).start()
        else:
            _regenerate_qr_codes(changed)

    return changed


# ---------------------------------------------------------------------
# Automatic promotions
# ---------------------------------------------------------------------
def _graduate(class_key, finish_year):
    students = list(Student.objects.filter(grade_class=class_key, status__in=PROMOTABLE))
    for s in students:
        s.status = 'graduated'
        s.student_number = f"GR{finish_year}-{s.student_number}"
    if students:
        Student.objects.bulk_update(students, ['status', 'student_number'], batch_size=500)
    return students


def _move(old_class, new_class):
    return Student.objects.filter(grade_class=old_class, status__in=PROMOTABLE).update(grade_class=new_class)


def january_rollover(today=None):
    today = today or timezone.localdate()
    with transaction.atomic():
        graduated = _graduate('form four', today.year - 1)
        promoted = 0
        for old, new in (('form three', 'form four'), ('form two', 'form three'), ('form one', 'form two')):
            promoted += _move(old, new)
        RolloverLog.objects.create(
            event='january', year=today.year,
            promoted_count=promoted, graduated_count=len(graduated),
        )

    renumber_students(background_qr=False, regenerate=False)
    refresh = list(Student.objects.filter(grade_class__in=O_LEVEL, status__in=PROMOTABLE)) + graduated
    _regenerate_qr_codes(refresh)
    return {'promoted': promoted, 'graduated': len(graduated), 'qr_rebuilt': len(refresh)}


def june_rollover(today=None):
    today = today or timezone.localdate()
    with transaction.atomic():
        graduated = _graduate('form six', today.year)
        promoted = _move('form five', 'form six')
        RolloverLog.objects.create(
            event='june', year=today.year,
            promoted_count=promoted, graduated_count=len(graduated),
        )

    renumber_students(background_qr=False, regenerate=False)
    refresh = list(Student.objects.filter(grade_class='form six', status__in=PROMOTABLE)) + graduated
    _regenerate_qr_codes(refresh)
    return {'promoted': promoted, 'graduated': len(graduated), 'qr_rebuilt': len(refresh)}


# ---------------------------------------------------------------------
# CSV import (now with duplicate detection, against the DB AND within the file)
# ---------------------------------------------------------------------
def _parse_and_validate_rows(decoded_csv_text):
    reader = csv.DictReader(io.StringIO(decoded_csv_text))

    if reader.fieldnames is None:
        return [], [], 'CSV file appears to be empty.'

    missing_required = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
    if missing_required:
        return [], [], f"Missing required column(s): {', '.join(missing_required)}"

    valid_rows = []
    skipped = []
    duplicates_to_notify = []   # (first, last, dob, grade_class, existing_student_or_None)
    seen_in_file = {}           # duplicate_key -> row_number (catches two rows in the SAME file)

    for row_number, row in enumerate(reader, start=2):
        first_name = (row.get('first_name') or '').strip()
        last_name = (row.get('last_name') or '').strip()
        dob_raw = (row.get('date_of_birth') or '').strip()
        grade_class = (row.get('grade_class') or '').strip().lower()

        if not first_name or not last_name or not dob_raw or not grade_class:
            skipped.append({'row': row_number,
                            'reason': 'Missing one of: first_name, last_name, date_of_birth, grade_class.'})
            continue

        if grade_class not in VALID_CLASS_KEYS:
            skipped.append({'row': row_number,
                            'reason': f'grade_class "{grade_class}" must be one of: {", ".join(CLASS_ORDER)}.'})
            continue

        date_of_birth = _parse_date(dob_raw)
        if not date_of_birth:
            skipped.append({'row': row_number,
                            'reason': f'Could not parse date_of_birth "{dob_raw}" (use YYYY-MM-DD).'})
            continue

        key = duplicate_key(first_name, last_name, date_of_birth)

        # (a) duplicate of a student already in the database
        existing = find_duplicate_student(first_name, last_name, date_of_birth)
        if existing:
            skipped.append({'row': row_number,
                            'reason': f'Looks like a duplicate of existing student {existing.student_number} '
                                      f'({existing.full_name}). Sent to Notifications.'})
            duplicates_to_notify.append((first_name, last_name, date_of_birth, grade_class, existing))
            continue

        # (b) duplicate of ANOTHER row already read from this same file
        if key in seen_in_file:
            skipped.append({'row': row_number,
                            'reason': f'Duplicate of row {seen_in_file[key]} in this same file. Sent to Notifications.'})
            duplicates_to_notify.append((first_name, last_name, date_of_birth, grade_class, None))
            continue
        seen_in_file[key] = row_number

        data = {
            'student_number': _temp_student_number(),
            'first_name': first_name,
            'last_name': last_name,
            'date_of_birth': date_of_birth,
            'grade_class': grade_class,
            'age': Student.calculate_age(date_of_birth),
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
                pass

        valid_rows.append({'student': Student(**data), 'pocket_money': pocket_money_amount})

    return valid_rows, skipped, None, duplicates_to_notify


def run_import_job(job_id, decoded_csv_text):
    from django import db
    from apps.accounts.services import sync_all_parent_accounts
    from apps.pocketmoney.services import add_transaction
    from .models import ImportJob

    job = ImportJob.objects.get(pk=job_id)
    job.status = 'processing'
    job.save(update_fields=['status'])

    try:
        valid_rows, skipped, error, duplicates_to_notify = _parse_and_validate_rows(decoded_csv_text)

        if error:
            job.status = 'failed'
            job.error_message = error
            job.finished_at = timezone.now()
            job.save(update_fields=['status', 'error_message', 'finished_at'])
            return

        for first, last, dob, grade_class, existing in duplicates_to_notify:
            notify_duplicate(first, last, dob, grade_class, existing,
                             source="CSV import" if existing else "CSV import (duplicate row in same file)")

        job.total_rows = len(valid_rows)
        job.skipped_details = skipped
        job.save(update_fields=['total_rows', 'skipped_details'])

        students_to_create = [row['student'] for row in valid_rows]
        Student.objects.bulk_create(students_to_create)

        temp_numbers = [s.student_number for s in students_to_create]
        by_temp_number = {
            s.student_number: s
            for s in Student.objects.filter(student_number__in=temp_numbers)
        }
        created_students = [by_temp_number[s.student_number] for s in students_to_create]

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
            if job.processed_rows % 20 == 0:
                job.save(update_fields=['processed_rows'])

        job.save(update_fields=['processed_rows'])

        renumber_students(background_qr=False)

        job.status = 'done'
        job.created_count = len(created_students)
        job.created_names = created_names
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'created_count', 'created_names', 'finished_at'])

    except Exception as exc:
        job.status = 'failed'
        job.error_message = str(exc)[:500]
        job.finished_at = timezone.now()
        job.save(update_fields=['status', 'error_message', 'finished_at'])
    finally:
        db.connections.close_all()
