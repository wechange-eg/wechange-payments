# -*- coding: utf-8 -*-

from wechange_payments.conf import settings

from wechange_payments.backends import get_backend
from django.http.response import JsonResponse, HttpResponseNotAllowed
import six
from wechange_payments.models import Payment
from django.views.decorators.csrf import csrf_exempt


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
            missing_params = backend.check_missing_params(params, backend.REQUIRED_PARAMS_SEPA)
            if missing_params:
                return JsonResponse({'error': 'Missing parameters for request.', 'missing_parameters': missing_params}, status=500)
            result = backend.make_sepa_payment(request, params, user=user)
        
    
    if isinstance(result, six.string_types):
        return JsonResponse({'error': result}, status=500)
    
    assert isinstance(result, Payment)
    payment = result
        
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
