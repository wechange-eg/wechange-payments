# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from django_cron import CronJobBase, Schedule

from cosinnus.cron import CosinnusCronJobBase
from wechange_payments.payment import process_due_subscription_payments
from wechange_payments.conf import settings
from wechange_payments.backends import get_invoice_backend, get_additional_invoice_backends
from wechange_payments.models import Payment, AdditionalInvoice
from django.db.models import Q

logger = logging.getLogger('wechange-payments')


class ProcessDueSubscriptionPayments(CosinnusCronJobBase):
    
    RUN_AT_TIMES = ['04:00',]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    
    cosinnus_code = 'wechange_payments.process_due_subscription_payments'
    
    def do(self):
        # check if a portal restriction applies for the cron
        disabled_msg = _check_cron_disabled_on_portal()
        if disabled_msg:
            return disabled_msg
        
        # process subscriptions and return counts as log
        (ended_subscriptions, booked_subscriptions) = process_due_subscription_payments()
        logger.info('Cron-based daily subscription payment processing finished. Details in extra.',
                extra={'ended_subscriptions': ended_subscriptions, 'booked_subscriptions': booked_subscriptions})
        return "End expired subs: %d. Payments for due subs: %d" % (ended_subscriptions, booked_subscriptions)


class GenerateMissingInvoices(CosinnusCronJobBase):
    """ If the Invoice provider API was not reachable during payment time,
        the invoice might not have been generated yet. This cron checks
        all payments and generates any missing invoices. """
    
    RUN_AT_TIMES = ['04:30',]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    
    cosinnus_code = 'wechange_payments.generate_missing_invoices'
    
    def do(self):
        # check if a portal restriction applies for the cron
        disabled_msg = _check_cron_disabled_on_portal()
        if disabled_msg:
            return disabled_msg
        
        invoice_backend = get_invoice_backend()
        missing_invoice_payments = Payment.objects.filter(status=Payment.STATUS_PAID).filter(
            Q(invoice=None) | Q(invoice__is_ready=False))
        missing_before = missing_invoice_payments.count()
        invoices_created = 0
        for payment in missing_invoice_payments:
            invoice_backend.create_invoice_for_payment(payment, threaded=False)
            if payment.invoice is not None:
                invoices_created += 1
        
        still_missing = Payment.objects.filter(status=Payment.STATUS_PAID).filter(Q(invoice=None) | Q(invoice__is_ready=False)).count()
        return "Missing: %d. Invoices generated: %d. Still missing: %d"\
             % (missing_before, invoices_created, still_missing)


def _check_cron_disabled_on_portal():
    """ If anything but False is returned, payment crons should not run on this portal """
    # check if a portal restriction applies for the cron
    specific_portal_slugs = getattr(settings, 'PAYMENTS_CRON_ENABLED_FOR_SPECIFIC_PORTAL_SLUGS_ONLY', []) 
    if specific_portal_slugs:
        from cosinnus.models.group import CosinnusPortal
        portal = CosinnusPortal.get_current()
        if not portal.slug in specific_portal_slugs:
            return "Skipped cronjob: portal not enabled for payment cronjobs."
    return False
