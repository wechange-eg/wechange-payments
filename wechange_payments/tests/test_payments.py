# -*- coding: utf-8 -*-
import logging
import unittest

from annoying.functions import get_object_or_None
from dateutil import relativedelta
from django.contrib.auth import get_user_model
from django.test import Client
from django.test.testcases import TestCase, SimpleTestCase
from django.urls.base import reverse

from wechange_payments.backends import get_backend, get_invoice_backend, get_additional_invoice_backends
from wechange_payments.conf import PAYMENT_TYPE_DIRECT_DEBIT
from wechange_payments.conf import settings
from wechange_payments.models import Payment, Subscription, Invoice, AdditionalInvoice, DebitPeriodMixin
from wechange_payments.tests.example_data import TEST_DATA_SEPA_PAYMENT_FORM,\
    TEST_DATA_SEPA_PAYMENT_FORM_AUSTRIA
from django.utils.timezone import now
from wechange_payments.payment import process_due_subscription_payments
from datetime import timedelta, datetime, date
from copy import copy


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
        pass
    
    def _create_user(self, username):
        return get_user_model().objects.create(
            username=username,
            email='%s@mail.com' % username,
            first_name='User %s' % username,
            is_active=True,
        )
    
    def _make_sepa_payment(self, data):
        return self.client.post(reverse('wechange-payments:api-make-subscription-payment'), data)
    
    def setUp(self):
        """ Sets up a regular user and lots them in """
        self.client = Client()
    
    def test_0_1_payment_test_backends_available(self):
        # test betterpayment available
        # TODO
        pass
    
    def test_0_2_invoice_test_backends_available(self):
        # test invoice backend available
        # TODO
        pass
    
    def test_1_full_sepa_payment_and_invoice(self, user_data=TEST_DATA_SEPA_PAYMENT_FORM):
        # create a new user. this user will keep his subscription
        self.loyal_user = self._create_user(username='loyal_user')
        loyal_amount = 7.0
        self.client.force_login(self.loyal_user)
        loyal_data = copy(user_data)
        loyal_data['amount'] = loyal_amount
        response = self._make_sepa_payment(loyal_data)
        self.assertEqual(response.status_code, 200, 'Payment response redirects')

        loyal_subscription = get_object_or_None(Subscription, user=self.loyal_user)
        payment = get_object_or_None(Payment, user=self.loyal_user)
        self.assertIsNotNone(loyal_subscription, 'Subscription created after payment')
        self.assertIsNotNone(payment, 'Payment created afert payment')
        self.assertEqual(response.json()['redirect_to'], reverse('wechange-payments:payment-success', kwargs={'pk': payment.pk}), 'Redirected to correct success page')
        self.assertEqual(loyal_subscription.state, Subscription.STATE_2_ACTIVE, 'Subscription is active')
        self.assertEqual(payment.type, PAYMENT_TYPE_DIRECT_DEBIT, 'Payment type correct')
        self.assertEqual(payment.status, Payment.STATUS_PAID, 'Payment status is paid')
        self.assertEqual(loyal_subscription.amount, loyal_data['amount'], 'Subscription amount correct')
        self.assertEqual(payment.amount, loyal_subscription.amount, 'Payment amount is the same as its subscription')
        self.assertEqual(loyal_subscription.debit_period, loyal_data['debit_period'], 'Payment debit period correct')
        self.assertEqual(payment.debit_period, loyal_subscription.debit_period, 'Payment debit period is the same as its subscription')
        self.assertEqual(payment.subscription, loyal_subscription, 'Payment references subscription')
        self.assertEqual(loyal_subscription.reference_payment, payment, 'Subscription references payment')
        self.assertEqual(loyal_subscription.last_payment, payment, 'Subscription references payment as most recent')
        self.assertGreater(loyal_subscription.get_next_payment_date(), now().date(), 'Subscription due date is in future')
        self.assertFalse(loyal_subscription.check_payment_due(), 'Subscription is not due')
        self.assertEqual(loyal_subscription, Subscription.get_active_for_user(self.loyal_user), 'User has an "active" subscription after payment')
        self.assertEqual(loyal_subscription, Subscription.get_current_for_user(self.loyal_user), 'User has a "current" subscription after payment')
        
        # TODO: test transaction log generation
        logger.warn('TODO: transaction log assertions')
        
        # manually trigger the invoice generation (it wasn't done automatically as hooks are disabled for testing)
        invoice_backend = get_invoice_backend()
        invoice_backend.create_invoice_for_payment(payment, threaded=False)
        invoice = get_object_or_None(Invoice, payment=payment, user=self.loyal_user)
        self.assertIsNotNone(invoice, 'Invoice created after payment')
        self.assertEqual(invoice.state, Invoice.STATE_3_DOWNLOADED, 'Invoice was completed')
        self.assertTrue(invoice.is_ready, 'Invoice ready flag set')
        self.assertIsNotNone(invoice.file, 'Invoice file downloaded and available')
        self.assertEqual(invoice.payment, payment, 'Invoice references payment')
        
        # test additional invoices (additional backend needs to be configured in local settings!)
        for additional_invoice_backend in get_additional_invoice_backends():
            additional_invoice_backend.create_invoice_for_payment(payment, threaded=False, additional_invoice=True)
            additional_invoice = get_object_or_None(AdditionalInvoice, payment=payment, user=self.loyal_user, backend='%s.%s' %(additional_invoice_backend.__class__.__module__, additional_invoice_backend.__class__.__name__))
            self.assertIsNotNone(additional_invoice, 'Invoice created after payment')
            self.assertEqual(additional_invoice.state, Invoice.STATE_3_DOWNLOADED, 'Invoice was completed')
            self.assertTrue(additional_invoice.is_ready, 'Invoice ready flag set')
            self.assertIsNotNone(additional_invoice.file, 'Invoice file downloaded and available')
            self.assertEqual(additional_invoice.payment, payment, 'Invoice references payment')
            print(f'>>> additional invoice tested fine!')
            
        # for a new user, make a payment. this user will make a one-time payment and then cancel his subscription
        self.disloyal_user = self._create_user(username='disloyal_user')
        self.client.force_login(self.disloyal_user)
        disloyal_data = copy(user_data)
        disloyal_amount = 1.0
        disloyal_data['amount'] = disloyal_amount
        response = self._make_sepa_payment(disloyal_data)
        disloyal_subscription = get_object_or_None(Subscription, user=self.disloyal_user)
        self.assertEqual(disloyal_subscription, Subscription.get_active_for_user(self.disloyal_user), 'User has an "active" subscription after payment')
        # cancel the subscription
        response = self.client.post(reverse('wechange-payments:cancel-subscription'))
        # reload subscription from DB
        disloyal_subscription = get_object_or_None(Subscription, user=self.disloyal_user)
        self.assertEqual(disloyal_subscription.state, Subscription.STATE_1_CANCELLED_BUT_ACTIVE, 'Active subscription switched to canceled state after cancellation')
        self.assertIsNone(Subscription.get_active_for_user(self.disloyal_user), 'User with canceled sub has no "active" subscription')
        self.assertEqual(disloyal_subscription, Subscription.get_current_for_user(self.disloyal_user), 'User with canceled sub has a "current" subscription')
        
        # ------ run subscription processing ------
        process_due_subscription_payments()
        
        # reload subscriptions from DB
        loyal_subscription = get_object_or_None(Subscription, user=self.loyal_user)
        disloyal_subscription = get_object_or_None(Subscription, user=self.disloyal_user)
        # no changes in subscription states (because no time has passed and subscriptions weren't due)
        self.assertEqual(loyal_subscription.state, Subscription.STATE_2_ACTIVE, 'Active subscription kept its state after daily subscription processing')
        self.assertEqual(disloyal_subscription.state, Subscription.STATE_1_CANCELLED_BUT_ACTIVE, 'Canceled not-due subscription kept its state after daily subscription processing')
        self.assertEqual(loyal_subscription, Subscription.get_active_for_user(self.loyal_user), 'User has an "active" subscription after subscription processing with not-due subscriptions')
        self.assertEqual(loyal_subscription, Subscription.get_current_for_user(self.loyal_user), 'User has a "current" subscription after subscription processing with not-due subscriptions')
        self.assertIsNone(Subscription.get_active_for_user(self.disloyal_user), 'User with canceled sub has no "active" subscription after subscription processing with not-due subscriptions')
        self.assertEqual(disloyal_subscription, Subscription.get_current_for_user(self.disloyal_user), 'User with canceled sub has a "current" subscription after subscription processing with not-due subscriptions')
        # no changes in payments should have happened
        loyal_payments = Payment.objects.filter(user=self.loyal_user)
        disloyal_payments = Payment.objects.filter(user=self.disloyal_user)
        self.assertEqual(loyal_payments.count(), 1, 'No payments were made after subscription processing with not-due subscriptions')
        self.assertEqual(disloyal_payments.count(), 1, 'No payments were made after subscription processing with not-due subscriptions')
        loyal_payment = loyal_payments[0]
        disloyal_payment = disloyal_payments[0]
        
        # ------ time passes ------
        # fake the subscription and payment datetimes so that they magically happened 32 days ago
        for sub in [loyal_subscription, disloyal_subscription]:
            sub.created = sub.created - timedelta(days=32)
            sub.set_next_due_date(sub.created)
            sub.save()
        for pay in [loyal_payment, disloyal_payment]:
            pay.completed_at = pay.completed_at - timedelta(days=32)
            pay.last_action_at = pay.completed_at
            pay.save()
        # reload subscriptions from DB
        loyal_subscription = get_object_or_None(Subscription, user=self.loyal_user)
        disloyal_subscription = get_object_or_None(Subscription, user=self.disloyal_user)
        # make sure our datetime-faking worked and both subs are due
        self.assertTrue(loyal_subscription.check_payment_due(), '32 days old Subscription is due for payment')
        self.assertFalse(disloyal_subscription.check_payment_due(), '32 days old cancelled Subscription is not due for payment')
        self.assertTrue(disloyal_subscription.check_termination_due(), '32 days old cancelled Subscription is due for termination')
        
        # ------ run subscription processing ------
        time_before_subscription_processing = now()
        process_due_subscription_payments()
        # reload subscriptions from DB
        loyal_subscription = get_object_or_None(Subscription, user=self.loyal_user)
        disloyal_subscription = get_object_or_None(Subscription, user=self.disloyal_user)
        
        # canceled sub should now be terminated, terminated user should not have a subscription
        self.assertEqual(disloyal_subscription.state, Subscription.STATE_0_TERMINATED, 'Canceled due subscription was terminated after daily subscription processing')
        self.assertIsNone(Subscription.get_active_for_user(self.disloyal_user), 'User with terminated sub has no "active" subscription')
        self.assertIsNone(Subscription.get_current_for_user(self.disloyal_user), 'User with terminated sub has no "current" subscription')
        # loyal user sub should still be active, user should have a subscription, due date should be future
        self.assertEqual(loyal_subscription.state, Subscription.STATE_2_ACTIVE, 'Due active subscription kept its state after being renews daily subscription processing')
        self.assertEqual(loyal_subscription, Subscription.get_active_for_user(self.loyal_user), 'User has an "active" subscription after subscription processing with due subscriptions')
        self.assertEqual(loyal_subscription, Subscription.get_current_for_user(self.loyal_user), 'User has a "current" subscription after subscription processing with due subscriptions')
        self.assertGreater(loyal_subscription.next_due_date, time_before_subscription_processing.date(), 'Due active subscription kept its due date in the past after subscription processing')
        
        # loyal user should have a new payment made (a recurrent one), disloyal one should not
        loyal_payments = Payment.objects.filter(user=self.loyal_user).order_by('-last_action_at')
        disloyal_payments = Payment.objects.filter(user=self.disloyal_user).order_by('-last_action_at')
        self.assertEqual(loyal_payments.count(), 2, 'No payments were made after subscription processing with due active subscriptions')
        self.assertEqual(disloyal_payments.count(), 1, 'No payments were made after subscription processing with due canceled subscriptions')
        recurrent_payment = loyal_payments[0]
        
        # the new payment should be just made, paid, not be the reference payment, refer to sub, amount same
        self.assertGreater(recurrent_payment.completed_at, time_before_subscription_processing, 'We identified the monthly recurrent payment correctly for this test')
        self.assertEqual(recurrent_payment.status, Payment.STATUS_PAID, 'The monthly recurrent payment was successfully paid')
        self.assertFalse(recurrent_payment.is_reference_payment, 'The monthly recurrent payment is not the reference payment')
        self.assertEqual(recurrent_payment.subscription, loyal_subscription, 'The monthly recurrent payment references the correct subscription')
        self.assertEqual(recurrent_payment.amount, loyal_amount, 'The amount for the monthly recurrent payment is correct')
        self.assertEqual(recurrent_payment.amount, loyal_subscription.amount, 'The amount for the monthly recurrent payment is the same as for its subscription')
        self.assertEqual(recurrent_payment.debit_period, loyal_subscription.debit_period, 'The debit period for the monthly recurrent payment is the same as for its subscription')

        # manually trigger the invoice generation for the recurred payment (it wasn't done automatically as hooks are disabled for testing)
        invoice_backend = get_invoice_backend()
        invoice_backend.create_invoice_for_payment(recurrent_payment, threaded=False)
        invoice = get_object_or_None(Invoice, payment=recurrent_payment, user=self.loyal_user)
        self.assertIsNotNone(invoice, 'Invoice created after recurrent_payment')
        self.assertEqual(invoice.state, Invoice.STATE_3_DOWNLOADED, 'Invoice was completed')
        self.assertTrue(invoice.is_ready, 'Invoice ready flag set')
        self.assertIsNotNone(invoice.file, 'Invoice file downloaded and available')
        self.assertEqual(invoice.payment, recurrent_payment, 'Invoice references recurrent_payment')
        
        # test additional invoices (additional backend needs to be configured in local settings!)
        for additional_invoice_backend in get_additional_invoice_backends():
            additional_invoice_backend.create_invoice_for_payment(recurrent_payment, threaded=False, additional_invoice=True)
            additional_invoice = get_object_or_None(AdditionalInvoice, payment=recurrent_payment, user=self.loyal_user, backend='%s.%s' % (additional_invoice_backend.__class__.__module__, additional_invoice_backend.__class__.__name__))
            self.assertIsNotNone(additional_invoice, 'Invoice created after recurrent_payment')
            self.assertEqual(additional_invoice.state, Invoice.STATE_3_DOWNLOADED, 'Invoice was completed')
            self.assertTrue(additional_invoice.is_ready, 'Invoice ready flag set')
            self.assertIsNotNone(additional_invoice.file, 'Invoice file downloaded and available')
            self.assertEqual(additional_invoice.payment, recurrent_payment, 'Invoice references recurrent_payment')
            print(f'>>> additional invoice tested fine!')
        
        # a user with an active subscription should not be able to make another one
        self.client.force_login(self.loyal_user)
        logger.warn('TODO: double-concurrent subscription making fail test!')
        
        # even if somehow the subscription date got wrongfully set back in time, 
        # no payment should be able to be made because of safety checks with recently made payments 
        logger.warn('TODO: faked-subscription-date failsafe test that prevents payments')
        
        # TODO: should all these consecutive tests go into a seperate test function?
        # if so, would we really want to re-create the API call all the time, or mock it?
        
    def test_1_b_full_sepa_payment_and_invoice_austria(self):
        return self.test_1_full_sepa_payment_and_invoice(user_data=TEST_DATA_SEPA_PAYMENT_FORM_AUSTRIA)

    def _create_user_and_make_initial_payment(self, amount, debit_period):
        user = self._create_user(username=f'{debit_period}_paying_user')
        self.client.force_login(user)
        post_data = copy(TEST_DATA_SEPA_PAYMENT_FORM)
        post_data['amount'] = amount
        post_data['debit_period'] = debit_period
        response = self._make_sepa_payment(post_data)
        self.assertEqual(response.status_code, 200, 'Payment response redirects')
        return user

    def _turn_back_subscription_due_date(self, n_months, subscriptions):
        for sub in subscriptions:
            sub.created = sub.created - timedelta(days=(32 * n_months))
            sub.set_next_due_date(sub.created.date())
            sub.save()
        for subscription in subscriptions:
            subscription.refresh_from_db()

    def _process_due_subscriptions(self, subscriptions):
        process_due_subscription_payments()
        for subscription in subscriptions:
            subscription.refresh_from_db()

    def test_1_c_full_sepa_payment_and_invoice_debit_periods(self):
        """Test full sepa payment with different debit_period values."""
        monthly_amount = 10.0
        self.monthly_paying_user = self._create_user_and_make_initial_payment(
            monthly_amount, DebitPeriodMixin.DEBIT_PERIOD_MONTHLY
        )
        self.quarterly_paying_user = self._create_user_and_make_initial_payment(
            monthly_amount, DebitPeriodMixin.DEBIT_PERIOD_QUARTER_YEARLY
        )
        self.half_yearly_paying_user = self._create_user_and_make_initial_payment(
            monthly_amount, DebitPeriodMixin.DEBIT_PERIOD_HALF_YEARLY
        )
        self.yearly_paying_user = self._create_user_and_make_initial_payment(
            monthly_amount, DebitPeriodMixin.DEBIT_PERIOD_YEARLY
        )

        # get reference payment and subscription
        monthly_payment = get_object_or_None(Payment, user=self.monthly_paying_user)
        quarterly_payment = get_object_or_None(Payment, user=self.quarterly_paying_user)
        half_yearly_payment = get_object_or_None(Payment, user=self.half_yearly_paying_user)
        yearly_payment = get_object_or_None(Payment, user=self.yearly_paying_user)

        monthly_subscription = get_object_or_None(Subscription, user=self.monthly_paying_user)
        quarterly_subscription = get_object_or_None(Subscription, user=self.quarterly_paying_user)
        half_yearly_subscription = get_object_or_None(Subscription, user=self.half_yearly_paying_user)
        yearly_subscription = get_object_or_None(Subscription, user=self.yearly_paying_user)
        subscriptions =  [monthly_subscription, quarterly_subscription, half_yearly_subscription, yearly_subscription]

        self.assertIsNotNone(monthly_payment)
        self.assertIsNotNone(quarterly_payment)
        self.assertIsNotNone(half_yearly_payment)
        self.assertIsNotNone(yearly_payment)

        self.assertIsNotNone(monthly_subscription)
        self.assertIsNotNone(quarterly_subscription)
        self.assertIsNotNone(half_yearly_subscription)
        self.assertIsNotNone(yearly_subscription)

        # check amount
        self.assertEqual(monthly_payment.amount, monthly_amount)
        self.assertEqual(quarterly_payment.amount, monthly_amount)
        self.assertEqual(half_yearly_payment.amount, monthly_amount)
        self.assertEqual(yearly_payment.amount, monthly_amount)

        self.assertEqual(monthly_subscription.amount, monthly_amount)
        self.assertEqual(quarterly_subscription.amount, monthly_amount)
        self.assertEqual(half_yearly_subscription.amount, monthly_amount)
        self.assertEqual(yearly_subscription.amount, monthly_amount)

        # check debit_period
        self.assertEqual(monthly_payment.debit_period, DebitPeriodMixin.DEBIT_PERIOD_MONTHLY)
        self.assertEqual(quarterly_payment.debit_period, DebitPeriodMixin.DEBIT_PERIOD_QUARTER_YEARLY)
        self.assertEqual(half_yearly_payment.debit_period, DebitPeriodMixin.DEBIT_PERIOD_HALF_YEARLY)
        self.assertEqual(yearly_payment.debit_period, DebitPeriodMixin.DEBIT_PERIOD_YEARLY)

        self.assertEqual(monthly_subscription.debit_period, DebitPeriodMixin.DEBIT_PERIOD_MONTHLY)
        self.assertEqual(quarterly_subscription.debit_period, DebitPeriodMixin.DEBIT_PERIOD_QUARTER_YEARLY)
        self.assertEqual(half_yearly_subscription.debit_period, DebitPeriodMixin.DEBIT_PERIOD_HALF_YEARLY)
        self.assertEqual(yearly_subscription.debit_period, DebitPeriodMixin.DEBIT_PERIOD_YEARLY)

        # check debit_amount
        self.assertEqual(monthly_payment.debit_amount, monthly_amount)
        self.assertEqual(quarterly_payment.debit_amount, monthly_amount * 3)
        self.assertEqual(half_yearly_payment.debit_amount, monthly_amount * 6)
        self.assertEqual(yearly_payment.debit_amount, monthly_amount * 12)

        self.assertEqual(monthly_subscription.debit_amount, monthly_amount)
        self.assertEqual(quarterly_subscription.debit_amount, monthly_amount * 3)
        self.assertEqual(half_yearly_subscription.debit_amount, monthly_amount * 6)
        self.assertEqual(yearly_subscription.debit_amount, monthly_amount * 12)

        # check next due dates
        next_month = date.today() + relativedelta.relativedelta(months=1)
        next_quarter = date.today() + relativedelta.relativedelta(months=3)
        next_half_year = date.today() + relativedelta.relativedelta(months=6)
        next_year = date.today() + relativedelta.relativedelta(months=12)
        self.assertEqual(monthly_subscription.next_due_date, next_month)
        self.assertEqual(quarterly_subscription.next_due_date, next_quarter)
        self.assertEqual(half_yearly_subscription.next_due_date, next_half_year)
        self.assertEqual(yearly_subscription.next_due_date, next_year)

        # test monthly subscription (for completion’s sake)
        self._turn_back_subscription_due_date(1, subscriptions)

        self.assertTrue(monthly_subscription.check_payment_due())
        self.assertFalse(quarterly_subscription.check_payment_due())
        self.assertFalse(half_yearly_subscription.check_payment_due())
        self.assertFalse(yearly_subscription.check_payment_due())

        # process due payments
        self._process_due_subscriptions(subscriptions)

        # check payment was made
        monthly_payments = Payment.objects.filter(user=self.monthly_paying_user).order_by('-last_action_at')
        quarterly_payments = Payment.objects.filter(user=self.quarterly_paying_user).order_by('-last_action_at')
        half_yearly_payments = Payment.objects.filter(user=self.half_yearly_paying_user).order_by('-last_action_at')
        yearly_payments = Payment.objects.filter(user=self.yearly_paying_user).order_by('-last_action_at')

        self.assertEqual(monthly_payments.count(), 2)
        self.assertEqual(quarterly_payments.count(), 1)
        self.assertEqual(half_yearly_payments.count(), 1)
        self.assertEqual(yearly_payments.count(), 1)

        # test quarterly subscription
        self._turn_back_subscription_due_date(3, subscriptions)

        self.assertTrue(monthly_subscription.check_payment_due())
        self.assertTrue(quarterly_subscription.check_payment_due())
        self.assertFalse(half_yearly_subscription.check_payment_due())
        self.assertFalse(yearly_subscription.check_payment_due())

        # process due payments
        self._process_due_subscriptions(subscriptions)

        # check payments were made
        monthly_payments = Payment.objects.filter(user=self.monthly_paying_user).order_by('-last_action_at')
        quarterly_payments = Payment.objects.filter(user=self.quarterly_paying_user).order_by('-last_action_at')
        half_yearly_payments = Payment.objects.filter(user=self.half_yearly_paying_user).order_by('-last_action_at')
        yearly_payments = Payment.objects.filter(user=self.yearly_paying_user).order_by('-last_action_at')
        self.assertEqual(monthly_payments.count(), 3)
        self.assertEqual(quarterly_payments.count(), 2)
        self.assertEqual(half_yearly_payments.count(), 1)
        self.assertEqual(yearly_payments.count(), 1)

        # test half-yearly subscription
        self._turn_back_subscription_due_date(6, subscriptions)

        self.assertTrue(monthly_subscription.check_payment_due())
        self.assertTrue(quarterly_subscription.check_payment_due())
        self.assertTrue(half_yearly_subscription.check_payment_due())
        self.assertFalse(yearly_subscription.check_payment_due())

        # process due payments
        self._process_due_subscriptions(subscriptions)

        # check payments were made
        monthly_payments = Payment.objects.filter(user=self.monthly_paying_user).order_by('-last_action_at')
        quarterly_payments = Payment.objects.filter(user=self.quarterly_paying_user).order_by('-last_action_at')
        half_yearly_payments = Payment.objects.filter(user=self.half_yearly_paying_user).order_by('-last_action_at')
        yearly_payments = Payment.objects.filter(user=self.yearly_paying_user).order_by('-last_action_at')
        self.assertEqual(monthly_payments.count(), 4)
        self.assertEqual(quarterly_payments.count(), 3)
        self.assertEqual(half_yearly_payments.count(), 2)
        self.assertEqual(yearly_payments.count(), 1)

        # test yearly subscription
        self._turn_back_subscription_due_date(12, subscriptions)

        self.assertTrue(monthly_subscription.check_payment_due())
        self.assertTrue(quarterly_subscription.check_payment_due())
        self.assertTrue(half_yearly_subscription.check_payment_due())
        self.assertTrue(yearly_subscription.check_payment_due())

        # process due payments
        self._process_due_subscriptions(subscriptions)

        # check payments were made
        monthly_payments = Payment.objects.filter(user=self.monthly_paying_user).order_by('-last_action_at')
        quarterly_payments = Payment.objects.filter(user=self.quarterly_paying_user).order_by('-last_action_at')
        half_yearly_payments = Payment.objects.filter(user=self.half_yearly_paying_user).order_by('-last_action_at')
        yearly_payments = Payment.objects.filter(user=self.yearly_paying_user).order_by('-last_action_at')
        self.assertEqual(monthly_payments.count(), 5)
        self.assertEqual(quarterly_payments.count(), 4)
        self.assertEqual(half_yearly_payments.count(), 3)
        self.assertEqual(yearly_payments.count(), 2)

        # check debit amounts
        monthly_payment = monthly_payments.first()
        quarterly_payment = quarterly_payments.first()
        half_yearly_payment = half_yearly_payments.first()
        yearly_payment = yearly_payments.first()
        self.assertEqual(monthly_payment.debit_amount, monthly_amount)
        self.assertEqual(quarterly_payment.debit_amount, monthly_amount * 3)
        self.assertEqual(half_yearly_payment.debit_amount, monthly_amount * 6)
        self.assertEqual(yearly_payment.debit_amount, monthly_amount * 12)

    def test_2_anonymous_access_locked(self):
        pass
    
    @unittest.skipIf(getattr(settings, 'PAYMENTS_TEST_PHASE', False), 'Test skipped because payment system is in test-server mode!')
    def test_3_hardcoded_security_checks(self):
        pass
        # check if
        
    def test_4_subscription_state_safety(self):
        # tests if exclusive subscription states can really not occur
        pass

        
class AnyonmousUserPaymentsAccessTest(TestCase):
    """ Tests that the most important payment functions cannot be accessed by anonymous users. """
    pass
        
        