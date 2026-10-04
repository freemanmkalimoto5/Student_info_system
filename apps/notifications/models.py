from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    TYPE_CHOICES = [
        ('duplicate_student', 'Possible duplicate student'),
        ('system_check', 'System check'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('fixed', 'Fixed'),
    ]

    notif_type = models.CharField(max_length=30, choices=TYPE_CHOICES, default='duplicate_student')
    title = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    existing_student = models.ForeignKey(
        'students.Student', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='duplicate_notifications',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    fixed_at = models.DateTimeField(null=True, blank=True)
    fixed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='+',
    )

    class Meta:
        ordering = ['status', '-created_at']

    def __str__(self):
        return f"[{self.get_status_display()}] {self.title}"

    def mark_fixed(self, user):
        self.status = 'fixed'
        self.fixed_at = timezone.now()
        self.fixed_by = user
        self.save(update_fields=['status', 'fixed_at', 'fixed_by'])
