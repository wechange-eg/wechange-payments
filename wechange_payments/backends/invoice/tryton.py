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


TRYTON_API_ENDPOINT_CREATE_INVOICE = '/lexoffice/__DB_NAME__/v1/invoices?finalize=true'
TRYTON_API_ENDPOINT_RENDER_INVOICE = '/lexoffice/__DB_NAME__/v1/invoices/%(id)s/document'
TRYTON_API_ENDPOINT_DOWNLOAD_INVOICE = '/lexoffice/__DB_NAME__/v1/files/%(id)s'
TRYTON_API_ENDPOINT_CREATE_CONTACT = None # endpoint does not exist in Tryton!

EXTRA_DATA_CONTACT_ID = 'lexoffice-contact-id'


class TrytonInvoiceBackend(LexofficeInvoiceBackend):
    
    API_ENDPOINT_CREATE_INVOICE = TRYTON_API_ENDPOINT_CREATE_INVOICE
    API_ENDPOINT_RENDER_INVOICE = TRYTON_API_ENDPOINT_RENDER_INVOICE
    API_ENDPOINT_DOWNLOAD_INVOICE = TRYTON_API_ENDPOINT_DOWNLOAD_INVOICE
    API_ENDPOINT_CREATE_CONTACT = TRYTON_API_ENDPOINT_CREATE_CONTACT
    
    db_name = None # initialized on init
    
    required_setting_keys = [
        'api_domain',
        'api_key',
        'db_name',
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        auth_data = kwargs.get('auth_data')
        self.db_name = auth_data.get('db_name')
        self.API_ENDPOINT_CREATE_INVOICE = self.API_ENDPOINT_CREATE_INVOICE.replace('__DB_NAME__', self.db_name)
        self.API_ENDPOINT_RENDER_INVOICE = self.API_ENDPOINT_RENDER_INVOICE.replace('__DB_NAME__', self.db_name)
        self.API_ENDPOINT_DOWNLOAD_INVOICE = self.API_ENDPOINT_DOWNLOAD_INVOICE.replace('__DB_NAME__', self.db_name)
    
    def _make_invoice_request_params(self, invoice):
        """ In Tryton, we can add the internal transaction ID from betterpayments so
            accounting can connect invoices and payments. """
        data = super()._make_invoice_request_params(invoice)
        data.update({
            'transaction_id': invoice.payment.internal_transaction_id,
            'payment_type': invoice.payment.type,
        })
        return data
    
    def _add_contact_invoice_request_params(self, payment, data):
        """ Overriden from LexOffice logic, we do not use contacts for Tryton """
        return data
