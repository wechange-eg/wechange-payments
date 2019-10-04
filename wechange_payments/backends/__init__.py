# -*- coding: utf-8 -*-

from wechange_payments.backends.payment.base import DummyBackend
from wechange_payments.backends.payment.betterpayments import BetterPaymentBackend
from wechange_payments.utils.utils import resolve_class

BACKEND = None
INVOICE_BACKEND = None

def get_backend():
    global BACKEND
    if BACKEND is None:
        from wechange_payments.conf import settings
        BACKEND = resolve_class(settings.PAYMENTS_BACKEND)
        BACKEND = BACKEND()
    return BACKEND

def get_invoice_backend():
    global INVOICE_BACKEND
    if INVOICE_BACKEND is None:
        from wechange_payments.conf import settings
        INVOICE_BACKEND = resolve_class(settings.PAYMENTS_INVOICE_BACKEND)
        INVOICE_BACKEND = INVOICE_BACKEND()
    return INVOICE_BACKEND
