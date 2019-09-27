# -*- coding: utf-8 -*-

from builtins import object
from django.conf import settings  # noqa

from appconf import AppConf

PAYMENT_TYPE_DIRECT_DEBIT = 'dd'
PAYMENT_TYPE_CREDIT_CARD = 'cc'
PAYMENT_TYPE_PAYPAL = 'paypal'

REDIRECTING_PAYMENT_TYPES = [
    PAYMENT_TYPE_CREDIT_CARD,
    PAYMENT_TYPE_PAYPAL,
]
INSTANT_SUBSCRIPTION_PAYMENT_TYPES = [
    PAYMENT_TYPE_DIRECT_DEBIT,
]

class WechangePaymentsDefaultSettings(AppConf):
    
    class Meta(object):
        prefix = 'PAYMENTS'
        
    BACKEND = 'wechange_payments.backends.BetterPaymentBackend'
    ACCEPTED_PAYMENT_METHODS = [
        PAYMENT_TYPE_DIRECT_DEBIT,
        PAYMENT_TYPE_CREDIT_CARD,
        PAYMENT_TYPE_PAYPAL
    ]
    
    SEND_MAIL_FUNCTION = 'django.core.mail.send_mail'
    USE_HOOK_INSTEAD_OF_SEND_MAIL = False
    
    """ Payment Source Infos """
    
    PAYMENT_RECIPIENT_NAME = None # 'WECHANGE eG'
    SEPA_CREDITOR_ID = None # 
    
    """ Payment Form settings """
    
    # the displayed slider min amount
    MINIMUM_PAYMENT_AMOUNT = 1.0
    # the displayed slider max amount
    MAXIMUM_PAYMENT_AMOUNT = 20.0
    # the displayed slider default amount
    DEFAULT_PAYMENT_AMOUNT = 5.0
    
    # the lowest allowed amount for a payment transaction
    MINIMUM_ALLOWED_PAYMENT_AMOUNT = 1.0 
    # the highest allowed amount for a payment transaction
    MAXIMUM_ALLOWED_PAYMENT_AMOUNT = 100.0 
    
    # how many days until the payment popup is shown again for non-subscribers, after clicking it away
    POPUP_SHOW_AGAIN_DAYS = 30
    # how many days after a new user registered to show the popup, instead of immediately
    POPUP_DELAY_FOR_NEW_USERS_DAYS = 7
    # how many seconds till the "processing payment" page shows a "we're taking long..." message
    LATE_PAYMENT_PROCESS_MESSAGE_SECONDS = 30
    
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


