# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import traceback

from django.core.management.base import BaseCommand
from django.utils.encoding import force_text

from cosinnus.conf import settings
from cosinnus.core.middleware.cosinnus_middleware import initialize_cosinnus_after_startup
from wechange_payments.payment import process_due_subscription_payments


logger = logging.getLogger('cosinnus')


class Command(BaseCommand):
    help = 'Checks all subscriptions, executes payments on the ones that are due, \
            and terminates canceled ones that are past their paid date.'

    def handle(self, *args, **options):
        try:
            initialize_cosinnus_after_startup()
            process_due_subscription_payments()
        except Exception as e:
            logger.error('A critical error occured during daily subscription payment processing and bubbled up completely! Exception was: %s' % force_text(e), 
                         extra={'exception': e, 'trace': traceback.format_exc()})
            if settings.DEBUG:
                raise
            