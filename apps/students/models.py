from datetime import date

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Student(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('graduated', 'Graduated'),
        ('transferred', 'Transferred'),
        ('suspended', 'Suspended'),
    ]

    # Fixed class order — used for both the dropdown and for sorting
    # students by class when auto-numbering (see services.renumber_students).
    CLASS_CHOICES = [
        ('form one', 'Form One'),
        ('form two', 'Form Two'),
        ('form three', 'Form Three'),
        ('form four', 'Form Four'),
        ('form five', 'Form Five'),
        ('form six', 'Form Six'),
    ]

    # --- Basic identity -----------------------------------------------
    # student_number is auto-assigned by renumber_students() based on
    # class + alphabetical order — it's not manually entered on the form.
    student_number = models.CharField(max_length=20, unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(
        max_length=100, blank=True, null=True,
        verbose_name="Middle Name (Father's Name)"
    )
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField()
    age = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(120)],
        blank=True,
        help_text="Auto-calculated from date of birth if left blank."
    )
    photo = models.ImageField(upload_to='student_photos/', blank=True, null=True)

    # --- Academic info ---------------------------------------------------
    grade_class = models.CharField(
        max_length=20, choices=CLASS_CHOICES, default='form one',
        verbose_name='Class / Grade'
    )
    enrollment_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    # --- Parents / guardians ----------------------------------------------
    father_name = models.CharField(max_length=150, blank=True, null=True)
    father_phone = models.CharField(max_length=20, blank=True, null=True)
    father_whatsapp = models.CharField(
        max_length=20, blank=True, null=True,
        verbose_name="Father's WhatsApp Number",
        help_text="Optional — used for WhatsApp notifications. Falls back to phone number if left blank."
    )
    mother_name = models.CharField(max_length=150, blank=True, null=True)
    mother_phone = models.CharField(max_length=20, blank=True, null=True)
    mother_whatsapp = models.CharField(
        max_length=20, blank=True, null=True,
        verbose_name="Mother's WhatsApp Number",
        help_text="Optional — used for WhatsApp notifications. Falls back to phone number if left blank."
    )
    guardian_name = models.CharField(max_length=150, blank=True, null=True)
    guardian_phone = models.CharField(max_length=20, blank=True, null=True)
    guardian_relationship = models.CharField(max_length=50, blank=True, null=True)

    # --- Religious / community info -----------------------------------
    parish = models.CharField(max_length=150, blank=True, null=True)

    # --- Address -----------------------------------------------------
    full_address = models.TextField(blank=True, null=True)
    region = models.CharField(max_length=100, blank=True, null=True)
    district = models.CharField(max_length=100, blank=True, null=True)
    ward = models.CharField(max_length=100, blank=True, null=True)

    # --- Audit trail ----------------------------------------------------
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
        help_text="Staff account that registered this student."
    )

    # --- Timestamps ----------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.student_number} - {self.full_name}"

    @property
    def full_name(self):
        parts = [self.first_name, self.middle_name, self.last_name]
        return " ".join(p for p in parts if p)

    @staticmethod
    def calculate_age(date_of_birth):
        """
        Shared by save() and the bulk CSV import path (which uses
        bulk_create and therefore skips save() entirely) so age is
        computed the same way everywhere.
        """
        today = date.today()
        return today.year - date_of_birth.year - (
            (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
        )

    def save(self, *args, **kwargs):
        # Auto-calculate age from date_of_birth whenever it isn't set,
        # so staff don't have to compute it by hand on the form.
        if self.date_of_birth and not self.age:
            self.age = Student.calculate_age(self.date_of_birth)
        super().save(*args, **kwargs)


class ImportJob(models.Model):
    """
    Tracks a bulk CSV import running in a background thread, so the
    upload page can show a live progress bar and the import keeps
    running even if the person navigates away — it's not tied to
    their browser connection at all, just a server-side job.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ]

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='pending')
    total_rows = models.PositiveIntegerField(default=0)
    processed_rows = models.PositiveIntegerField(default=0)
    created_count = models.PositiveIntegerField(default=0)
    created_names = models.JSONField(default=list, blank=True)
    skipped_details = models.JSONField(default=list, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    @property
    def percent(self):
        if not self.total_rows:
            return 0
        return round(100 * self.processed_rows / self.total_rows)
