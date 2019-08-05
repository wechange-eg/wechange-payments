# -*- coding: utf-8 -*-
"""
If the default usage of the views suits you, simply use a line like
this one in your root URLconf to set up the default URLs::
"""

from django.conf.urls import url
from wechange_payments.views import api, frontend

urlpatterns = [
    url(r'^payments/payment/$', api.make_payment, name='api-make-payment'),
    url(r'^payments/postback_endpoint/$', api.postback_endpoint, name='api-postback-endpoint'),
    
    url(r'^account/payments/$', frontend.payment, name='payment'),
    url(r'^welcome/contribute/$', frontend.welcome_page, name='welcome-page'),
]
