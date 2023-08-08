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
    
    def _create_invoice_at_provider(self, *args, **kwargs):
        """ Tryton does not block until the PDF is created, so if we call get-document too fast after creation, it will
            return a 404. So we wait manually.
            TODO: remove this once tryton is blocking their request until PDF creation is finished. """
        ret = super()._create_invoice_at_provider(*args, **kwargs)
        import time
        time.sleep(5)
        return ret
    
    def _parse_finalize_invoice_result(self, request):
        """ Helper function for `_finalize_invoice_at_provider()`, parses the resulting
            document id from the returned status 200 request or returns None if there was none.
            Tryton returns only the ID as body text here. """
        document_id = request.text
        return document_id or None
        