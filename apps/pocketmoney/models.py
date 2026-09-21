from django.conf import settings
from django.db import models

from apps.students.models import Student


class Transaction(models.Model):
    """
    A single deposit or withdrawal against a student's pocket money.
    The running balance is never stored directly — it's always
    computed from the sum of all transactions (see services.get_balance)
    so it can never drift out of sync with the history.
    """
    TRANSACTION_TYPES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='pocket_money_transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.amount} - {self.student.full_name}"

    @property
    def signed_amount(self):
        """Positive for deposits, negative for withdrawals — handy for running totals."""
        return self.amount if self.transaction_type == 'deposit' else -self.amount
