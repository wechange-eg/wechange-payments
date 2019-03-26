# -*- coding: utf-8 -*-
from wechange_payments.backends.base import BaseBackend
from wechange_payments.conf import settings
import urllib
import hashlib


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
