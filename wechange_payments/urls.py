# -*- coding: utf-8 -*-
"""
If the default usage of the views suits you, simply use a line like
this one in your root URLconf to set up the default URLs::
"""

from django.conf.urls import url
from wechange_payments import views

urlpatterns = [
    url(r'^payments/payment/$', views.make_payment, name='make-payment'),
    url(r'^payments/postback_endpoint/$', views.postback_endpoint, name='postback-endpoint'),
]
