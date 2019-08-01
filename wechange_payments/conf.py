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
    USE_HOOK_INSTEAD_OF_SEND_MAIL = False
    
    """ Payment Source Infos """
    
    PAYMENT_RECIPIENT_NAME = None # 'WECHANGE eG'
    SEPA_CREDITOR_ID = None # 
    
    """ Payment Form settings """
    
    MINIMUM_PAYMENT_AMOUNT = 1.0
    MAXIMUM_PAYMENT_AMOUNT = 20.0
    DEFAULT_PAYMENT_AMOUNT = 5.0
    
    """ Betterpayment-settings """
    
    BETTERPAYMENT_API_KEY = ''
    BETTERPAYMENT_INCOMING_KEY = ''
    BETTERPAYMENT_OUTGOING_KEY = ''
    BETTERPAYMENT_API_DOMAIN = ''


    
    

class NonPrefixDefaultSettings(AppConf):
    """ Settings without a prefix namespace to provide default setting values for other apps.
        These are settings used by default in cosinnus apps, such as avatar dimensions, etc.
    """
    
    class Meta(object):
        prefix = ''
        
    # django_countries settings
    COUNTRIES_FIRST = ['de', 'at', 'ch']
    COUNTRIES_FIRST_REPEAT = True


