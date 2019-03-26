# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from wechange_payments.conf import settings

from wechange_payments.backends import get_backend
from django.http.response import JsonResponse


def make_sepa_payment(request):
    backend = get_backend()
    return JsonResponse({'status': backend.test_status()})
