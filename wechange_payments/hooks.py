# -*- coding: utf-8 -*-
from django.dispatch import receiver
from wechange_payments.signals import successful_payment_made
from wechange_payments.backends import get_invoice_backend

import logging
from wechange_payments.mails import PAYMENT_EVENT_SUCCESSFUL_PAYMENT,\
    send_payment_event_payment_email
logger = logging.getLogger('wechange-payments')


@receiver(successful_payment_made)
def start_invoice_generation(sender, payment, **kwargs):
    """ After a successfull payment, we start a threaded invoice generation """
    invoice_backend = get_invoice_backend()
    invoice_backend.create_invoice_for_payment(payment, threaded=True)

    
                        