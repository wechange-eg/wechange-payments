# -*- coding: utf-8 -*-

from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _

from wechange_payments.backends import get_invoice_backend, get_additional_invoice_backends
from wechange_payments.models import Payment, TransactionLog, Subscription, \
    Invoice, AdditionalInvoice
from cosinnus.conf import settings
from datetime import timedelta
from wechange_payments.payment import process_due_subscription_payments,\
    terminate_suspended_subscription
from django.utils.timezone import now
from wechange_payments.mails import send_payment_event_payment_email,\
    PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED, PAYMENT_EVENT_SUCCESSFUL_PAYMENT
from django.utils import translation
from django.contrib.admin import DateFieldListFilter


class PaymentAdmin(admin.ModelAdmin):
    list_display = ('internal_transaction_id', 'status', 'user_account_name', 'invoice_name', 'email', 'amount', 'type', 'completed_at', 'subscription', 'additional_invoices')
    list_filter = ('type', ('completed_at', DateFieldListFilter),)
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'email', 'first_name', 'last_name', 'completed_at', 'vendor_transaction_id', 'internal_transaction_id',)
    readonly_fields = ('backend', 'vendor_transaction_id', 'internal_transaction_id', 'amount', 'is_reference_payment', 'completed_at', 'last_action_at', 'extra_data', 'subscription')
    raw_id_fields = ('user',)
    actions = ['create_invoice', 'create_additional_invoices', 'resend_payment_email',]
    
    def user_account_name(self, obj):
        return obj.user.get_full_name()
    
    def invoice_name(self, obj):
        return f'{obj.first_name} {obj.last_name}'
    
    def additional_invoices(self, obj):
        return obj.additional_invoices.count()
    
    def resend_payment_email(self, request, queryset):
        for payment in queryset:
            if payment.status == Payment.STATUS_PAID:
                send_payment_event_payment_email(payment, PAYMENT_EVENT_SUCCESSFUL_PAYMENT)
                message = 'Sent email.'
                self.message_user(request, message)
            else:
                message = 'Payment not successful, no email sent'
                self.message_user(request, message)
    resend_payment_email.short_description = "Resend payment success email"
    
    def create_invoice(self, request, queryset):
        invoice_backend = get_invoice_backend()
        for payment in queryset:
            invoice_backend.create_invoice_for_payment(payment, threaded=True)
        
        message = _('Started invoice creation for %(number)d payment(s) in background.') % {'number': len(queryset)}
        self.message_user(request, message)
    create_invoice.short_description = _("Create invoice in Invoice API (threaded)")
    
    def create_additional_invoices(self, request, queryset):
        for payment in queryset:
            for additional_invoice_backend in get_additional_invoice_backends():
                additional_invoice_backend.create_invoice_for_payment(payment, threaded=True, additional_invoice=True)
        
        message = _('Started additional invoice creation for %(number)d payment(s) in background.') % {'number': len(queryset)}
        self.message_user(request, message)
    create_additional_invoices.short_description = _("Create additional invoices in Invoice API (threaded)")
    
    def has_delete_permission(self, request, obj=None):
        """ Can't delete/add Payments """
        return False
    
    def has_add_permission(self, request, obj=None):
        """ Can't delete/add Payments """
        return False
    
admin.site.register(Payment, PaymentAdmin)


class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('user', 'is_ready', 'state', 'payment', 'user_account_name', 'payment_name', 'payment_email', 'created', 'last_action_at')
    list_filter = ('is_ready', 'state', )
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'payment__vendor_transaction_id', 'payment__internal_transaction_id', 'payment__email', 'payment__first_name', 'payment__last_name', 'created')
    readonly_fields = ('state', 'backend')
    raw_id_fields = ('user',)
    actions = ['create_invoice',]
    
    def user_account_name(self, obj):
        return obj.user.get_full_name()
    
    def payment_name(self, obj):
        return f'{obj.payment.first_name} {obj.payment.last_name}'
    
    def payment_email(self, obj):
        return obj.payment.email
    
    def create_invoice(self, request, queryset):
        invoice_backend = get_invoice_backend()
        for invoice in queryset:
            invoice_backend.create_invoice(invoice, threaded=True)
        message = _('Started invoice creation for %(number)d payment(s) in background.') % {'number':len(queryset)}
        self.message_user(request, message)
    create_invoice.short_description = _("Run/continue invoice in Invoice API (threaded)")
    
    def has_delete_permission(self, request, obj=None):
        """ Can't delete/add Invoices """
        return False
    
    def has_add_permission(self, request, obj=None):
        """ Can't delete/add Invoices """
        return False
    
admin.site.register(Invoice, InvoiceAdmin)


class AdditionalInvoiceAdmin(InvoiceAdmin):
    
    def create_invoice(self, request, queryset):
        count = 0
        for additional_invoice_backend in get_additional_invoice_backends():
            for invoice in queryset:
                if invoice.backend == '%s.%s' %(additional_invoice_backend.__class__.__module__, additional_invoice_backend.__class__.__name__):
                    additional_invoice_backend.create_invoice(invoice, threaded=True)
                    count +=1
        message = _('Started additional invoice creation for %(count)d of %(total)d selected payment(s) in background.') % {'count': count, 'total': len(queryset)}
        self.message_user(request, message)
    
    create_invoice.short_description = _("Run/continue additional invoice in Invoice API (threaded)")

