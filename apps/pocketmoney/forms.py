from django import forms

from .models import Transaction


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['transaction_type', 'amount', 'note']
        widgets = {
            'note': forms.TextInput(attrs={'placeholder': 'What was it for? (optional)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount


class InitialDepositForm(forms.Form):
    """
    Embedded in the student REGISTRATION form — an optional starting
    balance. No admin password needed here since registering a
    student is already an admin-only action.
    """
    initial_amount = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=0,
        label="Initial Pocket Money (optional)",
        help_text="Starting balance to deposit when this student is registered. Leave blank for zero."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()


class BalanceAdjustmentForm(forms.Form):
    """
    Embedded in the student EDIT form — lets an admin add or reduce
    pocket money right from the student's page. Because this can move
    real money, it requires the admin to re-enter their own password;
    if left blank or wrong, the balance is NOT changed (the rest of
    the student edit still saves normally).
    """
    ADJUSTMENT_CHOICES = [('deposit', 'Add (Deposit)'), ('withdrawal', 'Reduce (Withdrawal)')]

    adjustment_type = forms.ChoiceField(choices=ADJUSTMENT_CHOICES, required=False, label="Adjustment Type")
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=0,
        label="Adjustment Amount", help_text="Leave blank to make no change."
    )
    note = forms.CharField(max_length=200, required=False, label="Note")
    admin_password = forms.CharField(
        widget=forms.PasswordInput, required=False,
        label="Your Password", help_text="Required only if you entered an amount above."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()
