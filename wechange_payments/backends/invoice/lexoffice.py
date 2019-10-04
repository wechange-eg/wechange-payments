# -*- coding: utf-8 -*-
import urllib
import hashlib
from wechange_payments.models import TransactionLog, Payment, Invoice

import logging
import requests
import six
import uuid
from django.urls.base import reverse
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied
from cosinnus.models.group import CosinnusPortal
from annoying.functions import get_object_or_None
from django.utils.timezone import now
from django.contrib import messages
from copy import copy
from django.utils.translation import ugettext_lazy as _, pgettext_lazy as p_
from wechange_payments.backends.invoice.base import BaseInvoiceBackend
from wechange_payments.conf import settings
import json
from django.utils.encoding import force_text
from cosinnus.utils.http import request_to_string

logger = logging.getLogger('wechange-payments')


LEXOFFICE_API_ENDPOINT_CREATE_INVOICE = '/v1/invoices?finalize=true'
LEXOFFICE_API_ENDPOINT_RENDER_INVOICE = '/v1/invoices/%(id)s/document'
LEXOFFICE_API_ENDPOINT_DOWNLOAD_INVOICE = '/v1/files/%(id)s'


class LexofficeInvoiceBackend(BaseInvoiceBackend):
    
    required_setting_keys = [
        'PAYMENTS_LEXOFFICE_API_DOMAIN',
        'PAYMENTS_LEXOFFICE_API_KEY',
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def _make_invoice_request_params(self, invoice):
        """ Prepare all neccessary params for the invoice creation API for Lexoffice 
            from an invoices and its attached payment instance """
        payment = invoice.payment
        data = {
            'archived': False,
            'voucherDate': invoice.created.isoformat(timespec='milliseconds'),
            'address': {
                'name': payment.first_name + ' ' + payment.last_name,
                'street': payment.address,
                'city': payment.city,
                'zip': payment.postal_code,
                'countryCode': str(payment.country),
            },
            'lineItems': [
                {
                    'type': 'custom',
                    'name': force_text(p_('Invoice PDF, important!', 'Freely chosen user fee for %(portal_name)s') % {'portal_name': CosinnusPortal.get_current().name}),
                    'description': force_text(p_('Invoice PDF, important!', 'Electronic service')),
                    'quantity': 1,
                    'unitName': 'Stück',
                    'unitPrice': {
                        'currency': 'EUR',
                        'grossAmount': payment.amount,
                        'taxRatePercentage': 19,
                    },
                },
            ],
            'totalPrice': {
                'currency': 'EUR',
            },
            'taxConditions': {
                'taxType': 'gross',
            },
            'shippingConditions': {
                'shippingDate': invoice.created.isoformat(timespec='milliseconds'),
                'shippingType': 'service'
            },
            'introduction': force_text(p_('Invoice PDF, important!', 'We charge you for our services as follows:')),
            'remark': force_text(p_('Invoice PDF, important!', 'Payment has already been made. Thank you for your support!')),
        }
        return data
    
    def _create_invoice_at_provider(self, invoice):
        post_url = settings.PAYMENTS_LEXOFFICE_API_DOMAIN + LEXOFFICE_API_ENDPOINT_CREATE_INVOICE
        headers = {
            'Authorization': 'Bearer %s' % settings.PAYMENTS_LEXOFFICE_API_KEY, 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        
        data = self._make_invoice_request_params(invoice)
        #logger.warn(request_to_string('POST', post_url, headers=headers, json=data))
        req = requests.post(post_url, headers=headers, json=data)
        
        if not req.status_code == 201:
            extra = {'post_url': post_url, 'status': req.status_code, 'content': req._content}
            logger.error('Payments: Invoice API creation failed, request did not return status=200.', extra=extra)
            raise Exception('Payments: Non-200 request return status code (request has been logged as error).')
            
        result = req.json()
        if not 'id' in result:
            extra = {'post_url': post_url, 'status': req.status_code, 'content': req._content, 'result': req.result}
            logger.error('Payments: Invoice API creation result did not contain field "id".', extra=extra)
            raise Exception('Payments: Missing fields in request result (request has been logged as error).')
        
        """
        Sample success response:
        {
            "id" : "fdd20e84-06ef-49df-b4b5-71293b6e2bd6",
            "resourceUri": "https://api.lexoffice.io/v1/invoices/fdd20e84-06ef-49df-b4b5-71293b6e2bd6",
            "createdDate": "2019-10-04T15:22:22.702+02:00",
            "updatedDate": "2019-10-04T15:22:23.054+02:00",
            "version": 1
        }
        """
        
        invoice.provider_id = result
        extra_data = invoice.extra_data or {}
        extra_data.update(result)
        invoice.extra_data = extra_data
        invoice.state = Invoice.STATE_1_CREATED
        invoice.save()
        
        return invoice
    
    def _finalize_invoice_at_provider(self, invoice):
        """ Calls the action to render an invoice as PDF on the server. 
            Expects the `provider_id` field of the Invoice set!
            This must set in `extra_data` such attributes, that are needed to download the rendered invoice
            document by `self._download_invoice_from_provider()`
            @return: the same invoice instance if successful, raise Exception otherwise. """
        raise Exception('NYI: Use a proper invoice provider backend for this function!')
    