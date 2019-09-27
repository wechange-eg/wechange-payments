# -*- coding: utf-8 -*-

from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT,\
    PAYMENT_TYPE_PAYPAL, PAYMENT_TYPE_CREDIT_CARD
from django.core.exceptions import ImproperlyConfigured
from wechange_payments.models import Payment
from wechange_payments.utils.utils import resolve_class
from django.template.loader import render_to_string
from wechange_payments import signals


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
            'email', # saschanarr@gmail.com
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
            'email', # saschanarr@gmail.com
        ],
        PAYMENT_TYPE_PAYPAL: [
            'amount', # 1.337
            'address', # Straße
            'city', # Berlin
            'postal_code', # 11111
            'country', # DE // ISO 3166-1 code
            'first_name', # Hans
            'last_name', # Mueller
            'email', # saschanarr@gmail.com
        ],
    }
    
    # if one is given for a payment type, an email will be sent out
    # after a successful payment
    EMAIL_TEMPLATES = {
        PAYMENT_TYPE_DIRECT_DEBIT: (
            'wechange_payments/mail/sepa_payment_success.html',
            'wechange_payments/mail/sepa_payment_success_subj.txt'
        ),
    }
    
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
    
    def send_successful_payment_email(self, email, payment, payment_type):
        template, subject_template = self.EMAIL_TEMPLATES.get(payment_type, (None, None))
        if template and subject_template:
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
    
    def make_sepa_payment(self, request, params, user=None):
        """
            Make a SEPA payment. A mandate is created here, which has to be displayed
            to the user. Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`
                
            @return: tuple (
                        model of wechange_payments.models.BasePayment if successful or None,
                        str error message if error or None
                    )
         """
        raise NotImplemented('Use a proper payment provider backend for this function!')
    
    def make_creditcard_payment(self, request, params, user=None):
        """
            Initiate a credit card payment. 
            Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`
                
            @return: tuple (
                        model of wechange_payments.models.BasePayment if successful or None,
                        str error message if error or None
                    )
         """
        raise NotImplemented('Use a proper payment provider backend for this function!')
    
    def make_paypal_payment(self, request, params, user=None):
        """
            Initiate a paypal payment.  
            Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`
                
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
    
    def make_sepa_payment(self, request, params, user=None):
        return (
            Payment(
                user=user,
                amount=1.337,
                extra_data={'sepa_mandate_token': 'sepa-token-111111111'}
            ), 
            None
        )
