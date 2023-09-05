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
LEXOFFICE_API_ENDPOINT_CREATE_CONTACT = '/v1/contacts'

EXTRA_DATA_CONTACT_ID = 'lexoffice-contact-id'


class LexofficeInvoiceBackend(BaseInvoiceBackend):
    
    API_ENDPOINT_CREATE_INVOICE = LEXOFFICE_API_ENDPOINT_CREATE_INVOICE
    API_ENDPOINT_RENDER_INVOICE = LEXOFFICE_API_ENDPOINT_RENDER_INVOICE
    API_ENDPOINT_DOWNLOAD_INVOICE = LEXOFFICE_API_ENDPOINT_DOWNLOAD_INVOICE
    API_ENDPOINT_CREATE_CONTACT = LEXOFFICE_API_ENDPOINT_CREATE_CONTACT
    
    api_domain = None # initialized on init
    api_key = None # initialized on init
    
    required_setting_keys = [
        'api_domain',
        'api_key',
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        auth_data = kwargs.get('auth_data')
        self.api_domain = auth_data.get('api_domain')
        self.api_key = auth_data.get('api_key')
    
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
        
        item_name = force_text(settings.PAYMENTS_INVOICE_LINE_ITEM_NAME % {'portal_name': CosinnusPortal.get_current().name})
        item_description = force_text(settings.PAYMENTS_INVOICE_LINE_ITEM_DESCRIPTION % {'user_id': invoice.user.id})
        item_description += f' (transaction-id: {payment.internal_transaction_id}, type: {payment.type})'
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
                    'name': item_name,
                    'description': item_description,
                    'quantity': 1,
                    'unitName': 'Stück',
                    'unitPrice': {
                        'currency': 'EUR',
                        'grossAmount': payment.amount,
                        'taxRatePercentage': self._get_tax_rate_percent(),
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
        data = self._add_contact_invoice_request_params(payment, data)
        
        if getattr(settings, 'PAYMENTS_INVOICE_REMARK'):
            data.update({
                'remark': force_text(getattr(settings, 'PAYMENTS_INVOICE_REMARK')),
            })
        return data
    
    def _add_contact_invoice_request_params(self, payment, data):
        # add LexOffice contact ID if one was created in reference payment
        reference_payment = payment if payment.is_reference_payment else payment.subscription.reference_payment
        contact_id = reference_payment.extra_data.get(EXTRA_DATA_CONTACT_ID, None)
        if contact_id:
            data['address']['contactId'] = contact_id
        return data
    
    def _create_contact_for_payment(self, invoice, force=False):
        """ Creates a LexOffice contact for the reference payment of this invoice.
            LexOffice requires this for some (currently inner-EU, non-DE) customers.
            @return: True if successful, False if otherwise """
        payment = invoice.payment
        reference_payment = payment if payment.is_reference_payment else payment.subscription.reference_payment
        contact_id = reference_payment.extra_data.get(EXTRA_DATA_CONTACT_ID, None)
        # sanity check, if the payment already has a contact ID, don't create a new one
        if contact_id and not force:
            logger.info('ContactId for payment already existed, not creating a new one.', extra={'invoice-id': invoice.id}) 
            return False
        contact_post_url = self.api_domain + self.API_ENDPOINT_CREATE_CONTACT
        headers = {
            'Authorization': 'Bearer %s' % self.api_key,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        contact_id_data = {
            'version': 0,
            'roles': {
                'customer': {}
            },
            'person': {
                'firstName': reference_payment.first_name,
                'lastName': reference_payment.last_name
            },
            'note': f'WECHANGE PAYL contact for subscription id: {reference_payment.subscription_id}, user id: {reference_payment.user_id}'
        }
        req = requests.post(contact_post_url, headers=headers, json=contact_id_data)
        
        if not req.status_code == 200:
            extra = {'post_url': contact_post_url, 'status': req.status_code, 'content': req._content}
            logger.error('Payments: Contact API creation failed, request did not return status=200.', extra=extra)
            if settings.DEBUG:
                print(extra)
            raise Exception('Payments: Non-201 request return status code (request has been logged as error).')
            
        result = req.json()
        if not 'id' in result:
            extra = {'post_url': contact_post_url, 'status': req.status_code, 'content': req._content, 'result': req.result}
            logger.error('Payments: Contact API creation result did not contain field "id".', extra=extra)
            if settings.DEBUG:
                print(extra)
            raise Exception('Payments: Missing fields in contact creation request result (request has been logged as error).')
        
        """
        Sample success response:
        {
          "id": "66196c43-baf3-4335-bfee-d610367059db",
          "resourceUri": "https://api.lexoffice.io/v1/contacts/66196c43-bfee-baf3-4335-d610367059db",
          "createdDate": "2016-06-29T15:15:09.447+02:00",
          "updatedDate": "2016-06-29T15:15:09.447+02:00",
          "version": 1
        }
        """
        
        contact_id = result.get('id')
        reference_payment.extra_data[EXTRA_DATA_CONTACT_ID] = contact_id
        reference_payment.save(update_fields=['extra_data'])
        return True

    
    def _create_invoice_at_provider(self, invoice, retry_after_contact_create=False):
        """ Calls the action to render an invoice as PDF on the server. 
            This must set the `provider_id` field of the Invoice!
            @return: the same invoice instance if successful, raise Exception otherwise. """
            
        post_url = self.api_domain + self.API_ENDPOINT_CREATE_INVOICE
        headers = {
            'Authorization': 'Bearer %s' % self.api_key,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        
        data = self._make_invoice_request_params(invoice)
        req = requests.post(post_url, headers=headers, json=data)
        
        if not req.status_code in [200, 201]:
            return_json = None
            try:
                return_json = req.json()
            except Exception as json_e:
                pass
            
            error_msg_requires_contact = 'Validation failed: [postingCategoryId: Legen Sie den Kontakt zunächst an.]'
            if return_json and  return_json.get('status') == 406 and return_json.get('message') == error_msg_requires_contact \
                     and not retry_after_contact_create:
                # for some customers, we must create a contact first. if so we try to create a contact first
                # and retry this same invoice creation *once*
                self._create_contact_for_payment(invoice)
                return self._create_invoice_at_provider(invoice, retry_after_contact_create=True)
            
            extra = {'post_url': post_url, 'status': req.status_code, 'content': req._content}
            logger.error('Payments: Invoice API creation failed, request did not return status=201.', extra=extra)
            if settings.DEBUG:
                print(extra)
            raise Exception('Payments: Non-201 request return status code (request has been logged as error).')
            
        result = req.json()
        if not 'id' in result:
            extra = {'post_url': post_url, 'status': req.status_code, 'content': req._content, 'result': req.result}
            logger.error('Payments: Invoice API creation result did not contain field "id".', extra=extra)
            if settings.DEBUG:
                print(extra)
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
    
    def _parse_finalize_invoice_result(self, request):
        """ Helper function for `_finalize_invoice_at_provider()`, parses the resulting
            document id from the returned status 200 request or returns None if there was none.
             LexOffice returns JSON here. """
        result_json = request.json()
        if not 'documentFileId' in result_json:
            return None
        return result_json['documentFileId']
    
    def _finalize_invoice_at_provider(self, invoice):
        """ Calls the action to render an invoice as PDF on the server.
            Expects the `provider_id` field of the Invoice set!
            This must set in `extra_data` such attributes, that are needed to download the rendered invoice
            document by `self._download_invoice_from_provider()`
            @return: the same invoice instance if successful, raise Exception otherwise. """
        
        if not invoice.provider_id:
            raise Exception('`provider_id` not present in invoice!')
        
        get_url = self.api_domain + self.API_ENDPOINT_RENDER_INVOICE % {
            'id': invoice.provider_id
        }
        headers = {
            'Authorization': 'Bearer %s' % self.api_key,
            'Accept': 'application/json',
        }
        req = requests.get(get_url, headers=headers)
        
        if not req.status_code == 200:
            extra = {'get_url': get_url, 'status': req.status_code, 'content': req._content}
            logger.error('Payments: Invoice API render failed, request did not return status=200.', extra=extra)
            if settings.DEBUG:
                print(extra)
            raise Exception('Payments: Non-200 request return status code (request has been logged as error).')
        
        document_file_id = self._parse_finalize_invoice_result(req)
        if not document_file_id:
            extra = {'get_url': get_url, 'status': req.status_code, 'content': req._content}
            if settings.DEBUG:
                print(extra)
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
            'documentFileId': document_file_id,
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
        
        get_url = self.api_domain + self.API_ENDPOINT_DOWNLOAD_INVOICE % {
            'id': invoice.extra_data['documentFileId']
        }
        headers = {
            'Authorization': 'Bearer %s' % self.api_key,
        }
        req = requests.get(get_url, headers=headers)
        
        if not req.status_code == 200:
            extra = {'get_url': get_url, 'status': req.status_code, 'content': req._content}
            logger.error('Payments: Invoice API download failed, request did not return status=200.', extra=extra)
            if settings.DEBUG:
                print(extra)
            raise Exception('Payments: Non-200 request return status code (request has been logged as error).')
            
        content = req.content
        if not content:
            extra = {'get_url': get_url, 'status': req.status_code, 'content': req._content, 'result': req.result}
            logger.error('Payments: Invoice API download result was empty.', extra=extra)
            if settings.DEBUG:
                print(extra)
            raise Exception('Payments: Missing content in download request result (request has been logged as error).')
        
        hash_source = str(uuid1()) + invoice.provider_id
        filename = hashlib.sha1(hash_source.encode('utf-8')).hexdigest()
        invoice.file.save(filename, ContentFile(content), save=False)
        invoice.state = Invoice.STATE_3_DOWNLOADED
        invoice.is_ready = True
        invoice.save()
        
        return invoice
    