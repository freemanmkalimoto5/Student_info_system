from django import forms
from django.contrib.auth.models import User

from .models import SiteSettings, AdminProfile


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = ['school_name', 'logo', 'contact_email', 'contact_phone']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()


class AddAdminForm(forms.Form):
    """
    Used by an existing full admin/superuser to create a new login —
    either a full Admin or a restricted Clerk (everything except the
    audit log, and a cut-down Settings page). The new account fills
    in their own details (name/phone/position) on first login via
    AdminProfileForm below.
    """
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput, help_text="Temporary password — they can change it later.")
    role = forms.ChoiceField(choices=AdminProfile.ROLE_CHOICES, initial='clerk')

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username


class AdminProfileForm(forms.ModelForm):
    """Filled in by a new admin/clerk the first time they log in."""
    class Meta:
        model = AdminProfile
        fields = ['full_name', 'phone', 'position']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()


class ClerkSettingsForm(forms.Form):
    """
    The cut-down Settings page a clerk gets: their own contact info,
    interface theme, and language preference — nothing system-wide.
    """
    email = forms.EmailField(required=False, label="Your Email")
    phone = forms.CharField(max_length=20, required=False, label="Your Phone Number")
    theme = forms.ChoiceField(choices=AdminProfile.THEME_CHOICES, label="Theme")
    language = forms.ChoiceField(choices=AdminProfile.LANGUAGE_CHOICES, label="Language")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()
