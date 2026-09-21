from django.contrib import admin

from .models import IDCard


@admin.register(IDCard)
class IDCardAdmin(admin.ModelAdmin):
    list_display = ('student', 'generated_at', 'print_count', 'last_printed_at')
    readonly_fields = ('generated_at', 'regenerated_at')
    search_fields = ('student__student_number', 'student__first_name', 'student__last_name')
