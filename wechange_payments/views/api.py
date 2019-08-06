# -*- coding: utf-8 -*-

from django.http.response import JsonResponse, HttpResponseNotAllowed,\
    HttpResponseForbidden
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt

from wechange_payments.backends import get_backend
from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT

import logging
from wechange_payments.models import Subscription
from wechange_payments.payment import create_subscription_for_payment
from django.shortcuts import redirect
from django.urls.base import reverse

logger = logging.getLogger('wechange-payments')


@csrf_exempt
def make_payment(request, on_success_func=None):
    """ A non-user-based payment API function, that can be used for anonymous (or user-based),
        one-time donations. """
    
    if not request.method=='POST':
        return HttpResponseNotAllowed(['POST'])
    
    backend = get_backend()
    params = request.POST.copy()
    user = request.user if request.user.is_authenticated else None
    
    payment_type = params.get('payment_type', None)
    error = 'Payment Type "%s" is not supported!' % payment_type 
    if payment_type in settings.PAYMENTS_ACCEPTED_PAYMENT_METHODS:
        # check for complete parameter set
        missing_params = backend.check_missing_params(params, payment_type)
        if missing_params:
            return JsonResponse({'error': _('Please fill out all of the missing fields!'), 'missing_parameters': missing_params}, status=500)
        if payment_type == PAYMENT_TYPE_DIRECT_DEBIT:
            payment, error = backend.make_sepa_payment(request, params, user=user)
            if payment is not None and on_success_func is not None:
                try:
                    ret = on_success_func(payment)
                except Exception as e:
                    logger.error('Payments: Critical! A user made a successful payment, but there was an error while creating his subscription! Find out what happened, create a subscription for them, and contact them!',
                         extra={'payment-id': payment.id, 'payment': payment, 'user': payment.user, 'exception': e})
                    # redirect to the success view with errors this point, so the user doesn't just resubmit the form
                    return redirect(reverse('wechange_payments:payment-success', kwargs={'payment_id': payment.id}) + '?subscription_error=1')
                return ret
    
    if payment is None:
        # special error cases:
        # 126: Invalid bank info
        if payment_type == PAYMENT_TYPE_DIRECT_DEBIT and error.endswith('(126)'):
            return JsonResponse({'error': _('The entered payment information is invalid. Please make sure you entered everything correctly!'), 'missing_parameters': ['iban', 'bic']}, status=500)
        return JsonResponse({'error': error}, status=500)
    
    data = {}
    if 'redirect_to' in payment.extra_data:
        data.update({
            'redirect_to': payment.extra_data['redirect_to']
        })
    return JsonResponse(data)



def make_subscription_payment(request):
    """ A user-based view, that is used only by the plattform itself, used to make the 
        first payment for the start of a subscription. Will not allow making a payment 
        while another subscription is still active! """
    if not request.method=='POST':
        return HttpResponseNotAllowed(['POST'])
    if not request.user.is_authenticated:
        return HttpResponseForbidden('You must be logged in to do that!')
    
    # if the user has an existing active sub, deny this payment (cancelled active subs are ok!)
    active_sub = Subscription.get_active_for_user(request.user)
    if active_sub and active_sub.state != Subscription.STATE_1_CANCELLED_BUT_ACTIVE:
        return JsonResponse({'error': _('You already have an active subscription and cannot start another one!')}, status=500)
    
    # use the regular payment method and create a subscription if it was successful
    def on_success_func(payment):
        create_subscription_for_payment(payment)
        return redirect(reverse('wechange_payments:payment-success', kwargs={'payment_id': payment.id}))
    
    return make_payment(request, on_success_func=on_success_func)
    

def postback_endpoint(request):
    """ For providers that offer a postback URL as logging/validation """
    
    backend = get_backend()
    backend.handle_postback(request, request.POST.copy())
    return JsonResponse({'status': 'ok'})
