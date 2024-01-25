# -*- coding: utf-8 -*-
from copy import copy
import hashlib
import logging
import urllib
import uuid

from annoying.functions import get_object_or_None
from django.core.exceptions import PermissionDenied
from django.urls.base import reverse
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
import requests
import six

from cosinnus.models.group import CosinnusPortal
from wechange_payments.backends.payment.base import BaseBackend
from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT, \
    PAYMENT_TYPE_CREDIT_CARD, REDIRECTING_PAYMENT_TYPES, PAYMENT_TYPE_PAYPAL
from wechange_payments.models import TransactionLog, Payment, Subscription
from wechange_payments.payment import suspend_failed_subscription, handle_successful_payment,\
    handle_payment_refunded
import time

logger = logging.getLogger('wechange-payments')

BETTERPAYMENTS_API_ENDPOINT_PAYMENT = '/rest/payment'

# a list of sensitive parameter keys that should be dropped from postback data and not saved in our DB
BETTERPAYMENT_SENSITIVE_POSTBACK_PARAMS = [
    'card_brand',
    'card_last_four',
    'card_expiry_year',
    'card_expiry_month',
    'bic',
    'iban',
    'account_holder'
]

ERROR_MESSAGE_PAYMENT_SECURITY_CHECK_FAILED = _('You cannot make any additional payments at this time. Please contact our support!')

def _strip_sensitive_data(params):
    """ Strips out sensitive data from a data dict that should not be saved in our DB """
    params = copy(params)
    for sensitive_key in BETTERPAYMENT_SENSITIVE_POSTBACK_PARAMS:
        if sensitive_key in params:
            params[sensitive_key] = '***'
    return params


