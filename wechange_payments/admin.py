# -*- coding: utf-8 -*-

from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

from wechange_payments.backends import get_invoice_backend
from wechange_payments.models import Payment, TransactionLog, Subscription, \
    Invoice
from cosinnus.conf import settings
from datetime import timedelta
from wechange_payments.payment import process_due_subscription_payments


class PaymentAdmin(admin.ModelAdmin):
    list_display = ('internal_transaction_id', 'status', 'user', 'amount', 'type', 'completed_at', 'vendor_transaction_id',)
    list_filter = ('type',)
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'completed_at', 'vendor_transaction_id', 'internal_transaction_id',)
    readonly_fields = ('backend', 'vendor_transaction_id', 'internal_transaction_id', 'amount', 'is_reference_payment', 'completed_at', 'last_action_at', 'extra_data')
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
    list_display = ('created', 'url', 'type', 'created', 'data', )
    list_filter = ('created', 'url', 'type',)
    search_fields = ('url', 'type', 'data',)
    readonly_fields = ('url', 'type', 'data', 'created',)

admin.site.register(TransactionLog, TransactionLogAdmin)


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'state', 'amount', 'next_due_date', 'has_problems', 'created', 'terminated')
    list_filter = ('state', 'has_problems', )
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'reference_payment__vendor_transaction_id', 'reference_payment__internal_transaction_id', 'created')
    readonly_fields = ('user', 'state', 'amount', 'num_attempts_recurring', 'next_due_date',)
    raw_id_fields = ('user',)
    
    if getattr(settings, 'PAYMENTS_TEST_PHASE', False) or getattr(settings, 'COSINNUS_PAYMENTS_ENABLED_ADMIN_ONLY', False):
        actions = ['debug_timeshift_due_date', 'debug_process_subscriptions_now']
    
        def debug_timeshift_due_date(self, request, queryset):
            for subscription in queryset:
                subscription.next_due_date = subscription.next_due_date - timedelta(days=32)
                subscription.save()
            message = 'Shifted subscription due date back 32 days.'
            self.message_user(request, message)
        debug_timeshift_due_date.short_description = "DEBUG: Shift back due date 32 days"
        
        def debug_process_subscriptions_now(self, request, queryset):
            process_due_subscription_payments()
            message = 'Ran subscription processing!'
            self.message_user(request, message)
        debug_process_subscriptions_now.short_description = "DEBUG: Run subscription processing/expiry now!"
        
admin.site.register(Subscription, SubscriptionAdmin)



