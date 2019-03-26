# -*- coding: utf-8 -*-
"""
If the default usage of the views suits you, simply use a line like
this one in your root URLconf to set up the default URLs::
"""

from __future__ import unicode_literals

from django.conf.urls import url
from wechange_payments import views

urlpatterns = [
    url(r'^payments/sepa/$', views.make_sepa_payment, name='make-sepa-payment'),
]
