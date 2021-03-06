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
from wechange_payments.conf import settings
from wechange_payments.models import Invoice


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
            from an invoices and its attached payment instance. """
        payment = invoice.payment
        if payment.organisation:
            recipient_name = payment.organisation
            supplement = payment.first_name + ' ' + payment.last_name
        else:
            recipient_name = payment.first_name + ' ' + payment.last_name
            supplement = None
        data = {
            'archived': False,
            'voucherDate': invoice.created.isoformat(timespec='milliseconds'),
            'address': {
                'name': recipient_name,
                'supplement': supplement,
                'street': payment.address,
                'city': payment.city,
                'zip': payment.postal_code,
                'countryCode': str(payment.country),
            },
            'lineItems': [
                {
                    'type': 'custom',
                    'name': force_text(settings.PAYMENTS_INVOICE_LINE_ITEM_NAME % {'portal_name': CosinnusPortal.get_current().name}),
                    'description': force_text(settings.PAYMENTS_INVOICE_LINE_ITEM_DESCRIPTION % {'user_id': invoice.user.id}),
                    'quantity': 1,
                    'unitName': 'Stück',
                    'unitPrice': {
                        'currency': 'EUR',
                        'grossAmount': payment.amount,
                        'taxRatePercentage': settings.PAYMENTS_INVOICE_PROVIDER_TAX_RATE_PERCENT,
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
            'introduction': force_text(pgettext_lazy('Invoice PDF, important!', 'We charge you for our services as follows:')),
        }
        if getattr(settings, 'PAYMENTS_INVOICE_REMARK'):
            data.update({
                'remark': force_text(getattr(settings, 'PAYMENTS_INVOICE_REMARK')),
            })
        return data
    
    def _create_invoice_at_provider(self, invoice):
        """ Calls the action to render an invoice as PDF on the server. 
            This must set the `provider_id` field of the Invoice!
            @return: the same invoice instance if successful, raise Exception otherwise. """
            
        post_url = settings.PAYMENTS_LEXOFFICE_API_DOMAIN + LEXOFFICE_API_ENDPOINT_CREATE_INVOICE
        headers = {
            'Authorization': 'Bearer %s' % settings.PAYMENTS_LEXOFFICE_API_KEY, 
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        
        data = self._make_invoice_request_params(invoice)
        req = requests.post(post_url, headers=headers, json=data)
        
        if not req.status_code == 201:
            extra = {'post_url': post_url, 'status': req.status_code, 'content': req._content}
            logger.error('Payments: Invoice API creation failed, request did not return status=201.', extra=extra)
            raise Exception('Payments: Non-201 request return status code (request has been logged as error).')
            
        result = req.json()
        if not 'id' in result:
            extra = {'post_url': post_url, 'status': req.status_code, 'content': req._content, 'result': req.result}
            logger.error('Payments: Invoice API creation result did not contain field "id".', extra=extra)
            raise Exception('Payments: Missing fields in creation request result (request has been logged as error).')
        
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
        
        invoice.provider_id = result['id']
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
        
        if not invoice.provider_id:
            raise Exception('`provider_id` not present in invoice!')
        
        get_url = settings.PAYMENTS_LEXOFFICE_API_DOMAIN + LEXOFFICE_API_ENDPOINT_RENDER_INVOICE % {
            'id': invoice.provider_id
        }
        headers = {
            'Authorization': 'Bearer %s' % settings.PAYMENTS_LEXOFFICE_API_KEY, 
            'Accept': 'application/json',
        }
        req = requests.get(get_url, headers=headers)
        
        if not req.status_code == 200:
            extra = {'get_url': get_url, 'status': req.status_code, 'content': req._content}
            logger.error('Payments: Invoice API render failed, request did not return status=200.', extra=extra)
            raise Exception('Payments: Non-200 request return status code (request has been logged as error).')
            
        result = req.json()
        if not 'documentFileId' in result:
            extra = {'get_url': get_url, 'status': req.status_code, 'content': req._content, 'result': req.result}
            logger.error('Payments: Invoice API rendering result did not contain field "documentFileId".', extra=extra)
            raise Exception('Payments: Missing fields in rendering request result (request has been logged as error).')
        
        """
        Sample success response:
        {
            "documentFileId": "b26e1d73-19ff-46b1-8929-09d8d73d4167"
        }
        """
        
        extra_data = invoice.extra_data or {}
        extra_data.update({
            'documentFileId': result['documentFileId']
        })
        invoice.extra_data = extra_data
        invoice.state = Invoice.STATE_2_FINALIZED
        invoice.save()
        
        return invoice
        
    
    def _download_invoice_from_provider(self, invoice):
        """ Download a PDF file for a finalized, rendered invoice.
            Expects fields in `extra_data` set in the invoice, that are needed to download the rendered invoice
            document from the provider.
            This must set the `file` field to the invoice download.
            @return: the same invoice instance if successful, raise Exception otherwise. """
        
        if not 'documentFileId' in invoice.extra_data:
            raise Exception('`documentFileId` not present in invoice `extra_data`!')
        
        get_url = settings.PAYMENTS_LEXOFFICE_API_DOMAIN + LEXOFFICE_API_ENDPOINT_DOWNLOAD_INVOICE % {
            'id': invoice.extra_data['documentFileId']
        }
        headers = {
            'Authorization': 'Bearer %s' % settings.PAYMENTS_LEXOFFICE_API_KEY, 
        }
        req = requests.get(get_url, headers=headers)
        
        if not req.status_code == 200:
            extra = {'get_url': get_url, 'status': req.status_code, 'content': req._content}
            logger.error('Payments: Invoice API download failed, request did not return status=200.', extra=extra)
            raise Exception('Payments: Non-200 request return status code (request has been logged as error).')
            
        content = req.content
        if not content:
            extra = {'get_url': get_url, 'status': req.status_code, 'content': req._content, 'result': req.result}
            logger.error('Payments: Invoice API download result was empty.', extra=extra)
            raise Exception('Payments: Missing content in download request result (request has been logged as error).')
        
        hash_source = str(uuid1()) + invoice.provider_id
        filename = hashlib.sha1(hash_source.encode('utf-8')).hexdigest()
        invoice.file.save(filename, ContentFile(content), save=False)
        invoice.state = Invoice.STATE_3_DOWNLOADED
        invoice.is_ready = True
        invoice.save()
        
        return invoice
    