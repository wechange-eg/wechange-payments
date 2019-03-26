# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from builtins import object
from django.conf import settings  # noqa
from django.utils.translation import ugettext_lazy as _

from appconf import AppConf


class WechangePaymentsDefaultSettings(AppConf):
    
    class Meta(object):
        prefix = 'PAYMENTS'
        
    BACKEND = 'wechange_payments.backends.BetterPaymentBackend'
    
    
    """ Betterpayment-settings """
    
    BETTERPAYMENT_API_KEY = ''
    BETTERPAYMENT_INCOMING_KEY = ''
    BETTERPAYMENT_OUTGOING_KEY = ''
    BETTERPAYMENT_API_DOMAIN = ''
    
