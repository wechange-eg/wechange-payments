# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging

from django_cron import CronJobBase, Schedule

from cosinnus.cron import CosinnusCronJobBase
from wechange_payments.payment import process_due_subscription_payments
from wechange_payments.conf import settings

logger = logging.getLogger('wechange-payments')


class ProcessDueSubscriptionPayments(CosinnusCronJobBase):
    
    RUN_AT_TIMES = ['00:30',]
    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    
    cosinnus_code = 'wechange_payments.process_due_subscription_payments'
    
    def do(self):
        # check if a portal restriction applies for the cron
        specific_portal_slugs = getattr(settings, 'PAYMENTS_CRON_ENABLED_FOR_SPECIFIC_PORTAL_SLUGS_ONLY', []) 
        if specific_portal_slugs:
            from cosinnus.models.group import CosinnusPortal
            portal = CosinnusPortal.get_current()
            if not portal.slug in specific_portal_slugs:
                return "Skipped subscription processing: current portal slug not in `PAYMENTS_CRON_ENABLED_FOR_SPECIFIC_PORTAL_SLUGS_ONLY`."
        
        # process subscriptions and return counts as log
        (ended_subscriptions, booked_subscriptions) = process_due_subscription_payments()
        logger.info('Cron-based daily subscription payment processing finished. Details in extra.',
                extra={'ended_subscriptions': ended_subscriptions, 'booked_subscriptions': booked_subscriptions})
        return "Ended expired subscriptions: %d. Processed payments for due subscriptions: %d" % (ended_subscriptions, booked_subscriptions)
