from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'notif_type', 'status', 'existing_student', 'created_at', 'fixed_at')
    list_filter = ('status', 'notif_type')
    search_fields = ('title', 'message')
