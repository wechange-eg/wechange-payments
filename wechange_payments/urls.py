# -*- coding: utf-8 -*-
"""
If the default usage of the views suits you, simply use a line like
this one in your root URLconf to set up the default URLs::
"""

from django.urls import path
from wechange_payments.views import api, frontend

urlpatterns = [
    path('account/contribution/', frontend.overview, name='overview'),
    path('account/contribution/payment/', frontend.payment, name='payment'),
    path('account/contribution/payment/update/', frontend.payment_update, name='payment-update'),
    path('account/contribution/payment/<int:pk>/process/', frontend.payment_process, name='payment-process'),
    path('account/contribution/payment/<int:pk>/success/', frontend.payment_success, name='payment-success'),
    path('account/contribution/payment/infos/', frontend.payment_infos, name='payment-infos'),
    path('account/contribution/mine/', frontend.my_subscription, name='my-subscription'),
    path('account/contribution/suspended/', frontend.suspended_subscription, name='suspended-subscription'),
    #path('account/contribution/past/', frontend.past_subscriptions, name='past-subscriptions'),
    path('account/contribution/cancel/', frontend.cancel_subscription, name='cancel-subscription'),
    path('account/contribution/debug-delete/', frontend.debug_delete_subscription, name='debug-delete-subscription'),
    path('account/invoices/', frontend.invoices, name='invoices'),
    path('account/invoices/<int:pk>/', frontend.invoice_detail, name='invoice-detail'),
    path('account/invoices/<int:pk>/download/', frontend.invoice_download, name='invoice-download'),
    path('account/additional_invoices/<int:pk>/download/', frontend.additional_invoice_download, name='additional-invoice-download'),
    
    #path('payments/api/payment/', api.make_payment, name='api-make-payment'),
    path('payments/api/subscription-payment/', api.make_subscription_payment, name='api-make-subscription-payment'),
    path('payments/api/subscription-change-amount/', api.subscription_change_amount, name='api-subscription-change-amount'),
    path('payments/api/success_endpoint/', api.success_endpoint, name='api-success-endpoint'),
    path('payments/api/error_endpoint/', api.error_endpoint, name='api-error-endpoint'),
    path('payments/api/postback_endpoint/', api.postback_endpoint, name='api-postback-endpoint'),
    path('payments/api/snooze-popup/', api.snooze_popup, name='api-snooze-popup'),
]
