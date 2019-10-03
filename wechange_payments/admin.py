# -*- coding: utf-8 -*-

from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from wechange_payments.backends import get_invoice_backend
from wechange_payments.models import Payment, TransactionLog, Subscription, \
    Invoice


class PaymentAdmin(admin.ModelAdmin):
    list_display = ('internal_transaction_id', 'status', 'user', 'amount', 'type', 'completed_at', 'vendor_transaction_id',)
    list_filter = ('type',)
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'completed_at', 'vendor_transaction_id', 'internal_transaction_id',)
    readonly_fields = ('backend', 'vendor_transaction_id', 'internal_transaction_id', 'amount', 'completed_at', 'last_action_at', 'extra_data')
    raw_id_fields = ('user',)
    actions = ['create_invoice',]
    
    def create_invoice(self, request, queryset):
        invoice_backend = get_invoice_backend()
        for payment in queryset:
            invoice_backend.create_invoice_for_payment(payment, threaded=True)
        message = _('Started invoice creation for %(number)d payment(s) in background.') % {'number':len(queryset)}
        self.message_user(request, message)
    create_invoice.short_description = _("Create invoice in Invoice API (threaded)")
    
admin.site.register(Payment, PaymentAdmin)


class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_ready', 'state', 'payment', 'created', 'last_action_at')
    list_filter = ('is_ready', 'state', )
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'payment__vendor_transaction_id', 'payment__internal_transaction_id', 'created')
    readonly_fields = ('state',)
    raw_id_fields = ('user',)
    actions = ['create_invoice',]
    
    def create_invoice(self, request, queryset):
        invoice_backend = get_invoice_backend()
        for invoice in queryset:
            invoice_backend.create_invoice(invoice, threaded=True)
        message = _('Started invoice creation for %(number)d payment(s) in background.') % {'number':len(queryset)}
        self.message_user(request, message)
    create_invoice.short_description = _("Run/continue invoice in Invoice API (threaded)")
    
admin.site.register(Invoice, InvoiceAdmin)


class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ('created', 'url', 'type', 'data',)
    list_filter = ('created', 'url', 'type',)
    search_fields = ('url', 'type', 'data',)
    readonly_fields = ('url', 'type', 'data', 'created',)

admin.site.register(TransactionLog, TransactionLogAdmin)


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'state', 'amount', 'next_due_date', 'has_problems', 'created', 'terminated')
    list_filter = ('state', 'has_problems', )
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'reference_payment__vendor_transaction_id', 'reference_payment__internal_transaction_id', 'created')
    readonly_fields = ('state', 'amount',)
    raw_id_fields = ('user',)

admin.site.register(Subscription, SubscriptionAdmin)



