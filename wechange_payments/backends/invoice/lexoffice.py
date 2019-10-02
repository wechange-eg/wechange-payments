# -*- coding: utf-8 -*-
import urllib
import hashlib
from wechange_payments.models import TransactionLog, Payment

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
from wechange_payments.payment import create_subscription_for_payment
from wechange_payments.backends.invoice.base import BaseInvoiceBackend

logger = logging.getLogger('wechange-payments')


LEXOFFICE_API_ENDPOINT_CREATE_INVOICE = '/v1/invoices?finalize=true'
LEXOFFICE_API_ENDPOINT_RENDER_INVOICE = '/v1/invoices/%(id)s/document'
LEXOFFICE_API_ENDPOINT_DOWNLOAD_INVOICE = '/v1/files/%(id)s'


class LexofficeInvoiceBackend(BaseInvoiceBackend):
    
    required_setting_keys = [
        'LEXOFFICE_API_DOMAIN',
        'LEXOFFICE_API_KEY',
    ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