class BetterPaymentBackend(BaseBackend):
    
    required_setting_keys = [
        'PAYMENTS_BETTERPAYMENT_API_KEY',
        'PAYMENTS_BETTERPAYMENT_INCOMING_KEY',
        'PAYMENTS_BETTERPAYMENT_OUTGOING_KEY',
        'PAYMENTS_BETTERPAYMENT_API_DOMAIN',
    ]
    
    # statuses see https://testdashboard.betterpayment.de/docs/#transaction-statuses
    BETTERPAYMENT_STATUS_STARTED = 1
    BETTERPAYMENT_STATUS_PENDING = 2
    BETTERPAYMENT_STATUS_SUCCESS = 3
    BETTERPAYMENT_STATUS_ERROR = 4
    BETTERPAYMENT_STATUS_CANCELED = 5
    BETTERPAYMENT_STATUS_DECLINED = 6
    BETTERPAYMENT_STATUS_REFUNDED = 7
    BETTERPAYMENT_STATUS_CHARGEBACK = 13
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def calculate_request_checksum(self, params, incoming_or_outgoing_key):
        """ Calculate a checksum authentication key for BetterPayments
            as described in https://dashboard.betterpayment.de/docs/?shell#using-payment-gateway.
            Use `PAYMENTS_BETTERPAYMENT_OUTGOING_KEY` for requests sent out to Betterpayments from us,
            and `PAYMENTS_BETTERPAYMENT_INCOMING_KEY` to validate Postback requests made to us from them.
        """
        hash_params = dict([(k, v or '') for k,v in params.items() if not k == 'checksum'])
        query = urllib.parse.urlencode(hash_params) + incoming_or_outgoing_key
        sha1 = hashlib.sha1()
        sha1.update(query.encode('utf-8'))
        return sha1.hexdigest()
    
    def sign_request_params_with_checksum(self, params):
        """ Adds the 'checksum' parameter to a set of params, which is required
            for many BetterPayment requests. """
        params.update({
            'checksum': self.calculate_request_checksum(params, settings.PAYMENTS_BETTERPAYMENT_OUTGOING_KEY)
        })
        return params
    
    def test_status(self):
        testparams = {
          "api_key": "aab1fbbca555e0e70c27",
          "currency": "EUR",
          "merchant_reference": "123",
          "order_id": "123",
          "payment_type": "cc",
          "shipping_costs": "3.50",
          "amount": "17.50"
        }
        outgoing_key = "4d422da6fb8e3bb2749a"
        checksum_test = "9b6b075854fc3473c09700e20e19af3fbc3ff543"
        return 'key: %s, correct is: %s' % (self.calculate_request_checksum(testparams, outgoing_key), checksum_test)
    
    def _create_sepa_mandate(self, order_id):
        """ /rest/create_mandate_reference 
                api_key:668651eb6e943eb3dc14
                payment_type:dd
                order_id:our_order
                
            Save the transaction id and give it to the payment request!
            The token is the mandate token that has to be shown to the user.
            @return: tuple (transaction_id, sepa_mandate_token) or str if there was an error.
            """
        url = '/rest/create_mandate_reference'
        post_url = settings.PAYMENTS_BETTERPAYMENT_API_DOMAIN + url
        data = {
            'api_key': settings.PAYMENTS_BETTERPAYMENT_API_KEY,
            'payment_type': PAYMENT_TYPE_DIRECT_DEBIT,
            'order_id': order_id,
        }
        
        req = requests.post(post_url, data=data)
        if not req.status_code == 200:
            extra = {'post_url': post_url, 'status': req.status_code, 'content': req._content}
            logger.error('Payments: BetterPayment SEPA Mandate creation failed, request did not return status=200.', extra=extra)
            return 'Error: The payment provider could not be reached.'
    
        result = req.json() # success!
        TransactionLog.objects.create(
            type=TransactionLog.TYPE_REQUEST,
            url=post_url,
            data=_strip_sensitive_data(result),
        )
        
        """
            Result on error:
            {
                "error_code": 104,
                "error_message": "Unsupported payment type."
            }
            Result on success:
            {
                "transaction_id": "3cdc6954-ba3d-48e8-be7a-441fe1f7cfe1",
                "token": "204ca0131bfdd1637e75e4b611e685b8",
                "status_code": 9,
                "status": "registered",
                "error_code": 0,
                "order_id": null
            }
        """
            
        transaction_id = result.get('transaction_id', None)
        sepa_mandate_token = result.get('token', None)
        
        assert result.get('error_code', None) is not None
        if result.get('error_code') != 0:
            extra= {'post_url': post_url, 'data': _strip_sensitive_data(data), 'result': result}
            logger.error('Payments: API Calling SEPA Mandate Creation returned an error!', extra=extra)
            return _('Error: "%(error_message)s" (%(error_code)d)') % {'error_message': result.get('error_message'), 'error_code': result.get('error_code')}
        
        if result.get('error_code') == 0 and not transaction_id or not sepa_mandate_token:
            extra= {'post_url': post_url, 'data': _strip_sensitive_data(data), 'result': result}
            logger.error('Payments: API Error while calling SEPA Mandate Creation, missing transaction id or sepa mandate token!', extra=extra)
            return 'Error: Payment provider did not supply expected data.' 
        
        return (transaction_id, sepa_mandate_token)
    
    def make_sepa_payment(self, params, user=None, make_postponed=False):
        """
            Make a SEPA payment. A mandate is created here, which has to be displayed
            to the user. Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can potentially be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`.
            @param make_postponed: If True, makes a pre-authorizes payment that won't not cashed in yet
            @return: A tuple of (`Payment`, None) if successful or (None, Str-error-message)
         """
        order_id = str(uuid.uuid4())
        mandate_result = self._create_sepa_mandate(order_id)
        if isinstance(mandate_result, six.string_types):
            # contains error message, return
            return None, mandate_result
        transaction_id, sepa_mandate_token = mandate_result
        
        payment, error = self._make_actual_payment(PAYMENT_TYPE_DIRECT_DEBIT, order_id, params, user=user, original_transaction_id=transaction_id, make_postponed=make_postponed)
        if error is not None:
            return None, error
        
        payment.extra_data.update({
            'sepa_mandate_token': sepa_mandate_token 
        })
        try:
            if settings.PAYMENTS_SEPA_IS_INSTANTLY_SUCCESSFUL:
                if make_postponed:
                    payment.status = Payment.STATUS_PREAUTHORIZED_UNPAID
                else:
                    payment.status = Payment.STATUS_PAID
                    payment.completed_at = now()
                    logger.info('Payments: Successfully paid and completed an initial SEPA payment (instantly successful without postback)',
                        extra={'user': payment.user.id, 'order_id': payment.internal_transaction_id})
            else:
                payment.status = Payment.STATUS_COMPLETED_BUT_UNCONFIRMED
            payment.save()
        except Exception as e:
            logger.critical('Payments: SEPA Payment successful, but Payment object could not be saved!', extra={'internal_transaction_id': payment.internal_transaction_id,  order_id: 'order_id', 'exception': e, 'payment_data': str(payment.__dict__)})
            
        if settings.PAYMENTS_SEPA_IS_INSTANTLY_SUCCESSFUL:
            handle_successful_payment(payment)
            
        return payment, None
    
    def make_creditcard_payment(self, params, user=None, make_postponed=False):
        """ Initiate a credit card payment. 
            @param user: The user for which this payment should be made. Can potentially be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`.
            @param make_postponed: If True, makes a pre-authorizes payment that won't not cashed in yet
            @return: A tuple of (`Payment`, None) if successful or (None, Str-error-message) """
        return self._make_redirected_payment(params, PAYMENT_TYPE_CREDIT_CARD, user=user, make_postponed=make_postponed)
    
    def make_paypal_payment(self, params, user=None, make_postponed=False):
        """ Initiate a paypal payment. 
            @param user: The user for which this payment should be made. Can potentially be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`.
            @param make_postponed: If True, makes a pre-authorizes payment that won't not cashed in yet
            @return: A tuple of (`Payment`, None) if successful or (None, Str-error-message) """
        return self._make_redirected_payment(params, PAYMENT_TYPE_PAYPAL, user=user, make_postponed=make_postponed)
    
    def make_recurring_payment(self, reference_payment):
        """ Executes a subsequent payment for a given reference payment. 
            Used for monthly recurring payments. Returns the newly made `Payment` instance. 
            @param user: The user for which this payment should be made. Can potentially be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`.
            @return: A tuple of (`Payment`, None) if successful, returning the *new* Payment,
                or (None, Str-error-message) """
        if not self.user_pre_recurring_payment_safety_checks(reference_payment.user):
            return None, _('Error: "%(error_message)s" (%(error_code)d)') % {'error_message': ERROR_MESSAGE_PAYMENT_SECURITY_CHECK_FAILED, 'error_code': -6}
        # additional check: reference payment must be coming from an active subscription!
        if not reference_payment.subscription or not reference_payment.subscription.state == Subscription.STATE_2_ACTIVE:
            return None, _('Error: "%(error_message)s" (%(error_code)d)') % {'error_message': ERROR_MESSAGE_PAYMENT_SECURITY_CHECK_FAILED, 'error_code': -7}
        # additional check: reference payment must be coming from an active subscription that has no pending payments!
        if reference_payment.subscription.has_pending_payment():
            return None, _('Error: "%(error_message)s" (%(error_code)d)') % {'error_message': ERROR_MESSAGE_PAYMENT_SECURITY_CHECK_FAILED, 'error_code': -8}
        
        # collect params from reference payment
        order_id = str(uuid.uuid4())
        params = {
            'amount': reference_payment.subscription.amount, # use amount of subscription, not payment, as subscription amount can be changed!
            'address': reference_payment.address,
            'city': reference_payment.city,
            'postal_code': reference_payment.postal_code,
            'country': str(reference_payment.country),
            'first_name': reference_payment.first_name,
            'last_name': reference_payment.last_name,
            'email': reference_payment.email,    
            'organisation': reference_payment.organisation,
        }
        payment, error = self._make_actual_payment(
            reference_payment.type,
            order_id, 
            params,
            user=reference_payment.user, 
            original_transaction_id=reference_payment.vendor_transaction_id,
            is_recurring=True,
        )
        if error is not None:
            return None, error
        
        # attach subscription from reference payment
        payment.subscription = reference_payment.subscription
        
        if reference_payment.type == PAYMENT_TYPE_DIRECT_DEBIT and settings.PAYMENTS_SEPA_IS_INSTANTLY_SUCCESSFUL:
            payment.status = Payment.STATUS_PAID
            payment.completed_at = now()
            logger.info('Payments: Successfully paid and completed a recurring SEPA payment (instantly successful without postback)',
                extra={'user': payment.user.id, 'order_id': payment.internal_transaction_id})
        else:
            payment.status = Payment.STATUS_COMPLETED_BUT_UNCONFIRMED
            
        try:
            payment.save()
        except Exception as e:
            logger.critical('Payments: Payment object could not be saved for a recurring payment!', extra={'internal_transaction_id': payment.internal_transaction_id, 'order_id': order_id, 'exception': e, 'payment_data': str(payment.__dict__)})
        
        if reference_payment.type == PAYMENT_TYPE_DIRECT_DEBIT and settings.PAYMENTS_SEPA_IS_INSTANTLY_SUCCESSFUL:
            handle_successful_payment(payment)

        return payment, None
    
    def _make_actual_payment(self, payment_type, order_id, params, user=None, original_transaction_id=None, is_recurring=False, make_postponed=False):
        """ Execute the actual payment-making API call to betterpayment.
            At this point, all parameters are assumed to be existent and valid.
            
            Warning: This function does no further risk/safety checks!
            
            Warning: The returned `Payment` instance is *not being saved* in this method!
                It is the responsibility of the calling function to save it!
            
            Note: Never save any payment information in our DB!
            
            @param params: Expected Params can be found in `REQUIRED_PARAMS`.
            @param original_transaction_id: supply the reference payment's vendor transaction id here.
                if not None, means this is a recurring payment made from an existing payment. 
            @param make_postponed: If True, makes a pre-authorizes payment that won't not cashed in yet
            @return: A tuple of (Payment`, None) if successful or (None, Str-error-message)
        """
        if make_postponed and not settings.PAYMENTS_POSTPONED_PAYMENTS_IMPLEMENTED:
            return None, _('Making postponed payments is currently not possible!')
        else:
            post_url = settings.PAYMENTS_BETTERPAYMENT_API_DOMAIN + BETTERPAYMENTS_API_ENDPOINT_PAYMENT
        data = {
            'api_key': settings.PAYMENTS_BETTERPAYMENT_API_KEY,
            'payment_type': payment_type,
            'order_id': order_id,
            'recurring': 1,
            'postback_url': CosinnusPortal.get_current().get_domain() + reverse('wechange-payments:api-postback-endpoint'),
            
            'amount': params['amount'],
            'address': params['address'],
            'city': params['city'],
            'postal_code': params['postal_code'],
            'country': params['country'],
            'first_name': params['first_name'],
            'last_name': params['last_name'],
            'email': params['email'],
        }
        if payment_type == PAYMENT_TYPE_DIRECT_DEBIT and not is_recurring:
            data.update({
                'iban': params['iban'],
                'bic': params['bic'],
                'account_holder': params['account_holder'],
            })
        if original_transaction_id:
            data.update({
                'original_transaction_id': original_transaction_id,
            })
        if payment_type in REDIRECTING_PAYMENT_TYPES and not is_recurring:
            data.update({
                'success_url': CosinnusPortal.get_current().get_domain() + reverse('wechange-payments:api-success-endpoint'), 
                'error_url': CosinnusPortal.get_current().get_domain() + reverse('wechange-payments:api-error-endpoint'),
            })
        if user:
            data.update({
                'customer_id': user.id,
            })
        data = self.sign_request_params_with_checksum(data)
        
        # do request
        req = requests.post(post_url, data=data)
        if not req.status_code == 200:
            extra = {'post_url': post_url, 'status':req.status_code, 'content': req._content}
            logger.error('Payments: BetterPayment Payment of type "%s" failed, request did not return status=200.' % payment_type, extra=extra)
            return (None, _('Error: "%(error_message)s" (%(error_code)d)') % {'error_message': _('The payment provider could not be reached.'), 'error_code': -1})
        
        result = req.json() # success!
        result['payment_type'] = payment_type
        log_data = _strip_sensitive_data(result)
        log_data.update({
            'user': user.id if user else 'None',
            'order_id': order_id,
        })
        TransactionLog.objects.create(
            type=TransactionLog.TYPE_REQUEST,
            url=post_url,
            data=log_data
        )
        
        """
            Result on error:
            {
                "error_code": 104,
                "error_message": "Unsupported payment type."
            }
            Result on success:
            {
              "transaction_id":"5e02903b-0fbf-4266-affd-dc58f2749cd1",
              "order_id":"123000",
              "error_code":0,
              "status_code":1,
              "status":"started",
              # optional for redirecting types:
              "client_action":"redirect",
              "action_data":{  
                "url":"https://www.sofort.com/payment/go/94296bbd19b39b806bc9dc540b9e4a8aa00eae1b"
              }
            }
        """
        # result should always have an error code, which is 0 on success
        if not 'error_code' in result:
            return (None, _('Error: "%(error_message)s" (%(error_code)d)') % {'error_message': _('Unexpected response from payment provider.'), 'error_code': -2})
        
        if result.get('error_code') != 0:
            # in test or admin-only test phase, we print and save out extra info for failed payments to be able to debug them
            if getattr(settings, 'PAYMENTS_TEST_PHASE', False) or getattr(settings, 'COSINNUS_PAYMENTS_ENABLED_ADMIN_ONLY', False):
                special_data = copy(data)
                special_data.update({
                    'TYPE': 'SPECIAL ERROR DEBUG',
                    'order_id': order_id
                })
                TransactionLog.objects.create(
                    type=TransactionLog.TYPE_REQUEST,
                    url=post_url,
                    data=special_data
                )
                
            # ignore some errors for sentry warnings (126: invalid account info)
            if result.get('error_code') not in [126,]: 
                extra= {'post_url': post_url, 'data': _strip_sensitive_data(data), 'result': result}
                logger.warn('Payments: API Calling Payment of type "%s" returned an error!' % payment_type, extra=extra)
            return (None, _('Error: "%(error_message)s" (%(error_code)d)') % {'error_message': result.get('error_message'), 'error_code': result.get('error_code')})
        
        extra_data = {}
        # handle client_action and action_data
        if result.get('client_action', None) == 'redirect' and 'action_data' in result:
            extra_data.update({
                'redirect_to': result.get('action_data').get('url'), 
            })
        
        # save iban with all digits except for the first 2 and last 4 replaced with "*"
        extra_data.update({
            'status': result.get('status'), 
            'status_code': result.get('status_code'),
        })
        if payment_type == PAYMENT_TYPE_DIRECT_DEBIT and not is_recurring:
            obfuscated_iban = params['iban'][:2] + ('*' * (len(params['iban'])-6)) + params['iban'][-4:]
            extra_data.update({
                'iban': obfuscated_iban.upper(),
                'account_holder': params['account_holder'],
            })

        # save successful payment
        payment = Payment(
            user=user,
            vendor_transaction_id=result.get('transaction_id'),
            internal_transaction_id=result.get('order_id'),
            amount=float(params['amount']),
            type=payment_type,
            status=Payment.STATUS_STARTED,
            is_reference_payment=(not is_recurring),
            is_postponed_payment=make_postponed,
            
            address=params['address'],
            city=params['city'],
            postal_code=params['postal_code'],
            country=params['country'],
            first_name=params['first_name'],
            last_name=params['last_name'],
            organisation=params.get('organisation', None),
            email=params['email'],
            
            backend='%s.%s' %(self.__class__.__module__, self.__class__.__name__),
            extra_data=extra_data,
        )
        logger.info('Payments: Successfully completed the first step of %s payment of type "%s"' \
                % ('an initial' if payment.is_reference_payment else 'a recurring', payment_type),
            extra={'user': payment.user.id, 'order_id': payment.internal_transaction_id})
        
        # NOTE: the payment object is *not* being saved here! It is the responsibility of the calling
        # function to save it!
        return (payment, None)
    
    def _make_redirected_payment(self, params, payment_type, user=None, make_postponed=False):
        """ 
            Initiate a payment where the user gets redirected to an external site for
            a part of the payment process.
            Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can potentially be null.
            @param params: Expected params can be found in `REQUIRED_PARAMS`.
            @param make_postponed: If True, makes a pre-authorizes payment that won't not cashed in yet
            @return: A tuple of (`Payment`, None) if successful or (None, Str-error-message)
        """
        order_id = str(uuid.uuid4())
        payment, error = self._make_actual_payment(payment_type, order_id, params, user=user, make_postponed=make_postponed)
        if error is not None:
            return None, error
        try:
            payment.save()
        except Exception as e:
            logger.critical('Payments: Payment object could not be saved for a transaction of type "%s"!' % payment_type, extra={'internal_transaction_id': payment.internal_transaction_id, 'order_id': order_id, 'exception': e, 'payment_data': str(payment.__dict__)})
        return payment, None
            
    def handle_success_redirect(self, request, params):
        """ The user gets navigated here after completing a transaction on a popup/external payment provider.
            @return: The targetted Payment if the redirect was valid and active, False if it was an expired or inactive session. 
        """
        if self._validate_incoming_checksum(params, 'success_redirect'):
            # check for payment with order_id, set the payment to STATUS_COMPLETED_BUT_UNCONFIRMED,
            # and redirect to that payments status page (payment success comes in form of a postback)
            payment = get_object_or_None(Payment, internal_transaction_id=params.get('order_id'))
            if payment and payment.status in [Payment.STATUS_STARTED, Payment.STATUS_COMPLETED_BUT_UNCONFIRMED, Payment.STATUS_PAID]:
                if payment.status == Payment.STATUS_STARTED:
                    payment.status = Payment.STATUS_COMPLETED_BUT_UNCONFIRMED
                    payment.save()
                return payment
            return False
        else:
            raise PermissionDenied('The checksum validation failed.')
        
    def handle_error_redirect(self, request, params):
        """ The user gets navigated here after completing a transaction on a popup/external payment provider.
            @return: True if the redirect was valid and active, False if it was an expired or inactive session. 
        """
        if self._validate_incoming_checksum(params, 'error_redirect'):
            # check for payment with order_id and set the payment to STATUS_FAILED 
            payment = get_object_or_None(Payment, internal_transaction_id=params.get('order_id'))
            if payment and payment.status == Payment.STATUS_STARTED:
                payment.status = Payment.STATUS_FAILED
                payment.save()
                return True
            return False
        else:
            raise PermissionDenied('The checksum validation failed.')
    
    def handle_postback(self, request, params):
        """ Does Checksum validation and if valid saves the postback data as TransactionLogFor a provider backend-only postback to post feedback on a transaction. 
        
            Always save the data, and if it could be handled in a proper way, return a 200.
            Otherwise return a different status.
            @return: True if a 200 should be returned and the data was handled properly,
                        False if a 404 should be returned so the postback will be posted again """
        if self._validate_incoming_checksum(params, 'postback'):
            # drop sensitive data from postback
            params = _strip_sensitive_data(params)
            try:
                TransactionLog.objects.create(
                    type=TransactionLog.TYPE_POSTBACK,
                    data=params,
                )
            except Exception as e:
                logger.error('Payments: Error during postback processing! Postbacked data could not be saved!', 
                             extra={'params': params, 'exception': e})
            
            try:
                missing_params = [param for param in ['transaction_id', 'order_id', 'status_code'] if param not in params]
                if missing_params:
                    logger.error('BetterPayments Postback: Missing parameters: [%s]. Could not handle postback!' % ', '.join(missing_params), extra={'params': params})
                    return False
                
                # find referenced payment
                payment = get_object_or_None(Payment, 
                    vendor_transaction_id=params['transaction_id'],
                    internal_transaction_id=params['order_id']
                )
                
                if payment is None:
                    # sometimes, the returning postback for a transaction is actually faster than
                    # our DB can save the payment! we wait for 5 seconds and retry.
                    time.sleep(10)
                    # find referenced payment again
                    # TODO: why does this often still fail after 10 secs of sleeping?
                    payment = get_object_or_None(Payment, 
                        vendor_transaction_id=params['transaction_id'],
                        internal_transaction_id=params['order_id']
                    )
                    if payment is None:
                        # after waiting and retrying, we give up and error out.
                        # since we return a non-success here, it will be posted again though.
                        logger.error('BetterPayments Postback: Could not match a Payment object for given Postback! The postback was possibly too fast for us to save the payment object.', 
                                     extra={'params': params})
                        return False
                
                # Transaction Statuses see https://testdashboard.betterpayment.de/docs/#transaction-statuses
                status = int(params['status_code'])
                if status in [self.BETTERPAYMENT_STATUS_STARTED, self.BETTERPAYMENT_STATUS_PENDING]:
                    # case 'started', 'pending': no further action required, we are waiting for the transaction to complete
                    return True
                elif status == self.BETTERPAYMENT_STATUS_SUCCESS and payment.status == Payment.STATUS_PAID:
                    # got a postback on an already paid Payment, so we do not do anything
                    logger.info('Payments: Received a postback for a successful payment, but the payment\'s status was already PAID!', 
                                extra={'betterpayment_status_code': status, 'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id})
                    return True
                elif status == self.BETTERPAYMENT_STATUS_SUCCESS:
                    # case 'succcess': the payment was successful, update the Payment and start a subscription
                    # depending on `is_postponed_payment` and the payment.status, switch states here to preauthorized or paid!
                    if settings.PAYMENTS_POSTPONED_PAYMENTS_IMPLEMENTED and payment.is_postponed_payment:
                        # TODO: incomplete logic for postponed payments
                        if payment.status in [Payment.STATUS_STARTED, Payment.STATUS_COMPLETED_BUT_UNCONFIRMED]:
                            payment.status = Payment.STATUS_PREAUTHORIZED_UNPAID
                            # create_new_subscription = True
                            # TODO incomplete: create new subscription here!
                        elif payment.status == Payment.STATUS_PREAUTHORIZED_UNPAID:
                            payment.status = Payment.STATUS_PAID
                            payment.completed_at = now()
                            # we do not change our subscription here because one should already have been created
                            # at the time of pre-authorization for this payment
                        payment.save()
                        # TODO: incomplete!
                    else:
                        # regular success handling 
                        payment.status = Payment.STATUS_PAID
                        payment.completed_at = now()
                        logger.info('Payments: Received a status "paid" postback for a successful payment of type "%s"' % payment.type,
                            extra={'user': payment.user.id, 'order_id': payment.internal_transaction_id})
                        payment.save()
                        handle_successful_payment(payment)
                    return True
                elif status == self.BETTERPAYMENT_STATUS_CANCELED:
                    # case 'error', 'canceled', 'declined': mark the payment as canceled. no further action is required.
                    payment.status = Payment.STATUS_CANCELED
                    payment.save()
                    return True
                elif status in [self.BETTERPAYMENT_STATUS_ERROR, self.BETTERPAYMENT_STATUS_DECLINED]:
                    # case 'error', 'declined': mark the payment as failed
                    payment.status = Payment.STATUS_FAILED
                    payment.save()
                    logger.info('Payments: Received a status "error" or "declined" postback for a payment.',
                        extra={'user': payment.user.id, 'order_id': payment.internal_transaction_id})
                    # if the payment is a recurring one, we take the safe route and suspend the 
                    # subscription. we do NOT want to cause multiple failed booking attempts on a user's account
                    if not payment.is_reference_payment:
                        if payment.subscription:
                            suspend_failed_subscription(payment.subscription, payment=payment)
                        else:
                            logger.critical('Payments: Received a status "error" or "declined" postback for a non-reference payment without attached subscription! The subscription for this payment must be found manually and canceled!',
                                    extra={'user': payment.user.id, 'order_id': payment.internal_transaction_id})
                    elif payment.subscription:
                        # if it was a first payment, set the subscription to state ended
                        # TODO: should we inform the user that the payment failed? 
                        # send_payment_event_payment_email(payment)
                        payment.subscription.state = Subscription.STATE_0_TERMINATED
                        payment.subscription.save()
                    else:
                        logger.info('Payments: Received a status "error" or "declined" postback for a payment without attached subscription, so just cancelling the payment.',
                                    extra={'user': payment.user.id, 'order_id': payment.internal_transaction_id})
                    return True
                elif status in [self.BETTERPAYMENT_STATUS_REFUNDED, self.BETTERPAYMENT_STATUS_CHARGEBACK]:
                    # on a chargeback, immediately suspend the subscription to stop any further transactions. 
                    # we also send out an admin mail, because in this case we have to manually retract a bill
                    # in our accounting system 
                    payment.status = Payment.STATUS_RETRACTED
                    payment.save()
                    handle_payment_refunded(payment, status)
                    return True
                else:
                    # we do not know what to do with this status
                    logger.critical('NYI: Received postback with a status we cannot handle (Status: %d)!' % status, extra={'betterpayment_status_code': status, 'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id})
                    return True
            except Exception as e:
                logger.error('Payments: Error during postback processing! Postbacked data was saved, but payment status could not be updated!', extra={'params': params, 'exception': e})
                return False
        return False
    
    def _validate_incoming_checksum(self, params, endpoint):
        """ Validates an incoming request's checksum to make sure it was not faked.
            
            The following data are appended to the URL, which is used when redirecting back to 
            the shop’s success/error URLs.
                order_id
                transaction_id
                checksum
            It is recommended to verify the authenticity of the data by validating the checksum. 
            This checksum is calculated like with outgoing data, only the incoming key is used this time.
            See https://testdashboard.betterpayment.de/docs/#authentication-and-data-authenticity. """
        valid_checksum = self.calculate_request_checksum(params, settings.PAYMENTS_BETTERPAYMENT_INCOMING_KEY)
        if not 'checksum' in params or not params['checksum'] == valid_checksum:
            params.update({'valid_checksum_should_have_been': valid_checksum})
            logger.warning('Payments: Received an invalid or faked BetterPayments request on "%s". Discarding data.' % endpoint, extra=params)
            return False
        return True
        