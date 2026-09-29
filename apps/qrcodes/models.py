from django.db import models
from django.utils import timezone

from apps.students.models import Student


class IDCard(models.Model):
    """
    One QR/ID card record per student. Keeps track of the generated QR
    image, how many times it's been printed, and the date the card
    stops being valid (valid_until). valid_until = None means the card
    never expires (used for graduated students).
    """
    student = models.OneToOneField(
        Student, on_delete=models.CASCADE, related_name='id_card'
    )
    qr_image = models.ImageField(upload_to='qr_codes/', blank=True, null=True)

    # NEW: 31 Dec for O-level, 31 May for A-level, blank for graduated.
    valid_until = models.DateField(
        blank=True, null=True,
        help_text="Last valid day of this card. Blank = never expires (graduated)."
    )

    generated_at = models.DateTimeField(auto_now_add=True)
    regenerated_at = models.DateTimeField(auto_now=True)

    print_count = models.PositiveIntegerField(default=0)
    last_printed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"ID Card - {self.student.student_number}"

    @property
    def is_expired(self):
        """Graduated students never expire; everyone else expires after valid_until."""
        if self.student.status == 'graduated' or self.valid_until is None:
            return False
        return timezone.localdate() > self.valid_until

    def mark_printed(self):
        self.print_count += 1
        self.last_printed_at = timezone.now()
        self.save(update_fields=['print_count', 'last_printed_at'])
