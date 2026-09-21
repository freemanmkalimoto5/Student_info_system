from django.contrib import admin

from .models import SiteSettings, ParentAccount, AdminProfile, AuditLog


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ('school_name', 'contact_email', 'contact_phone', 'updated_at')

    def has_add_permission(self, request):
        # Singleton: block adding a second row from the admin.
        return not SiteSettings.objects.exists()


@admin.register(ParentAccount)
class ParentAccountAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'phone', 'relationship', 'user')
    search_fields = ('full_name', 'phone', 'user__username')
    filter_horizontal = ('students',)


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'full_name', 'position', 'profile_completed', 'created_at')
    list_filter = ('profile_completed',)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'action', 'student_name', 'student_number', 'performed_by_name')
    list_filter = ('action',)
    search_fields = ('student_name', 'student_number', 'performed_by_name')
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False  # audit log entries are only ever created by the app itself
