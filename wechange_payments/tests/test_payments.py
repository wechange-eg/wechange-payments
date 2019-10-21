# -*- coding: utf-8 -*-
from django.test.testcases import TestCase, SimpleTestCase
from wechange_payments.backends import get_backend
from django.contrib.auth import get_user_model

import logging
from django.test import Client
from wechange_payments.tests.example_data import TEST_DATA_SEPA_PAYMENT_FORM
from django.urls.base import reverse
from annoying.functions import get_object_or_None
from wechange_payments.models import Payment, Subscription
from wechange_payments.conf import PAYMENT_TYPE_DIRECT_DEBIT

logger = logging.getLogger('wechange-payments')


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


class PaymentsUnitTest(TestCase):
    
    @classmethod
    def setUpTestData(cls):
        user1 = get_user_model().objects.create(
            username='user1',
            email='user1@mail.com',
            first_name='User1',
            is_active=True,
        )
    
    def setUp(self):
        """ Sets up a regular user and lots them in """
        self.user1 = get_user_model().objects.get(username='user1')
        self.client = Client()
        self.client.force_login(self.user1)
    
    def test_1_sepa_payment(self):
        data = TEST_DATA_SEPA_PAYMENT_FORM
        response = self.client.post(reverse('wechange-payments:api-make-subscription-payment'), data)
        self.assertEqual(response.status_code, 200, 'Payment response redirects?')
        
        subscription = get_object_or_None(Subscription, user=self.user1)
        payment = get_object_or_None(Payment, user=self.user1)
        self.assertIsNotNone(subscription, 'Subscription created after payment?')
        self.assertIsNotNone(payment, 'Payment created afert payment?')
        self.assertEqual(response.json()['redirect_to'], reverse('wechange-payments:payment-success', kwargs={'pk': payment.pk}), 'Redirected to correct success page?')
        self.assertEqual(subscription.state, Subscription.STATE_2_ACTIVE, 'Subscription is active?')
        self.assertEqual(payment.type, PAYMENT_TYPE_DIRECT_DEBIT, 'Payment type correct?')
        self.assertEqual(payment.status, Payment.STATUS_PAID, 'Payment status is paid?')
        self.assertEqual(subscription.amount, data['amount'], 'Subscription amount correct?')
        self.assertEqual(payment.amount, data['amount'], 'Payment amount correct?')
        self.assertEqual(payment.subscription, subscription, 'Payment references subscription?')
        self.assertEqual(subscription.reference_payment, payment, 'Subscription references payment?')
        self.assertEqual(subscription.last_payment, payment, 'Subscription references payment as most recent?')
        
        # check next_due_date for subscription and more
        
class AnyonmousUserPaymentsAccessTest(TestCase):
    """ Tests that the most important payment functions cannot be accessed by anonymous users. """
    pass
        
        