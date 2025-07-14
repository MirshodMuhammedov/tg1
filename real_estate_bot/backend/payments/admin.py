from django.contrib import admin
from .models import Payment, ClickTransaction, PaymeTransaction

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'amount', 'payment_method', 'service_type', 
        'status', 'transaction_id', 'created_at'
    ]
    list_filter = ['payment_method', 'service_type', 'status', 'created_at']
    search_fields = ['user__first_name', 'user__last_name', 'transaction_id']
    readonly_fields = ['created_at', 'completed_at']
    
    fieldsets = (
        ('Информация о платеже', {
            'fields': ('user', 'amount', 'payment_method', 'service_type', 'description')
        }),
        ('Статус', {
            'fields': ('status', 'transaction_id', 'external_id')
        }),
        ('Связанные объекты', {
            'fields': ('property',)
        }),
        ('Временные метки', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )

@admin.register(ClickTransaction)
class ClickTransactionAdmin(admin.ModelAdmin):
    list_display = ['payment', 'click_trans_id', 'amount', 'action', 'error', 'created_at']
    list_filter = ['action', 'error', 'created_at']
    search_fields = ['click_trans_id', 'merchant_trans_id']

@admin.register(PaymeTransaction)
class PaymeTransactionAdmin(admin.ModelAdmin):
    list_display = ['payment', 'payme_id', 'amount', 'state', 'create_time']
    list_filter = ['state']
    search_fields = ['payme_id']