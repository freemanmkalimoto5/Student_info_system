from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('student', 'transaction_type', 'amount', 'created_by', 'created_at')
    list_filter = ('transaction_type',)
    search_fields = ('student__student_number', 'student__first_name', 'student__last_name')
