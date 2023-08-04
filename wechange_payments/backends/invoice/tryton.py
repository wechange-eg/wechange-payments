# -*- coding: utf-8 -*-
import hashlib
import logging
from uuid import uuid1

from django.core.files.base import ContentFile
from django.utils.encoding import force_text
from django.utils.translation import pgettext_lazy
import requests

from cosinnus.models.group import CosinnusPortal
from wechange_payments.backends.invoice.base import BaseInvoiceBackend
from wechange_payments.backends.invoice.lexoffice import LexofficeInvoiceBackend
from wechange_payments.conf import settings
from wechange_payments.models import Invoice


logger = logging.getLogger('wechange-payments')


TRYTON_API_ENDPOINT_CREATE_INVOICE = f'/lexoffice/{settings.PAYMENTS_TRYTON_DB_NAME}/v1/invoices?finalize=true'
TRYTON_API_ENDPOINT_RENDER_INVOICE = f'/lexoffice/{settings.PAYMENTS_TRYTON_DB_NAME}/v1/invoices/%(id)s/document'
TRYTON_API_ENDPOINT_DOWNLOAD_INVOICE = f'/lexoffice/{settings.PAYMENTS_TRYTON_DB_NAME}/v1/files/%(id)s'
TRYTON_API_ENDPOINT_CREATE_CONTACT = None # endpoint does not exist in Tryton!

EXTRA_DATA_CONTACT_ID = 'lexoffice-contact-id'


class TrytonInvoiceBackend(LexofficeInvoiceBackend):
    
    API_ENDPOINT_CREATE_INVOICE = TRYTON_API_ENDPOINT_CREATE_INVOICE
    API_ENDPOINT_RENDER_INVOICE = TRYTON_API_ENDPOINT_RENDER_INVOICE
    API_ENDPOINT_DOWNLOAD_INVOICE = TRYTON_API_ENDPOINT_DOWNLOAD_INVOICE
    API_ENDPOINT_CREATE_CONTACT = TRYTON_API_ENDPOINT_CREATE_CONTACT
    
    def _X_get_tax_rate_percent(self):
        """ Returns the tax rate percent as datatype the backend requires. """
        return "19"