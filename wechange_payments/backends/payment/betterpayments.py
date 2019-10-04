# -*- coding: utf-8 -*-
from wechange_payments.backends.payment.base import BaseBackend
from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT,\
    PAYMENT_TYPE_CREDIT_CARD, REDIRECTING_PAYMENT_TYPES, PAYMENT_TYPE_PAYPAL
import urllib
import hashlib
from wechange_payments.models import TransactionLog, Payment

import logging
import requests
import six
import uuid
from django.urls.base import reverse
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from cosinnus.models.group import CosinnusPortal
from annoying.functions import get_object_or_None
from django.utils.timezone import now
from django.contrib import messages
from copy import copy
from wechange_payments.payment import create_subscription_for_payment
from wechange_payments import signals

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

def _strip_sensitive_data(params):
    """ Strips out sensitive data from a data dict that should not be saved in our DB """
    params = copy(params)
    for sensitive_key in BETTERPAYMENT_SENSITIVE_POSTBACK_PARAMS:
        if sensitive_key in params:
            del params[sensitive_key]
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
    
    
    EMAIL_TEMPLATES_STATUS_MAP = {
        BETTERPAYMENT_STATUS_SUCCESS: BaseBackend.EMAIL_TEMPLATES_SUCCESS,
        BETTERPAYMENT_STATUS_ERROR: BaseBackend.EMAIL_TEMPLATES_ERROR,
        BETTERPAYMENT_STATUS_DECLINED: BaseBackend.EMAIL_TEMPLATES_ERROR,
    }
    
    
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
            return 'Error: %s" (%d)' % (result.get('error_message'), result.get('error_code'))
        
        if result.get('error_code') == 0 and not transaction_id or not sepa_mandate_token:
            extra= {'post_url': post_url, 'data': _strip_sensitive_data(data), 'result': result}
            logger.error('Payments: API Error while calling SEPA Mandate Creation, missing transaction id or sepa mandate token!', extra=extra)
            return 'Error: Payment provider did not supply expected data.' 
        
        return (transaction_id, sepa_mandate_token)
    
    
    def _make_actual_payment(self, payment_type, order_id, request, params, user=None, original_transaction_id=None):
        """ /rest/payment
        
            api_key:668651eb6e943eb3dc14
            payment_type:dd  //https://dashboard.betterpayment.de/docs/?shell#payment-type
            order_id:autogen_from_us_1
            customer_id:our_user_id_1
            //postback_url:our_postback_url
            original_transaction_id:597d3a4f-7955-44ad-bdd3-f16d101ba843 <from the mandate-creation!>
            checksum:<generate this>
            
            amount:1.337
            address:Straße
            city:Berlin
            postal_code:11111
            country:DE // ISO 3166-1
            first_name:Hans
            last_name:Mueller
            email:saschanarr@gmail.com
            iban:de29742940937493240340
            bic:BELADEBEXXX
            account_holder:Hans Mueller
        """
        post_url = settings.PAYMENTS_BETTERPAYMENT_API_DOMAIN + BETTERPAYMENTS_API_ENDPOINT_PAYMENT
        
        data = {
            'api_key': settings.PAYMENTS_BETTERPAYMENT_API_KEY,
            'payment_type': payment_type,
            'order_id': order_id,
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
        if payment_type == PAYMENT_TYPE_DIRECT_DEBIT:
            data.update({
                'iban': params['iban'],
                'bic': params['bic'],
                'account_holder': params['account_holder'],
            })
        if original_transaction_id:
            data.update({
                'original_transaction_id': original_transaction_id,
            })
        if payment_type in REDIRECTING_PAYMENT_TYPES:
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
            return (None, 'Error: The payment provider could not be reached.')
    
        result = req.json() # success!
        result['payment_type'] = payment_type
        TransactionLog.objects.create(
            type=TransactionLog.TYPE_REQUEST,
            url=post_url,
            data=result
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
            return (None, 'Error: %s (%d)' % (_('Unexpected response from payment provider.'), -1))
        
        if result.get('error_code') != 0:
            # ignore some errors for sentry warnings (126: invalid account info)
            if result.get('error_code') not in [126,]: 
                extra= {'post_url': post_url, 'data': _strip_sensitive_data(data), 'result': result}
                logger.warn('Payments: API Calling SEPA Payment returned an error!', extra=extra)
            return (None, 'Error: %s (%d)' % (result.get('error_message'), result.get('error_code')))
        
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
        if payment_type == PAYMENT_TYPE_DIRECT_DEBIT:
            obfuscated_iban = params['iban'][:2] + ('*' * (len(params['iban'])-6)) + params['iban'][-4:]
            extra_data.update({
                'iban': obfuscated_iban,
                'account_holder': params['account_holder'],
            })

        # save successful payment
        payment = Payment(
            user=user,
            vendor_transaction_id=result.get('transaction_id'),
            internal_transaction_id=result.get('order_id'),
            amount=float(params['amount']),
            type=Payment.TYPE_MAP.get(payment_type),
            status=Payment.STATUS_STARTED,
            
            address=params['address'],
            city=params['city'],
            postal_code=params['postal_code'],
            country=params['country'],
            first_name=params['first_name'],
            last_name=params['last_name'],
            email=params['email'],
            
            backend='%s.%s' %(self.__class__.__module__, self.__class__.__name__),
            extra_data=extra_data,
        )
        return (payment, None)
    
    def make_sepa_payment(self, request, params, user=None):
        """
            Make a SEPA payment. A mandate is created here, which has to be displayed
            to the user. Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can be null.
            @param params: Expected params are:
                
            @return: str error message or model of wechange_payments.models.BasePayment if successful
         """
        order_id = str(uuid.uuid4())
        mandate_result = self._create_sepa_mandate(order_id)
        if isinstance(mandate_result, six.string_types):
            # contains error message, return
            return None, mandate_result
        transaction_id, sepa_mandate_token = mandate_result
        
        payment, error = self._make_actual_payment(PAYMENT_TYPE_DIRECT_DEBIT, order_id, request, params, user=user, original_transaction_id=transaction_id)
        if error is not None:
            return None, error
        
        payment.extra_data.update({
            'sepa_mandate_token': sepa_mandate_token 
        })
        try:
            if settings.PAYMENTS_SEPA_IS_INSTANTLY_SUCCESSFUL:
                payment.status = Payment.STATUS_PAID
                payment.completed_at = now()
            else:
                payment.status = Payment.STATUS_COMPLETED_BUT_UNCONFIRMED
            payment.save()
        except Exception as e:
            logger.warning('Payments: SEPA Payment successful, but Payment object could not be saved!', extra={'internal_transaction_id': payment.internal_transaction_id,  order_id: 'order_id', 'exception': e})
            
        if settings.PAYMENTS_SEPA_IS_INSTANTLY_SUCCESSFUL:
            signals.successful_payment_made.send(sender=self, payment=payment)
            self.send_payment_status_payment_email(payment.email, payment, PAYMENT_TYPE_DIRECT_DEBIT)
            
        return payment, None
    
    def make_creditcard_payment(self, request, params, user=None):
        """ Initiate a credit card payment. """
        return self._make_redirected_payment(request, params, PAYMENT_TYPE_CREDIT_CARD, user=user)
    
    def make_paypal_payment(self, request, params, user=None):
        """ Initiate a paypal payment. """
        return self._make_redirected_payment(request, params, PAYMENT_TYPE_PAYPAL, user=user)
        
    def _make_redirected_payment(self, request, params, payment_type, user=None):
        """ 
            Initiate a payment where the user gets redirected to an external site for
            a part of the payment process.
            Return expects an error message or an object of base model
            `wechange_payments.models.BasePayment` if successful.
            Note: Never save any payment information in our DB!
            
            @param user: The user for which this payment should be made. Can be null.
            @param params: Expected params are:
                
            @return: str error message or model of wechange_payments.models.BasePayment if successful
        """
        order_id = str(uuid.uuid4())
        payment, error = self._make_actual_payment(payment_type, order_id, request, params, user=user)
        if error is not None:
            return None, error
        try:
            payment.save()
        except Exception as e:
            logger.warning('Payments: Payment object could not be saved for a transaction of type "%s"!' % payment_type, extra={'internal_transaction_id': payment.internal_transaction_id, 'order_id': order_id, 'exception': e})
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
        """ Does Checksum validation and if valid saves the postback data as TransactionLog """
        if self._validate_incoming_checksum(params, 'postback'):
            params = _strip_sensitive_data(params)
            try:
                # drop sensitive data from postback
                TransactionLog.objects.create(
                    type=TransactionLog.TYPE_POSTBACK,
                    data=params,
                )
            except Exception as e:
                logger.error('Payments: Error during postback processing! Postbacked data could not be saved!', extra={'params': params, 'exception': e})
            
            try:
                missing_params = [param for param in ['transaction_id', 'order_id', 'status_code'] if param not in params]
                if missing_params:
                    logger.error('BetterPayments Postback: Missing parameters: [%s]. Could not handle postback!' % ', '.join(missing_params), extra={'params': params})
                    return
                
                # find referenced payment
                payment = get_object_or_None(Payment, 
                    vendor_transaction_id=params['transaction_id'],
                    internal_transaction_id=params['order_id']
                )
                if payment is None:
                    logger.error('BetterPayments Postback: Could not match a Payment object for given Postback!', extra={'params': params})
                    return
                
                # Transaction Statuses see https://testdashboard.betterpayment.de/docs/#transaction-statuses
                status = int(params['status_code'])
                if status in [self.BETTERPAYMENT_STATUS_STARTED, self.BETTERPAYMENT_STATUS_PENDING]:
                    # case 'started', 'pending': no further action required, we are waiting for the transaction to complete
                    return
                elif status == self.BETTERPAYMENT_STATUS_SUCCESS:
                    # case 'succcess': the payment was successful, update the Payment and start a subscription
                    payment.status = Payment.STATUS_PAID
                    payment.completed_at = now()
                    payment.save()
                    signals.successful_payment_made.send(sender=self, payment=payment)
                    # IMPORTANT: if this is a recurring payment for a running subscription, don't start a subscription!
                    if payment.is_reference_payment:
                        create_subscription_for_payment(payment)
                    self.send_payment_status_payment_email(payment.email, payment, PAYMENT_TYPE_DIRECT_DEBIT)
                elif status == self.BETTERPAYMENT_STATUS_CANCELED:
                    # case 'error', 'canceled', 'declined': mark the payment as canceled. no further action is required.
                    payment.status = Payment.STATUS_CANCELED
                    payment.save()
                elif status in [self.BETTERPAYMENT_STATUS_ERROR, self.BETTERPAYMENT_STATUS_DECLINED]:
                    # case 'error', 'declined': mark the payment as failed
                    payment.status = Payment.STATUS_FAILED
                    payment.save()
                    self.send_payment_status_payment_email(payment.email, payment, PAYMENT_TYPE_DIRECT_DEBIT)
                elif status in [self.BETTERPAYMENT_STATUS_REFUNDED, self.BETTERPAYMENT_STATUS_CHARGEBACK]:
                    # TODO: add refund logic, cancel subscription probably?
                    logger.error('NYI: Received a postback for a refund, but refunding logic not yet implemented!', extra={'betterpayment_status_code': status, 'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id})
                else:
                    # we do not know what to do with this status
                    logger.error('NYI: Received postback with a status we cannot handle (Status: %d)!' % status, extra={'betterpayment_status_code': status, 'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id})
            except Exception as e:
                logger.error('Payments: Error during postback processing! Postbacked data was saved, but payment status could not be updated!', extra={'params': params, 'exception': e})
            
        return
    
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
        