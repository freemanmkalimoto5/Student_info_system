r"""
Automatic class promotion (REPLACES the old promote_students.py).

  1 January : form four -> graduated, form three -> four, two -> three, one -> two
              (+ renumber, + rebuild QR codes of forms 1-4 and the graduates)
  1 June    : form six  -> graduated, form five -> form six
              (+ renumber, + rebuild QR codes of the new form six and the graduates)

Schedule ONE daily task (Windows Task Scheduler):
    C:\path\to\venv\Scripts\python.exe manage.py promote_students
Each rollover runs only ONCE per year (recorded in RolloverLog), so running
the command every day is safe. If the computer was off on 1 Jan / 1 Jun, the
next run during that same month catches up.

Other options
  --force january|june     run that rollover now (still only once per year)
  --mark-done january|june record it as already done WITHOUT changing anything
                           (use in the year you start using this system)
  --regenerate-all         renumber everyone and rebuild every QR code
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.students import services
from apps.students.models import RolloverLog, Student


class Command(BaseCommand):
    help = "Promotes students on 1 January (O-level) and 1 June (A-level)."

    def add_arguments(self, parser):
        parser.add_argument('--force', choices=['january', 'june'])
        parser.add_argument('--mark-done', choices=['january', 'june'])
        parser.add_argument('--regenerate-all', action='store_true')

    def handle(self, *args, **opts):
        today = timezone.localdate()

        if opts['regenerate_all']:
            services.renumber_students(background_qr=False, regenerate=False)
            services._regenerate_qr_codes(list(Student.objects.all()))
            self.stdout.write(self.style.SUCCESS("Renumbered and rebuilt every QR code."))
            return

        if opts['mark_done']:
            RolloverLog.objects.get_or_create(event=opts['mark_done'], year=today.year)
            self.stdout.write(f"{opts['mark_done']} {today.year} marked as done. Nothing was changed.")
            return

        event = opts['force']
        if not event:
            event = {1: 'january', 6: 'june'}.get(today.month)
        if not event:
            self.stdout.write("Nothing to do this month.")
            return

        if RolloverLog.objects.filter(event=event, year=today.year).exists():
            self.stdout.write(f"{event.capitalize()} {today.year} rollover was already done. Skipping.")
            return

        result = services.january_rollover(today) if event == 'january' else services.june_rollover(today)
        self.stdout.write(self.style.SUCCESS(
            f"{event.capitalize()} rollover done: {result['promoted']} promoted, "
            f"{result['graduated']} graduated, {result['qr_rebuilt']} QR codes rebuilt."
        ))
