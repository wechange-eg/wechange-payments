# -*- coding: utf-8 -*-

from django.contrib import admin
from wechange_payments.models import Payment, TransactionLog, Subscription


class PaymentAdmin(admin.ModelAdmin):
    list_display = ('internal_transaction_id', 'user', 'amount', 'type', 'completed_at', 'vendor_transaction_id',)
    list_filter = ('type',)
    search_fields = ('user__first_name', 'user__last_name', 'user__email', 'completed_at', 'vendor_transaction_id', 'internal_transaction_id',)
    readonly_fields = ('backend', 'vendor_transaction_id', 'internal_transaction_id', 'amount', 'completed_at', 'extra_data')
    raw_id_fields = ('user',)

admin.site.register(Payment, PaymentAdmin)


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

