# -*- coding: utf-8 -*-
from wechange_payments.backends.base import BaseBackend
from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT
import urllib
import hashlib
from wechange_payments.models import TransactionLog, Payment

import logging
import requests
import six
import uuid
from django.urls.base import reverse

logger = logging.getLogger('wechange-payments')


class BetterPaymentBackend(BaseBackend):
    
    required_setting_keys = [
        'PAYMENTS_BETTERPAYMENT_API_KEY',
        'PAYMENTS_BETTERPAYMENT_INCOMING_KEY',
        'PAYMENTS_BETTERPAYMENT_OUTGOING_KEY',
        'PAYMENTS_BETTERPAYMENT_API_DOMAIN',
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def calculate_request_checksum(self, params, incoming_or_outgoing_key):
        """ Calculate a checksum authentication key for BetterPayments
            as described in https://dashboard.betterpayment.de/docs/?shell#using-payment-gateway.
            Use `PAYMENTS_BETTERPAYMENT_OUTGOING_KEY` for requests sent out to Betterpayments from us,
            and `PAYMENTS_BETTERPAYMENT_INCOMING_KEY` to validate Postback requests made to us from them.
        """
        hash_params = dict([(k, v or '') for k,v in params.items()])
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
            extra = {'post_url': post_url, 'status':req.status_code, 'content': req._content}
            logger.error('Payments: BetterPayment SEPA Mandate creation failed, request did not return status=200.', extra=extra)
            return 'Error: The payment provider could not be reached.'
    
        result = req.json() # success!
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
            extra= {'post_url': post_url, 'data': data, 'result': result}
            logger.error('Payments: API Calling SEPA Mandate Creation returned an error!', extra=extra)
            return 'Error: %s" (%d)' % (result.get('error_message'), result.get('error_code'))
        
        if result.get('error_code') == 0 and not transaction_id or not sepa_mandate_token:
            extra= {'post_url': post_url, 'data': data, 'result': result}
            logger.error('Payments: API Error while calling SEPA Mandate Creation, missing transaction id or sepa mandate token!', extra=extra)
            return 'Error: Payment provider did not supply expected data.' 
        
        return (transaction_id, sepa_mandate_token)
    
    
    def _make_actual_sepa_payment(self, order_id, original_transaction_id, request, params, user=None):
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
        url = '/rest/payment'
        post_url = settings.PAYMENTS_BETTERPAYMENT_API_DOMAIN + url
        data = {
            'api_key': settings.PAYMENTS_BETTERPAYMENT_API_KEY,
            'payment_type': PAYMENT_TYPE_DIRECT_DEBIT,
            'order_id': order_id,
            'original_transaction_id': original_transaction_id,
            'postback_url': request.build_absolute_uri(reverse('wechange-payments:api-postback-endpoint')),
            
            'amount': params['amount'],
            'address': params['address'],
            'city': params['city'],
            'postal_code': params['postal_code'],
            'country': params['country'],
            'first_name': params['first_name'],
            'last_name': params['last_name'],
            'email': params['email'],
            'iban': params['iban'],
            'bic': params['bic'],
            'account_holder': params['account_holder'],
        }
        if user:
            data.update({
                'customer_id': user.id,
            })
        data = self.sign_request_params_with_checksum(data)
        
        # do request
        req = requests.post(post_url, data=data)
        if not req.status_code == 200:
            extra = {'post_url': post_url, 'status':req.status_code, 'content': req._content}
            logger.error('Payments: BetterPayment SEPA Payment failed, request did not return status=200.', extra=extra)
            return (None, 'Error: The payment provider could not be reached.')
    
        result = req.json() # success!
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
              "client_action":"redirect",
              "action_data": {"url":"https://some-target-url"}
            }
        """

        assert result.get('error_code', None) is not None
        if result.get('error_code') != 0:
            extra= {'post_url': post_url, 'data': data, 'result': result}
            logger.error('Payments: API Calling SEPA Payment returned an error!', extra=extra)
            return (None, 'Error: %s (%d)' % (result.get('error_message'), result.get('error_code')))
        
        # TODO: handle client_action and action_data
        
        # save iban with all digits except for the first 2 and last 4 replaced with "*"
        obfuscated_iban = params['iban'][:2] + ('*' * (len(params['iban'])-6)) + params['iban'][-4:]
        extra_data = {
            'status': result.get('status'), 
            'status_code': result.get('status_code'),
            
            'iban': obfuscated_iban,
            'account_holder': params['account_holder'],
        }
        if result.get('client_action', None) == 'redirect' and 'action_data' in result:
            extra_data.update({
                'redirect_to': result.get('action_data'), 
            })

        # save successful payment
        payment = Payment(
                user=user,
                vendor_transaction_id=result.get('transaction_id'),
                internal_transaction_id=result.get('order_id'),
                amount=float(params['amount']),
                type=Payment.TYPE_SEPA,
                
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
            return mandate_result
        transaction_id, sepa_mandate_token = mandate_result
        
        payment, error = self._make_actual_sepa_payment(order_id, transaction_id, request, params, user=user)
        if error is not None:
            return None, error
        
        payment.user = user
        payment.extra_data.update({
            'sepa_mandate_token': sepa_mandate_token 
        })
        try:
            payment.save()
        except Exception as e:
            logger.warning('Payments: SEPA Payment successful, but Payment object could not be saved!', extra={'internal_transaction_id': payment.internal_transaction_id, 'exception': e})
            
        try:
            self.send_successful_payment_email(payment.email, payment, PAYMENT_TYPE_DIRECT_DEBIT)
        except Exception as e:
            logger.warning('Payments: SEPA Payment successful, but sending the success email to the user failed!', extra={'internal_transaction_id': payment.internal_transaction_id, 'exception': e})
            if settings.DEBUG:
                raise
        return payment, None
    
    
    def handle_postback(self, params):
        """ Does Checksum validation and if valid saves the postback data as TransactionLog """
        
        valid_checksum = self.calculate_request_checksum(params, settings.PAYMENTS_BETTERPAYMENT_INCOMING_KEY)
        if not 'checksum' in params or not params['checksum'] == valid_checksum:
            params.update({'valid_checksum_should_have_been': valid_checksum})
            logger.warning('Payments: Received an invalid BetterPayments postback. Discarding data.', extra=params)
            return
            
        TransactionLog.objects.create(
            type=TransactionLog.TYPE_POSTBACK,
            data=params,
        )
        
        
    