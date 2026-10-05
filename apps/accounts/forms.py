from django import forms
from django.contrib.auth.models import User
from django.core.files.uploadedfile import UploadedFile

from .models import SiteSettings, AdminProfile


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = ['school_name', 'logo', 'contact_email', 'contact_phone', 'website']


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = f"{existing} form-control".strip()


class AddAdminForm(forms.Form):
    """
    Used by a SUPERUSER to create a new login: another Superuser (full
    control), a full Admin, or a restricted Clerk (everything except the
    audit log, and a cut-down Settings page). The new account fills in
    their own details (name/phone/position/email) on first login via
    AdminProfileForm below.
    """
    ROLE_CHOICES = [
        ('superuser', 'Superuser (full control, can add other admins)'),
        ('admin', 'Admin'),
        ('clerk', 'Clerk'),
    ]

    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput, help_text="Temporary password — they can change it later.")
    role = forms.ChoiceField(choices=ROLE_CHOICES, initial='admin')

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("This username is already taken.")
        return username


class AdminProfileForm(forms.ModelForm):
    """
    Filled in by a new admin/clerk the first time they log in. EVERY field
    is required here -- the model keeps them optional (blank=True) so older
    accounts keep working, but nobody gets past this form with gaps.

    The name is three separate boxes (first, middle, last). First and last
    name are saved on the User; middle name and the combined full name are
    saved on the AdminProfile (see views.complete_profile).
    """
    first_name = forms.CharField(max_length=60, label="First Name")
    last_name = forms.CharField(max_length=60, label="Last Name")
    email = forms.EmailField(label="Email Address")
    selected_role = forms.ChoiceField(
        label="Your Role",
        choices=[
            ('', '— Select your role —'),
            ('superuser', 'Superuser'),
            ('admin', 'Admin'),
            ('clerk', 'Clerk'),
        ],
    )

    field_order = ['photo', 'first_name', 'middle_name', 'last_name', 'email', 'phone', 'position', 'selected_role']

    MAX_PHOTO_BYTES = 5 * 1024 * 1024

    class Meta:
        model = AdminProfile
        fields = ['middle_name', 'phone', 'position', 'photo']
        labels = {
            'middle_name': 'Middle Name',
            'phone': 'Phone Number',
            'position': 'Position / Title',
            'photo': 'Your Photo',
        }
        widgets = {
            'photo': forms.FileInput(attrs={'accept': 'image/*'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('middle_name', 'phone', 'position', 'photo'):
            self.fields[name].required = True
        self.fields['middle_name'].max_length = 60
        for field in self.fields.values():
            existing = field.widget.attrs.get('class', '')
            if not isinstance(field.widget, forms.FileInput):
                field.widget.attrs['class'] = f"{existing} form-control".strip()

    @staticmethod
    def _clean_name(value, label):
        value = ' '.join(value.split())
        if len(value) < 2 or not all(c.isalpha() or c in "'\u2019- " for c in value):
            raise forms.ValidationError(f"Enter a valid {label} (letters only).")
        return value

    def clean_first_name(self):
        return self._clean_name(self.cleaned_data['first_name'], 'first name')

    def clean_middle_name(self):
        return self._clean_name(self.cleaned_data['middle_name'], 'middle name')

    def clean_last_name(self):
        return self._clean_name(self.cleaned_data['last_name'], 'last name')

    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()
        digits = [c for c in phone if c.isdigit()]
        if len(digits) < 9 or any(not (c.isdigit() or c in '+ -') for c in phone):
            raise forms.ValidationError("Enter a valid phone number, e.g. 0712 345 678.")
        return phone

    def clean_position(self):
        return ' '.join(self.cleaned_data['position'].split())

    def _assigned_role(self):
        """The role the superuser gave this account when creating it."""
        user = self.instance.user
        if user.is_superuser:
            return 'superuser'
        return 'clerk' if self.instance.role == 'clerk' else 'admin'

    def clean_selected_role(self):
        chosen = self.cleaned_data['selected_role']
        if chosen != self._assigned_role():
            # Deliberately does not say which role is the right one.
            raise forms.ValidationError(
                "This is not the role assigned to your account, so you cannot continue. "
                "Select the role the superuser gave you, or contact the superuser."
            )
        return chosen

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if isinstance(photo, UploadedFile) and photo.size > self.MAX_PHOTO_BYTES:
            raise forms.ValidationError("The photo is too large -- please use one under 5 MB.")
        return photo


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
