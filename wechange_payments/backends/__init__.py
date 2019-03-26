# -*- coding: utf-8 -*-

from .betterpayments import BetterPaymentBackend
from wechange_payments.utils.utils import resolve_class

BACKEND = None

def get_backend():
    global BACKEND
    if BACKEND is None:
        from wechange_payments.conf import settings
        BACKEND = resolve_class(settings.PAYMENTS_BACKEND)
        BACKEND = BACKEND()
    return BACKEND

