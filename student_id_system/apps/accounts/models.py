from django.conf import settings
from django.db import models

from apps.students.models import Student


class SiteSettings(models.Model):
    """
    Singleton table (always pk=1) holding system-wide branding and
    contact info: school name/logo shown in the top bar, plus basic
    contact details editable from the Settings page.
    """
    school_name = models.CharField(max_length=150, default='Your School Name')
    logo = models.ImageField(upload_to='site/', blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Site Settings'
        verbose_name_plural = 'Site Settings'

    def __str__(self):
        return self.school_name

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce a single row
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class ParentAccount(models.Model):
    """
    A parent/guardian's login, auto-created whenever a student is
    registered with that parent's name + phone. Username is derived
    from their name; password is their phone number (see
    apps.accounts.services.sync_all_parent_accounts).

    Keyed by phone number so siblings sharing a parent reuse the same
    login instead of creating duplicates.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='parent_account')
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, unique=True)
    relationship = models.CharField(max_length=50, blank=True)  # Father / Mother / Guardian
    students = models.ManyToManyField(Student, related_name='parent_accounts', blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.phone})"


class AdminProfile(models.Model):
    """
    Extra profile info an admin fills in the first time they log in
    (see apps.accounts.views.complete_profile), so the system knows
    who added/edited/deleted each student beyond just a username.

    Only created for admins added through the Settings > Add Admin
    flow — the original superuser (from `createsuperuser`) doesn't
    have one and isn't required to complete this (though visiting
    Settings lazily creates one for them too, already marked complete,
    so they can still set their own theme/language/contact info).

    role controls how much of the system this account can reach:
      - 'admin': full access, same as a superuser except can't be
        removed by another admin.
      - 'clerk': access to everything EXCEPT the audit log, and a
        cut-down Settings page (theme, own phone/email, language only
        — no school branding, no adding other admins).
    """
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('clerk', 'Clerk'),
    ]
    THEME_CHOICES = [
        ('system', 'Match System'),
        ('light', 'Light'),
        ('dark', 'Dark'),
    ]
    LANGUAGE_CHOICES = [
        ('en', 'English'),
        ('sw', 'Swahili'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='admin_profile')
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    position = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='admin')
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default='system')
    language = models.CharField(max_length=5, choices=LANGUAGE_CHOICES, default='en')
    profile_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.full_name or self.user.username


class AuditLog(models.Model):
    """
    Tracks who created/updated/deleted each student. student_number
    and student_name are snapshotted as plain text so the log still
    reads correctly even after a student is deleted.
    """
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('deleted', 'Deleted'),
        ('pocket_money_deposit', 'Pocket Money Deposit'),
        ('pocket_money_withdrawal', 'Pocket Money Withdrawal'),
        ('pocket_money_deleted', 'Pocket Money Transaction Deleted'),
    ]

    student_number = models.CharField(max_length=20)
    student_name = models.CharField(max_length=200)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='audit_actions'
    )
    performed_by_name = models.CharField(max_length=150, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_action_display()} - {self.student_name}"
