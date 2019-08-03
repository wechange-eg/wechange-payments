# -*- coding: utf-8 -*-

from django.http.response import JsonResponse, HttpResponseNotAllowed
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt
import six

from wechange_payments.backends import get_backend
from wechange_payments.conf import settings
from wechange_payments.models import Payment

import logging

logger = logging.getLogger('wechange-payments')


@csrf_exempt
def make_payment(request):
    if not request.method=='POST':
        return HttpResponseNotAllowed(['POST'])
    
    backend = get_backend()
    params = request.POST.copy()
    user = request.user if request.user.is_authenticated else None
    
    payment_type = params.get('payment_type', None)
    result = 'Payment Type "%s" is not supported!' % payment_type 
    if payment_type in settings.PAYMENTS_ACCEPTED_PAYMENT_METHODS:
        if payment_type == 'dd':
            # check for complete dataset
            missing_params = backend.check_missing_params(params, payment_type)
            if missing_params:
                return JsonResponse({'error': _('Please fill out all of the missing fields!'), 'missing_parameters': missing_params}, status=500)
            result = backend.make_sepa_payment(request, params, user=user)
        
    
    if isinstance(result, six.string_types):
        # special error cases:
        # 126: Invalid bank info
        if payment_type == 'dd' and result.endswith('(126)'):
            return JsonResponse({'error': _('The entered payment information is invalid. Please make sure you entered everything correctly!'), 'missing_parameters': ['iban', 'bic']}, status=500)
        return JsonResponse({'error': result}, status=500)
    
    assert isinstance(result, Payment)
    payment = result
    
    
    email = params.get('email', None)
    if email:
        try:
            backend.send_successful_payment_email(email, payment, payment_type)
        except Exception as e:
            logger.warning('Payments: SEPA Payment successful, but sending the success email to the user failed!', extra={'internal_transaction_id': payment.internal_transaction_id, 'exception': e})
            if settings.DEBUG:
                raise
        
    data = {
        'sepa_mandate_token': payment.extra_data['sepa_mandate_token'],
        'amount_paid': payment.amount,
        'order_id': payment.internal_transaction_id,
    }
    if 'redirect_to' in payment.extra_data:
        data.update({
            'redirect_to': payment.extra_data['redirect_to']
        })
    return JsonResponse(data)


def postback_endpoint(request):
    """ For providers that offer a postback URL as logging/validation """
    
    backend = get_backend()
    backend.handle_postback(request, request.POST.copy())
    return JsonResponse({'status': 'ok'})
