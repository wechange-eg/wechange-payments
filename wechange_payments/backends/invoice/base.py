# -*- coding: utf-8 -*-

from wechange_payments.conf import settings
from django.core.exceptions import ImproperlyConfigured
from wechange_payments.models import Payment
from wechange_payments.utils.utils import resolve_class
from django.template.loader import render_to_string
from wechange_payments import signals

import logging
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
    
    
        
    def create_invoice_for_payment(self, payment):
        """ Creates a finalized invoice in Lexoffice with all required data.
            @return: An Invoice instance if the invoice was created in Lexoffice, raise Exception otherwise """
        raise NotImplemented('Use a proper invoice provider backend for this function!')
    
    def render_invoice_for_payment(self, invoice):
        """ Calls the action to render an invoice as PDF on the server. 
            @return: True if successful, raise Exception otherwise. """
        raise NotImplemented('Use a proper invoice provider backend for this function!')
    
    def download_invoice_for_payment(self, invoice):
        """ Download a PDF file for a finalized, rendered invoice.
            @param documentFileId: The documentFileId for the invoice, which is returned from
                Lexoffice after calling the render invoice endpoint.
            @return: A file response? """
        raise NotImplemented('Use a proper invoice provider backend for this function!')
        
    def handle_postback(self, request, params):
        """ For a provider backend-only postback to post feedback on a transaction. 
            Always return 200 on this and save the data. """
        raise NotImplemented('Use a proper payment provider backend for this function!')
        

