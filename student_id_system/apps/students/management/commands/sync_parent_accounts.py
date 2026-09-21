"""
One-time backfill: creates parent/guardian login accounts for every
student already in the database. Needed because parent accounts are
normally only created when a student is registered or edited through
the form — students that existed before this feature (or before its
migrations were applied) never triggered that sync.

Safe to run more than once — sync_all_parent_accounts() reuses an
existing account (matched by phone number) instead of duplicating it.
"""
from django.core.management.base import BaseCommand

from apps.students.models import Student
from apps.accounts.services import sync_all_parent_accounts


class Command(BaseCommand):
    help = "Creates parent/guardian login accounts for all existing students."

    def handle(self, *args, **options):
        students = Student.objects.all()
        count = 0
        for student in students:
            sync_all_parent_accounts(student)
            count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {count} student(s). Check Django admin "
            f"(/admin/accounts/parentaccount/) to see the accounts created."
        ))
