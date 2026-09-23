r"""
Promotes students between classes automatically, based on the current
month:
  - January:  form one -> two -> three -> four -> five (all at once)
  - July:     form five -> form six
  - June:     form six students are marked as graduated

This has no built-in scheduler — Django itself can't run code on a
timer. Schedule this command to run daily (it's safe to run every day;
it only acts during the relevant month, and running it twice in the
same month is harmless since promoted students no longer match the
filter the second time):

  Windows: use Task Scheduler to run, once a day,
      C:\path\to\venv\Scripts\python.exe manage.py promote_students
  from the project directory.

  Linux/macOS: a daily cron entry running
      python manage.py promote_students
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.students.models import Student
from apps.students.services import renumber_students

JANUARY_PROMOTIONS = {
    'form one': 'form two',
    'form two': 'form three',
    'form three': 'form four',
    'form four': 'form five',
}


class Command(BaseCommand):
    help = "Promotes students between classes based on the academic calendar (see module docstring)."

    def handle(self, *args, **options):
        month = timezone.now().month
        summary_lines = []

        if month == 1:
            for old_class, new_class in JANUARY_PROMOTIONS.items():
                qs = Student.objects.filter(grade_class=old_class, status='active')
                count = qs.count()
                if count:
                    qs.update(grade_class=new_class)
                    summary_lines.append(f"{count} student(s) moved from {old_class} to {new_class}")

        if month == 7:
            qs = Student.objects.filter(grade_class='form five', status='active')
            count = qs.count()
            if count:
                qs.update(grade_class='form six')
                summary_lines.append(f"{count} student(s) moved from form five to form six")

        if month == 6:
            qs = Student.objects.filter(grade_class='form six', status='active')
            count = qs.count()
            if count:
                qs.update(status='graduated')
                summary_lines.append(f"{count} student(s) in form six marked as graduated")

        if summary_lines:
            # Renumbering also regenerates QR codes for anyone whose
            # student_number changed as a result of the class shift.
            renumber_students(background_qr=False)
            for line in summary_lines:
                self.stdout.write(self.style.SUCCESS(line))
        else:
            self.stdout.write("No promotions applicable this month.")
