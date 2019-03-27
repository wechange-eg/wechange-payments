# -*- coding: utf-8 -*-

from builtins import object
from django.conf import settings  # noqa

from appconf import AppConf


class WechangePaymentsDefaultSettings(AppConf):
    
    class Meta(object):
        prefix = 'PAYMENTS'
        
    BACKEND = 'wechange_payments.backends.BetterPaymentBackend'
    ACCEPTED_PAYMENT_METHODS = ['dd'] # ['cc', 'dd', 'paypal']
    
    """ Betterpayment-settings """
    
    BETTERPAYMENT_API_KEY = ''
    BETTERPAYMENT_INCOMING_KEY = ''
    BETTERPAYMENT_OUTGOING_KEY = ''
    BETTERPAYMENT_API_DOMAIN = ''
    
