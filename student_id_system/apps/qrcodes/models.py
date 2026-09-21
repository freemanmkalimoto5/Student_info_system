from django.db import models

from apps.students.models import Student


class IDCard(models.Model):
    """
    One QR/ID card record per student. Keeps track of the generated QR
    image plus how many times it's been printed, so you have an audit
    trail if a card is lost and reissued.
    """
    student = models.OneToOneField(
        Student, on_delete=models.CASCADE, related_name='id_card'
    )
    qr_image = models.ImageField(upload_to='qr_codes/', blank=True, null=True)

    generated_at = models.DateTimeField(auto_now_add=True)
    regenerated_at = models.DateTimeField(auto_now=True)

    print_count = models.PositiveIntegerField(default=0)
    last_printed_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"ID Card - {self.student.student_number}"

    def mark_printed(self):
        from django.utils import timezone
        self.print_count += 1
        self.last_printed_at = timezone.now()
        self.save(update_fields=['print_count', 'last_printed_at'])
