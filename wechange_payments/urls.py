# -*- coding: utf-8 -*-
"""
If the default usage of the views suits you, simply use a line like
this one in your root URLconf to set up the default URLs::
"""

from django.conf.urls import url
from wechange_payments.views import api, frontend

urlpatterns = [
    url(r'^account/subscription/$', frontend.overview, name='overview'),
    url(r'^account/subscription/payment/$', frontend.payment, name='payment'),
    url(r'^account/subscription/payment/(?P<pk>\d+)/success/$', frontend.payment_success, name='payment-success'),
    url(r'^account/subscription/payment/infos/$', frontend.payment_infos, name='payment-infos'),
    url(r'^account/subscription/mine/$', frontend.my_subscription, name='my-subscription'),
    #url(r'^account/subscription/past/$', frontend.past_subscriptions, name='past-subscriptions'),
    url(r'^account/subscription/cancel/$', frontend.cancel_subscription, name='cancel-subscription'),
    url(r'^account/invoices/$', frontend.invoices, name='invoices'),
    
    url(r'^welcome/contribute/$', frontend.welcome_page, name='welcome-page'),
    
    url(r'^payments/api/payment/$', api.make_payment, name='api-make-payment'),
    url(r'^payments/api/subscription-payment/$', api.make_subscription_payment, name='api-make-subscription-payment'),
    url(r'^payments/api/subscription-change-amount/$', api.subscription_change_amount, name='api-subscription-change-amount'),
    url(r'^payments/api/postback_endpoint/$', api.postback_endpoint, name='api-postback-endpoint'),
]
