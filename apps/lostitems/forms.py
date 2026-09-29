from decimal import Decimal

from django import forms

from .models import LostItem


class LostItemForm(forms.ModelForm):
    class Meta:
        model = LostItem
        fields = ['item_name', 'price', 'date_lost', 'note']
        widgets = {
            'date_lost': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'note': forms.TextInput(attrs={'placeholder': 'Optional, e.g. lost in the dormitory'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()

    def clean_price(self):
        price = self.cleaned_data['price']
        if price <= 0:
            raise forms.ValidationError("Price must be greater than zero.")
        return price


class PaymentForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal('0.01'),
        label="Amount paid now (TSh)",
        help_text="The balance is filled in. Type a smaller amount for a partial payment.",
    )
    note = forms.CharField(max_length=200, required=False, label="Note (optional)")

    def __init__(self, *args, item=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = item
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()
        if item is not None:
            self.fields['amount'].widget.attrs['max'] = str(item.balance)

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if self.item is not None and amount > self.item.balance:
            raise forms.ValidationError(
                f"You cannot pay more than the balance (TSh {self.item.balance:,.0f})."
            )
        return amount
