# -*- coding: utf-8 -*-

import logging
import threading

from annoying.functions import get_object_or_None
from django.core.exceptions import ImproperlyConfigured

from wechange_payments.conf import settings
from wechange_payments.models import Invoice, Payment


logger = logging.getLogger('wechange-payments')

class BaseInvoiceBackend(object):
    """  """
    
    # define this in the implementing backend
    required_setting_keys = []
    
    def __init__(self):
        for key in self.required_setting_keys:
            if not getattr(settings, key, None):
                raise ImproperlyConfigured('Setting "%s" is required for backend "%s"!' 
                            % (key, self.__class__.__name__))
    
    def create_invoice_for_payment(self, payment, threaded=False):
        """ Tries to create a finalized invoice in Lexoffice with all required data for a given payment.
            @return: An Invoice instance if the invoice was created in Lexoffice, raise Exception otherwise """
        if threaded:
            thread = threading.Thread(target=self.create_invoice_for_payment, args=(payment, False))
            thread.start()
            return
        
        try:
            # only create invoices for successfully paid Payments!
            if payment.status != Payment.STATUS_PAID:
                return
            
            invoice = get_object_or_None(Invoice, payment=payment)
            if not invoice:
                invoice = Invoice.objects.create(
                    payment=payment,
                    user=payment.user,
                    backend='%s.%s' %(self.__class__.__module__, self.__class__.__name__)
                )
            self.create_invoice(invoice, threaded=False)
        except Exception as e:
            logger.error('Payments: Critical: Error during (our) invoice creation: Could not create an `Invoice` instance for a Payment! This must be manually repeated!', extra={'exception': e, 'payment_internal_transaction_id': payment.internal_transaction_id})
            if settings.DEBUG:
                raise
        
    def create_invoice(self, invoice, threaded=False):
        """ Tries to create, finalize and download an invoice at the invoice provider 
            (given an instance of our `Invoice`) if the invoice is not finished yet.
            For unfinished invoices, will only call the API for missing steps.
            @param threaded: If True, will run in a thread.
            @return The finished instance of `Invoice` or None if *any* step failed """
        if threaded:
            thread = threading.Thread(target=self.create_invoice, args=(invoice, False))
            thread.start()
            return
            
        if invoice.is_ready or invoice.state == Invoice.STATE_3_DOWNLOADED:
            return invoice
        exc = None
        try:
            if invoice.state == Invoice.STATE_0_NOT_CREATED:
                self._create_invoice_at_provider(invoice)
            if invoice.state == Invoice.STATE_1_CREATED:
                self._finalize_invoice_at_provider(invoice)
            if invoice.state == Invoice.STATE_2_FINALIZED:
                self._download_invoice_from_provider(invoice)
            if invoice.state == Invoice.STATE_3_DOWNLOADED:
                logger.info('Payments: Successfully created an invoice at the invoice provider!', extra={'invoice_id': invoice.id})
                return invoice
        except Exception as exc:
            if settings.DEBUG:
                raise
            logger.error('Payments: Error during invoice creation: Stopped at invoice state %d!' % invoice.state, extra={'state': invoice.state, 'exception': exc, 'invoice_id': invoice.id, 'payment_internal_transaction_id': invoice.payment.internal_transaction_id})
        # save the invoice to trigger updating its `last_action_at`, so we can delay repeated API calls.
        invoice.save()
        return None
    
    def _create_invoice_at_provider(self, invoice):
        """ Calls the action to render an invoice as PDF on the server. 
            This must set the `provider_id` field of the Invoice!
            @return: the same invoice instance if successful, raise Exception otherwise. """
        raise Exception('NYI: Use a proper invoice provider backend for this function!')
    
    def _finalize_invoice_at_provider(self, invoice):
        """ Calls the action to render an invoice as PDF on the server. 
            Expects the `provider_id` field of the Invoice set!
            This must set in `extra_data` such attributes, that are needed to download the rendered invoice
            document by `self._download_invoice_from_provider()`
            @return: the same invoice instance if successful, raise Exception otherwise. """
        raise Exception('NYI: Use a proper invoice provider backend for this function!')
    
    def _download_invoice_from_provider(self, invoice):
        """ Download a PDF file for a finalized, rendered invoice.
            Expects fields in `extra_data` set in the invoice, that are needed to download the rendered invoice
            document from the provider.
            This must set the `file` field to the invoice download.
            @return: the same invoice instance if successful, raise Exception otherwise. """
        raise Exception('NYI: Use a proper invoice provider backend for this function!')
        

