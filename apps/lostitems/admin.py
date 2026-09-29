from django.contrib import admin

from .models import LostItem, LostItemPayment


class PaymentInline(admin.TabularInline):
    model = LostItemPayment
    extra = 0
    readonly_fields = ('created_at', 'received_by')


@admin.register(LostItem)
class LostItemAdmin(admin.ModelAdmin):
    list_display = ('student', 'item_name', 'price', 'status', 'date_lost')
    list_filter = ('status',)
    search_fields = ('student__student_number', 'student__first_name', 'student__last_name', 'item_name')
    inlines = [PaymentInline]