admin.site.register(AdditionalInvoice, AdditionalInvoiceAdmin)


class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ('created', 'url', 'type', 'created', 'data', )
    list_filter = ('created', 'url', 'type',)
    search_fields = ('url', 'type', 'data',)
    readonly_fields = ('url', 'type', 'data', 'created',)
    
    def has_delete_permission(self, request, obj=None):
        """ Can't delete/add Transaction Logs """
        return False
    
    def has_add_permission(self, request, obj=None):
        """ Can't delete/add Transaction Logs """
        return False

admin.site.register(TransactionLog, TransactionLogAdmin)


class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'state', 'amount', 'next_due_date', 'has_problems', 'created', 'terminated')
    list_filter = ('state', 'has_problems', )
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'reference_payment__vendor_transaction_id', 'reference_payment__internal_transaction_id', 'created')
    readonly_fields = ('user', 'state', 'amount', 'num_attempts_recurring', 'next_due_date',)
    raw_id_fields = ('user',)
    
    actions = ['resend_both_initial_emails', 'resend_subscription_email', 'terminate_suspended',]
    
    def resend_both_initial_emails(self, request, queryset):
        for subscription in queryset:
            if subscription.state in Subscription.ACTIVE_STATES:
                send_payment_event_payment_email(subscription.reference_payment, PAYMENT_EVENT_SUCCESSFUL_PAYMENT)
                send_payment_event_payment_email(subscription.reference_payment, PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED)
                message = 'Sent emails.'
                self.message_user(request, message)
            else:
                message = 'Subscription not active, no emails sent'
                self.message_user(request, message)
    resend_both_initial_emails.short_description = "Resend initial mails (payment & subscription)"
    
    def resend_subscription_email(self, request, queryset):
        for subscription in queryset:
            if subscription.state in Subscription.ACTIVE_STATES:
                send_payment_event_payment_email(subscription.reference_payment, PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED)
                message = 'Sent emails.'
                self.message_user(request, message)
            else:
                message = 'Subscription not active, no emails sent'
                self.message_user(request, message)
    resend_subscription_email.short_description = "Resend initial subscription mail"
    
    def terminate_suspended(self, request, queryset):
        for subscription in queryset:
            if subscription.state == Subscription.STATE_99_FAILED_PAYMENTS_SUSPENDED:
                # switch language to user's preference language
                cur_language = translation.get_language()
                try:
                    translation.activate(getattr(subscription.user.cosinnus_profile, 'language', settings.LANGUAGES[0][0]))
                    # terminate subscription correctly
                    terminate_suspended_subscription(subscription)
                finally:
                    translation.activate(cur_language)
                message = f'Subscription {subscription.id} was suspended.'
                level = messages.SUCCESS
            else:
                message = f'Subscription {subscription.id} could not be terminated because it is not in a SUSPENDED state!'
                level = messages.ERROR
            self.message_user(request, message, level=level)
    terminate_suspended.short_description = "TERMINATE subscription (suspended subscriptions only!)"
    
    if getattr(settings, 'PAYMENTS_TEST_PHASE', False) or getattr(settings, 'COSINNUS_PAYMENTS_ENABLED_ADMIN_ONLY', False) \
        or getattr(settings, 'COSINNUS_PAYMENTS_ADMIN_DEBUG_FUNCTIONS_ENABLED', False):
        actions = actions + ['debug_timeshift_due_date', 'debug_process_subscriptions_now', 'debug_terminate_subscriptions']
        
        def debug_terminate_subscriptions(self, request, queryset):
            for subscription in queryset:
                subscription.state = Subscription.STATE_0_TERMINATED
                subscription.cancelled = now()
                subscription.save()
            message = 'Terminated subscriptions.'
            self.message_user(request, message)
        debug_terminate_subscriptions.short_description = "DEBUG: Terminate selected subcriptions"
        
        def debug_timeshift_due_date(self, request, queryset):
            for subscription in queryset:
                subscription.next_due_date = subscription.next_due_date - timedelta(days=32)
                subscription.save()
            message = 'Shifted subscription due date back 32 days.'
            self.message_user(request, message)
        debug_timeshift_due_date.short_description = "DEBUG: Shift back due date 32 days for selected"
        
        def debug_process_subscriptions_now(self, request, queryset):
            process_due_subscription_payments()
            message = 'Ran subscription processing!'
            self.message_user(request, message)
        debug_process_subscriptions_now.short_description = "DEBUG: Run subscription processing/expiry now!"
    
    def has_delete_permission(self, request, obj=None):
        """ Can't delete/add Subscriptions """
        return False
    
    def has_add_permission(self, request, obj=None):
        """ Can't delete/add Subscriptions """
        return False
        
admin.site.register(Subscription, SubscriptionAdmin)



