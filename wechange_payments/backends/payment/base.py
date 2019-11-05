# -*- coding: utf-8 -*-

from datetime import timedelta
import logging

from django.core.exceptions import ImproperlyConfigured
from django.db.models import Sum
from django.template.loader import render_to_string
from django.utils.timezone import now

from wechange_payments import signals
from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT, \
    PAYMENT_TYPE_PAYPAL, PAYMENT_TYPE_CREDIT_CARD
from wechange_payments.models import Payment
from wechange_payments.utils.utils import resolve_class


logger = logging.getLogger('wechange-payments')

class BaseBackend(object):
    """  """
    # define this in the implementing backend
    required_setting_keys = []
    
    # params for each payment type
    REQUIRED_PARAMS = {
        PAYMENT_TYPE_DIRECT_DEBIT: [
            'amount', # 1.337
            'address', # Straße
            'city', # Berlin
            'postal_code', # 11111
            'country', # DE // ISO 3166-1 code
            'first_name', # Hans
            'last_name', # Mueller
            'email', # test@mail.com
            'iban', # de29742940937493240340
            'bic', # BELADEBEXXX
            'account_holder', # Hans Mueller
        ],
        PAYMENT_TYPE_CREDIT_CARD: [
            'amount', # 1.337
            'address', # Straße
            'city', # Berlin
            'postal_code', # 11111
            'country', # DE // ISO 3166-1 code
            'first_name', # Hans
            'last_name', # Mueller
            'email', # test@mail.com
        ],
        PAYMENT_TYPE_PAYPAL: [
            'amount', # 1.337
            'address', # Straße
            'city', # Berlin
            'postal_code', # 11111
            'country', # DE // ISO 3166-1 code
            'first_name', # Hans
            'last_name', # Mueller
            'email', # test@mail.com
        ],
    }
    
    # email templates depending on payment statuses and types, see `EMAIL_TEMPLATES_STATUS_MAP`
    EMAIL_TEMPLATES_SUCCESS = {
        PAYMENT_TYPE_DIRECT_DEBIT: (
            'wechange_payments/mail/sepa_payment_success.html',
            'wechange_payments/mail/sepa_payment_success_subj.txt'
        ),
        PAYMENT_TYPE_CREDIT_CARD: (
            'wechange_payments/mail/sepa_payment_success.html',
            'wechange_payments/mail/sepa_payment_success_subj.txt'
        ),
        PAYMENT_TYPE_PAYPAL: (
            'wechange_payments/mail/sepa_payment_success.html',
            'wechange_payments/mail/sepa_payment_success_subj.txt'
        ),  
    }
    EMAIL_TEMPLATES_ERROR = {
        PAYMENT_TYPE_DIRECT_DEBIT: (
            'wechange_payments/mail/sepa_payment_success.html',
            'wechange_payments/mail/sepa_payment_success_subj.txt'
        ),
        PAYMENT_TYPE_CREDIT_CARD: (
            'wechange_payments/mail/sepa_payment_success.html',
            'wechange_payments/mail/sepa_payment_success_subj.txt'
        ),
        PAYMENT_TYPE_PAYPAL: (
            'wechange_payments/mail/sepa_payment_success.html',
            'wechange_payments/mail/sepa_payment_success_subj.txt'
        ),  
    }
    
    # implement this in the payment backend, matching payment statuses to 
    # template types in `EMAIL_TEMPLATES`
    EMAIL_TEMPLATES_STATUS_MAP = {}
    
    
    def __init__(self):
        for key in self.required_setting_keys:
            if not getattr(settings, key, None):
                raise ImproperlyConfigured('Setting "%s" is required for backend "%s"!' 
                            % (key, self.__class__.__name__))
    
    def check_missing_params(self, params, payment_type):
        """ Checks if any of the required parameters are missing in
            a given set of parameters. Use the parameter lists like 
            `REQUIRED_PARAMS_SEPA` for this. """
        missing_params = []
        for param in self.REQUIRED_PARAMS[payment_type]:
            if not params.get(param, None):
                missing_params.append(param)
        return missing_params
    
    def user_pre_payment_safety_checks(self, user):
        """ Executes a series of hardcoded safety checks to verify that the a payment
            may be executed for a user. Meant as a second independent check to make 
            sure that no irregularly frequent or too-high amounts will be processed
            from a user.
            This function *must* be called before making any actual payments!
            
            @return: True if a payment may be made, False otherwise 
            """
        # --------- Pre-Payment Safety checks ----------
        # 0. Currently not accepting user-less payments
        if not user:
            logger.warn('Payments: user_pre_payment_safety_checks was prevented because a userless payment was attempted.')
            return False
        # 1. User is active
        if not user.is_active:
            logger.warn('Payments: user_pre_payment_safety_checks was prevented for an inactive user.', 
                extra={'user': user})
            return False
        
        # skip this safety measure for test servers
        if getattr(settings, 'COSINNUS_PAYMENTS_TEST_PHASE', False):
            return True
        
        # 2. No existing successful payment in the last 14 days
        seven_days = now() - timedelta(days=14)
        paid_payments = Payment.objects.filter(user=user, status=Payment.STATUS_PAID, completed_at__gt=seven_days)
        if paid_payments.count() > 0:
            logger.critical('Payments: NEED TO INVESTIGATE! `user_pre_payment_safety_checks` was prevented because of an existing successful Payment for this user in the last 7 days!', 
                extra={'user': user})
            return False
        # 3. No payments for this user over the hardcapped payment amount in the last 27 days
        twenty_eight_days = now() - timedelta(days=27)
        paid_payments_month = Payment.objects.filter(user=user, status=Payment.STATUS_PAID, completed_at__gt=twenty_eight_days)
        payment_sum = paid_payments_month.aggregate(Sum('amount')).get('amount__sum', 0.00)
        if payment_sum > settings.PAYMENTS_MAXIMUM_ALLOWED_PAYMENT_AMOUNT:
            logger.critical('Payments: NEED TO INVESTIGATE! `user_pre_payment_safety_checks` was prevented because the sum of Payment amounts for this user in the last 28 days exceeds the maximum hardcap payment amount!', 
                extra={'user': user, 'payment_sum': payment_sum})
            return False
        return True
    
    def send_payment_status_payment_email(self, email, payment, payment_type):
        """ Sends a success/error email out to the user, depending on the status of the given payment. """
        try:
            email_template_map = self.EMAIL_TEMPLATES_STATUS_MAP.get(payment.status, {})
            if not email_template_map:
                logger.warning('Could not find email templates for payment status "%s"' % str(payment.status), extra={'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id})
            template, subject_template = email_template_map.get(payment_type, (None, None)) 
            if not template or not subject_template:
                logger.warning('Could not find a payment email template for payment type "%s"' % str(payment.status), extra={'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id})
            
            mail_func = resolve_class(settings.PAYMENTS_SEND_MAIL_FUNCTION)
            data = {
                'payment': payment,
            }
            if settings.PAYMENTS_USE_HOOK_INSTEAD_OF_SEND_MAIL == True:
                signals.success_email_sender.send(sender=self, to_email=email, template=template, subject_template=subject_template, data=data)
            else:
                subject = render_to_string(subject_template, data)
                message = render_to_string(template, data)
                mail_func(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
        except Exception as e:
            logger.warning('Payments: Sending a payment status email to the user failed!', extra={'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id, 'exception': e})
            if settings.DEBUG:
                raise
        
    def make_sepa_payment(self, params, user=None, make_postponed=False):
        """
            Make a SEPA payment. A mandate is created here, which has to be displayed
            to the user. Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`
            @param make_postponed: If True, makes a pre-authorizes payment that won't not cashed in yet
                
            @return: tuple (
                        model of wechange_payments.models.BasePayment if successful or None,
                        str error message if error or None
                    )
         """
        raise NotImplemented('Use a proper payment provider backend for this function!')
    
    def make_creditcard_payment(self, params, user=None, make_postponed=False):
        """
            Initiate a credit card payment. 
            Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`
            @param make_postponed: If True, makes a pre-authorizes payment that won't not cashed in yet
                
            @return: tuple (
                        model of wechange_payments.models.BasePayment if successful or None,
                        str error message if error or None
                    )
         """
        raise NotImplemented('Use a proper payment provider backend for this function!')
    
    def make_paypal_payment(self, params, user=None, make_postponed=False):
        """
            Initiate a paypal payment.  
            Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`
            @param make_postponed: If True, makes a pre-authorizes payment that won't not cashed in yet
                
            @return: tuple (
                        model of wechange_payments.models.BasePayment if successful or None,
                        str error message if error or None
                    )
         """
        raise NotImplemented('Use a proper payment provider backend for this function!')
    
    def cash_in_postponed_payment(self, postponed_payment):
        """ Cashes in a pre-authorized payment made using `make_postponed=True`, by making an API call
            using a reference to that pre-authorized payment. 
            
            @param postponed_payment: The pre-authorized payment which a cash-in call can be made to.
            @return: tuple (
                        model of wechange_payments.models.BasePayment if successful or None,
                        str error message if error or None
                    )
        """
        raise NotImplemented('Use a proper payment provider backend for this function!')
    
    def make_recurring_payment(self, reference_payment):
        """
            Executes a subsequent payment for a given reference payment. 
            Used for monthly recurring payments. Returns the newly made `Payment` instance. 
            
            @param reference_payment: The initial reference payment which can be referred to to make
                follow-up payments on.
            @return: tuple (
                        model of wechange_payments.models.BasePayment if successful or None,
                        str error message if error or None
                    )
        """
        raise NotImplemented('Use a proper payment provider backend for this function!')
    
    def handle_success_redirect(self, request, params):
        """ Endpoint the user gets redirected to, after a transaction was successful that happened
            in an external website. 
            @return: Return a proper redirect for the user on our site. """
        raise NotImplemented('Use a proper payment provider backend for this function!')
        
    def handle_error_redirect(self, request, params):
        """ Endpoint the user gets redirected to, after a transaction failed that happened
            in an external website. 
            @return: Return a proper redirect for the user on our site. """
        raise NotImplemented('Use a proper payment provider backend for this function!')
        
    def handle_postback(self, request, params):
        """ For a provider backend-only postback to post feedback on a transaction. 
            Always return 200 on this and save the data. """
        raise NotImplemented('Use a proper payment provider backend for this function!')
        

class DummyBackend(BaseBackend):
    """ This Backend will always act like all calls were successful. """
    
    def handle_postback(self, params):
        pass
    
    def make_sepa_payment(self, params, user=None):
        return (
            Payment(
                user=user,
                amount=1.337,
                extra_data={'sepa_mandate_token': 'sepa-token-111111111'}
            ), 
            None
        )
