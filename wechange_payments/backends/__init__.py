# -*- coding: utf-8 -*-

from wechange_payments.utils.utils import resolve_class

BACKEND = None
INVOICE_BACKEND = None
ADDITIONAL_INVOICE_BACKENDS = None

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
        Backend = resolve_class(settings.PAYMENTS_INVOICE_BACKEND)
        INVOICE_BACKEND = Backend(auth_data=settings.PAYMENTS_INVOICE_BACKEND_AUTH_DATA)
    return INVOICE_BACKEND

def get_additional_invoice_backends():
    global ADDITIONAL_INVOICE_BACKENDS
    if ADDITIONAL_INVOICE_BACKENDS is None:
        ADDITIONAL_INVOICE_BACKENDS = []
        from wechange_payments.conf import settings
        for backend_dict in settings.PAYMENTS_ADDITIONAL_INVOICES_BACKENDS:
            Backend = resolve_class(backend_dict.get('backend'))
            ADDITIONAL_INVOICE_BACKENDS.append(Backend(auth_data=backend_dict.get('auth_data')))
    return ADDITIONAL_INVOICE_BACKENDS

