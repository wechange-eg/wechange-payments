# -*- coding: utf-8 -*-

from builtins import object
from django.conf import settings  # noqa

from appconf import AppConf


class WechangePaymentsDefaultSettings(AppConf):
    
    class Meta(object):
        prefix = 'PAYMENTS'
        
    BACKEND = 'wechange_payments.backends.BetterPaymentBackend'
    ACCEPTED_PAYMENT_METHODS = ['dd'] # ['cc', 'dd', 'paypal']
    
    SEND_MAIL_FUNCTION = 'django.core.mail.send_mail'
    
    """ Payment Source Infos """
    
    PAYMENT_RECIPIENT_NAME = None # 'WECHANGE eG'
    SEPA_CREDITOR_ID = None # 
    
    """ Betterpayment-settings """
    
    BETTERPAYMENT_API_KEY = ''
    BETTERPAYMENT_INCOMING_KEY = ''
    BETTERPAYMENT_OUTGOING_KEY = ''
    BETTERPAYMENT_API_DOMAIN = ''
    
