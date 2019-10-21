# -*- coding: utf-8 -*-
from django.test.testcases import TestCase, SimpleTestCase
from wechange_payments.backends import get_backend


class BetterPaymentsBackendUnitTest(SimpleTestCase):
    
    required_setting_keys = []
    
    
    def test_checksum(self):
        """
            Tests the checksum signing algorithm with test data from 
            https://dashboard.betterpayment.de/docs/?shell#using-payment-gateway
        """
        backend = get_backend()
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
        
        calculated_checksum = backend.calculate_request_checksum(testparams, outgoing_key)
        self.assertEqual(calculated_checksum, checksum_test)


