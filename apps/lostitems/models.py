from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.students.models import Student


class LostItem(models.Model):
    """
    Something a student lost, what it costs, and how much of that price
    has been paid so far. The status (Pending / Partially paid / Paid) is
    NOT typed by hand: it is worked out from the payments recorded.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('partial', 'Partially paid'),
        ('paid', 'Paid'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='lost_items')
    item_name = models.CharField(max_length=150, verbose_name='Item lost')
    price = models.DecimalField(max_digits=12, decimal_places=2, help_text="Replacement price.")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    date_lost = models.DateField(default=timezone.localdate)
    note = models.CharField(max_length=250, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True, help_text="When it was fully paid.")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_lost', '-created_at']

    def __str__(self):
        return f"{self.item_name} - {self.student.student_number} ({self.get_status_display()})"

    # ---- money ------------------------------------------------------
    @property
    def amount_paid(self):
        if not self.pk:
            return Decimal('0')
        return sum((p.amount for p in self.payments.all()), Decimal('0'))

    @property
    def balance(self):
        return max(self.price - self.amount_paid, Decimal('0'))

    @property
    def percent_paid(self):
        if not self.price:
            return 0
        return min(100, int(self.amount_paid * 100 / self.price))

    def _derive_status(self):
        paid = self.amount_paid
        if paid <= 0:
            self.status, self.paid_at = 'pending', None
        elif paid >= self.price:
            self.status = 'paid'
            self.paid_at = self.paid_at or timezone.now()
        else:
            self.status, self.paid_at = 'partial', None

    def save(self, *args, **kwargs):
        self._derive_status()
        super().save(*args, **kwargs)


class LostItemPayment(models.Model):
    """One (possibly partial) payment towards a lost item."""
    item = models.ForeignKey(LostItem, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.amount} for {self.item.item_name}"
