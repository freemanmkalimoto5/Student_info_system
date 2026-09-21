"""
Student business logic: bulk CSV import and auto-numbering, kept
separate from views.py so they can be reused (management commands,
API endpoints, etc).
"""
import csv
import io
import uuid
from datetime import datetime

from .models import Student

# Class order used both for the dropdown (see Student.CLASS_CHOICES)
# and here for sorting students when auto-numbering.
CLASS_ORDER = [key for key, _label in Student.CLASS_CHOICES]

VALID_CLASS_KEYS = set(CLASS_ORDER)

# student_number is no longer supplied manually — it's assigned by
# renumber_students() based on class + alphabetical order. grade_class
# is required in CSV imports because numbering depends on knowing it.
REQUIRED_COLUMNS = ['first_name', 'last_name', 'date_of_birth', 'grade_class']

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


def renumber_students():
    """
    Re-assigns every student's student_number based on:
      1. Class order: form one, two, three, four, five, six
      2. Alphabetical by first name, then last name, within each class

    So if form one ends at student_number 10, form two continues
    starting at 11, and so on — a single contiguous sequence across
    all classes.

    Whenever a student's number actually changes, their QR code is
    regenerated to match (since the QR encodes the student number).

    Returns the list of Student instances whose number changed.
    """
    from apps.qrcodes.models import IDCard
    from apps.qrcodes.services import generate_id_card_qr

    order_index = {key: i for i, key in enumerate(CLASS_ORDER)}

    all_students = list(Student.objects.all())
    all_students.sort(
        key=lambda s: (
            order_index.get(s.grade_class, len(CLASS_ORDER)),  # unknown classes sort last
            s.first_name.lower(),
            s.last_name.lower(),
        )
    )

    changed = []
    for position, student in enumerate(all_students, start=1):
        new_number = str(position)
        if student.student_number != new_number:
            student.student_number = new_number
            student.save(update_fields=['student_number'])
            changed.append(student)

    for student in changed:
        card, _ = IDCard.objects.get_or_create(student=student)
        card.qr_image.save(
            f"qr_{student.student_number}.png",
            generate_id_card_qr(student),
            save=True,
        )

    return changed


def import_students_from_csv(uploaded_file):
    """
    Reads an uploaded CSV file and creates Student records. Each new
    student also gets parent login accounts synced (see
    apps.accounts.services.sync_all_parent_accounts).

    Returns a dict:
        {
            'created': [full_name, ...],
            'skipped': [{'row': 2, 'reason': '...'}, ...],
        }
    Nothing is rolled back on partial failure — each row succeeds or
    fails independently. Numbering is NOT done per-row for efficiency;
    call renumber_students() once after this returns.
    """
    from apps.accounts.services import sync_all_parent_accounts

    decoded = uploaded_file.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(decoded))

    result = {'created': [], 'skipped': []}

    if reader.fieldnames is None:
        result['skipped'].append({'row': 0, 'reason': 'CSV file appears to be empty.'})
        return result

    missing_required = [col for col in REQUIRED_COLUMNS if col not in reader.fieldnames]
    if missing_required:
        result['skipped'].append({
            'row': 0,
            'reason': f"Missing required column(s): {', '.join(missing_required)}"
        })
        return result

    for row_number, row in enumerate(reader, start=2):  # row 1 = header
        first_name = (row.get('first_name') or '').strip()
        last_name = (row.get('last_name') or '').strip()
        dob_raw = (row.get('date_of_birth') or '').strip()
        grade_class = (row.get('grade_class') or '').strip().lower()

        if not first_name or not last_name or not dob_raw or not grade_class:
            result['skipped'].append({
                'row': row_number,
                'reason': 'Missing one of: first_name, last_name, date_of_birth, grade_class.'
            })
            continue

        if grade_class not in VALID_CLASS_KEYS:
            result['skipped'].append({
                'row': row_number,
                'reason': f'grade_class "{grade_class}" must be one of: {", ".join(CLASS_ORDER)}.'
            })
            continue

        date_of_birth = _parse_date(dob_raw)
        if not date_of_birth:
            result['skipped'].append({
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
        }
        for col in OPTIONAL_COLUMNS:
            value = (row.get(col) or '').strip()
            if value:
                data[col] = value

        try:
            student = Student.objects.create(**data)
            sync_all_parent_accounts(student)
            result['created'].append(student.full_name)
        except Exception as exc:
            result['skipped'].append({'row': row_number, 'reason': str(exc)})

    return result
