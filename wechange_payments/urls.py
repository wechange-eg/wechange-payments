# -*- coding: utf-8 -*-
"""
If the default usage of the views suits you, simply use a line like
this one in your root URLconf to set up the default URLs::
"""

from django.conf.urls import url
from wechange_payments.views import api, frontend

urlpatterns = [
    url(r'^payments/payment/$', api.make_payment, name='api-make-payment'),
    url(r'^payments/subscription-payment/$', api.make_subscription_payment, name='api-make-subscription-payment'),
    url(r'^payments/postback_endpoint/$', api.postback_endpoint, name='api-postback-endpoint'),
    
    url(r'^account/subscription/overview/$', frontend.overview, name='overview'),
    url(r'^account/subscription/payment/$', frontend.payment, name='payment'),
    url(r'^account/subscription/payment/(?P<payment_id>\d+)/success/$', frontend.payment_success, name='payment-success'),
    url(r'^account/subscription/mine/$', frontend.subscriptions, name='subscriptions'),
    url(r'^welcome/contribute/$', frontend.welcome_page, name='welcome-page'),
]
