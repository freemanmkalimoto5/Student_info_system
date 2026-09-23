from django.contrib import admin

from .models import Student, ImportJob


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_number', 'first_name', 'last_name', 'grade_class', 'status', 'age')
    list_filter = ('status', 'grade_class', 'parish')
    search_fields = ('student_number', 'first_name', 'last_name', 'parish')
    fieldsets = (
        ('Identity', {
            'fields': ('student_number', 'first_name', 'last_name', 'date_of_birth', 'age', 'photo')
        }),
        ('Academic', {
            'fields': ('grade_class', 'status', 'enrollment_date')
        }),
        ('Parents / Guardian', {
            'fields': (
                'father_name', 'father_phone',
                'mother_name', 'mother_phone',
                'guardian_name', 'guardian_phone', 'guardian_relationship',
            )
        }),
        ('Community', {
            'fields': ('parish',)
        }),
        ('Address', {
            'fields': ('full_address', 'region', 'district', 'ward')
        }),
    )
    readonly_fields = ('enrollment_date',)


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'processed_rows', 'total_rows', 'created_count', 'created_by', 'created_at')
    list_filter = ('status',)
    readonly_fields = [f.name for f in ImportJob._meta.fields]

    def has_add_permission(self, request):
        return False  # jobs are only ever created by the import view itself
