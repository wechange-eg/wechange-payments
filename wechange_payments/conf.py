# -*- coding: utf-8 -*-

from builtins import object
from django.conf import settings  # noqa

from appconf import AppConf
from django.utils.translation import pgettext_lazy

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
        
    BACKEND = 'wechange_payments.backends.payment.betterpayments.BetterPaymentBackend'
    INVOICE_BACKEND = 'wechange_payments.backends.invoice.lexoffice.LexofficeInvoiceBackend'
    
    ACCEPTED_PAYMENT_METHODS = [
        PAYMENT_TYPE_DIRECT_DEBIT,
        PAYMENT_TYPE_CREDIT_CARD,
        PAYMENT_TYPE_PAYPAL
    ]
    
    SEND_MAIL_FUNCTION = 'django.core.mail.send_mail'
    USE_HOOK_INSTEAD_OF_SEND_MAIL = False
    
    """ Payment Source Infos """
    
    PAYMENT_RECIPIENT_NAME = 'Die WECHANGE Genossenschaft'
    SEPA_CREDITOR_ID = None #
    
    """ Payments app settings """
    
    # if set to True, prevent new payments from being made, cronjobs from running, and prevent any changes
    # to users' payments except for cancelling their subscription
    SOFT_DISABLE_PAYMENTS = False
    
    """ Payment Form settings """
    
    # the displayed slider min amount
    MINIMUM_MONTHLY_AMOUNT = 1.0
    # the displayed slider max amount
    MAXIMUM_MONTHLY_AMOUNT = 20.0
    # the displayed slider default amount
    DEFAULT_MONTHLY_AMOUNT = 10.0
    
    # the lowest allowed amount for a monthly payment
    MINIMUM_ALLOWED_MONTHLY_AMOUNT = 1.0
    # the highest allowed amount for a monthly payment
    MAXIMUM_ALLOWED_MONTHLY_AMOUNT = 100.0

    # the lowest allowed amount for a payment transaction
    MINIMUM_ALLOWED_PAYMENT_AMOUNT = MINIMUM_MONTHLY_AMOUNT
    # the highest allowed amount for payment transaction
    MAXIMUM_ALLOWED_PAYMENT_AMOUNT = MAXIMUM_MONTHLY_AMOUNT * 12

    # how many days until the payment popup is shown again for non-subscribers, after clicking it away
    POPUP_SHOW_AGAIN_DAYS = 30
    # how many days after a new user registered to show the popup, instead of immediately
    POPUP_DELAY_FOR_NEW_USERS_DAYS = 5
    # how many seconds till the "processing payment" page shows a "we're taking long..." message
    LATE_PAYMENT_PROCESS_MESSAGE_SECONDS = 30
    # how many days before a due recurring SEPA payment will a pre-notification be sent
    PRE_NOTIFICATION_BEFORE_PAYMENT_DAYS = 10
    # should the payment popup show a "no thanks" button to dismiss it?
    POPUP_SHOW_NO_THANKS_BUTTON = False
    
    # should SEPA payments be treated as instantly paid, or wait for a success postback from betterpayments?
    # all signs for betterpayment point to "yes"
    SEPA_IS_INSTANTLY_SUCCESSFUL = True
    
    # how many minutes since the last `last_action_at` should we wait before attempting another
    # invoice retrieval via API if the last one has failed. retrieval re-attempts are done when
    # the user tries to access their unretrieved invoice, or with a gather-all-missing cronjob
    INVOICE_PROVIDER_RETRY_MINUTES = 5
    
    # the default tax rate in percent to use with the invoice provider. change this for any MwSt changes!
    INVOICE_PROVIDER_TAX_RATE_PERCENT = 19
    
    # paid-for-item title on the PDF invoice
    INVOICE_LINE_ITEM_NAME = pgettext_lazy('Invoice PDF, important!', 'User fee for %(portal_name)s')
    
    # paid-for-item description on the PDF invoice
    INVOICE_LINE_ITEM_DESCRIPTION = pgettext_lazy('Invoice PDF, important!', 'Electronic service - Ref-Nr. %(user_id)d')
    
    # a supplementary remark at the end of each invoice. left out if None.
    INVOICE_REMARK = None
    
    # A lock for currently not-implemented behaviour, meant to make it clearer that the code
    # is not yet ready for WAITING, postponed payments that get cashed in later.
    # currently (and with the switch set to False), new subscriptions can only replace 
    # the active subscription instantly and prolong its running time!
    # DO NOT set this to True right now!
    POSTPONED_PAYMENTS_IMPLEMENTED = False
    
    """ Cron job settings """
    # if this contains a list of portal slugs as str, the cron will only run 
    # if the current portal's slug matches one in the list.
    # if it is empty, the cron will run without portal restriction
    CRON_ENABLED_FOR_SPECIFIC_PORTAL_SLUGS_ONLY = []
    
    """ Test System settings """
    
    # if True, enables additional views for payments
    TEST_PHASE = False
    
    # WARNING: never enable this setting in a production environment!
    # if set to True, will skip the hardcoded safety checks in `user_pre_recurring_payment_safety_checks()`
    OVERRIDE_SAFETY_CHECKS = False
    
    """ Betterpayment settings """
    
    BETTERPAYMENT_API_KEY = ''
    BETTERPAYMENT_INCOMING_KEY = ''
    BETTERPAYMENT_OUTGOING_KEY = ''
    BETTERPAYMENT_API_DOMAIN = ''

    # the auth data parameters for the configured invoice backend
    # should only be defined in .env
    """
    Example:
    
    INVOICE_BACKEND_AUTH_DATA = {
        'api_domain': 'https://wchg-testing.m-ds.de',
        'api_key': '<key>',
    }
    """
    INVOICE_BACKEND_AUTH_DATA = {}
    
    # list of dicts of additional invoice backends for extra invoice generation
    # should only be defined in .env
    ADDITIONAL_INVOICES_BACKENDS = []
    """
        Example:
        ADDITIONAL_INVOICES_BACKENDS = [{
            'backend': 'wechange_payments.backends.invoice.tryton.TrytonInvoiceBackend',
            'auth_data' {
                'api_domain': 'https://wchg-testing.m-ds.de',
                'api_key': '<key>',
                'db_name': 'wchgtesting',
            }
        }]
    """
    
    # if set, will add a "portalID" attribute to the invoice creation payload, to identify the portal
    # that the invoice came from. e.g. setting 'INVOICE_PORTAL_ID = "WE' would result in the attribute
    # {'Portal-ID': 'WE-0000003'} (for user-id 3)
    INVOICE_PORTAL_ID = None
    

class NonPrefixDefaultSettings(AppConf):
    """ Settings without a prefix namespace to provide default setting values for other apps.
        These are settings used by default in cosinnus apps, such as avatar dimensions, etc.
    """
    
    class Meta(object):
        prefix = ''
        
    # django_countries settings
    COUNTRIES_FIRST = ['de', 'at', 'ch']
    COUNTRIES_FIRST_REPEAT = True


""" 
    Note: You should configure Raven/Sentry to scrub sensitive POSTs, 
    since logs inside POST requests to betterpayments may contain the
    `bic` and `iban` keys, containing account information!
    
    Do this by either by using sanitized keys with its processor:
    
    ```
    RAVEN_CONFIG = {
        'dsn': 'https://c8ed0743c9b74e70a3e3bfb4f1ac015d:357b15febba84855af12b1077067f899@sentry.sinntern.de/4',
        'sanitize_keys': [
            'iban',
            'bic',
        ],
        'processors': (
            'raven.processors.SanitizeKeysProcessor',
            'raven.processors.SanitizePasswordsProcessor',
        )
    }
    ```
    
    or by using the complete `raven.processors.RemovePostDataProcessor`.
    
"""

