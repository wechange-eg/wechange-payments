# -*- coding: utf-8 -*-

from django.http.response import JsonResponse, HttpResponseNotAllowed,\
    HttpResponseForbidden
from django.utils.translation import ugettext_lazy as _
from django.views.decorators.csrf import csrf_exempt

from wechange_payments.backends import get_backend
from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT

import logging
from wechange_payments.models import Subscription
from wechange_payments.payment import create_subscription_for_payment,\
    change_subscription_amount
from django.shortcuts import redirect
from django.urls.base import reverse
from cosinnus.utils.functions import is_number
from django.contrib import messages

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
    
    # validate amount
    amount_or_error_response = _get_validated_amount(params['amount'])
    if isinstance(amount_or_error_response, JsonResponse):
        return amount_or_error_response
    
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
                    if settings.DEBUG:
                        raise
                    # redirect to the success view with errors this point, so the user doesn't just resubmit the form
                    redirect_url = reverse('wechange_payments:payment-success', kwargs={'pk': payment.id}) + '?subscription_error=1'
                    data = {
                        'redirect_to': redirect_url
                    }
                    return JsonResponse(data)
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
    
    # if the user has an existing active or waiting sub, deny this payment (cancelled active subs are ok!)
    active_sub = Subscription.get_active_for_user(request.user)
    waiting_sub = Subscription.get_waiting_for_user(request.user)
    if active_sub or waiting_sub:
        return JsonResponse({'error': _('You already have an active subscription and cannot start another one!')}, status=500)
    
    # if the user has a cancelled, but still active sub, we make special payment that
    # only saves the account data with the payment provider, but does not actually 
    # transfer any money yet. money will be transfered with the next subscription due date
    cancelled_sub = Subscription.get_current_for_user(request.user)
    if cancelled_sub:
        # sanity check that we are really dealing with a cancelled sub
        if not cancelled_sub.state == Subscription.STATE_1_CANCELLED_BUT_ACTIVE:
            logger.error('Critical: User seemed to have a cancelled sub, but sanity check on it failed when trying to make a waiting subscription!', 
                         extra={'user': request.user.email})
            return JsonResponse({'error': _('We can not create a new subscription for you at this point. Please contact the support! No payment has been made yet.')}, status=500)
        # TODO: implement postponed subscription payment!
        return JsonResponse({'error': 'NYI: Postponed subscription creation is not yet implemented!'}, status=500)
    
    # use the regular payment method and create a subscription if it was successful
    def on_success_func(payment):
        create_subscription_for_payment(payment)
        redirect_url = reverse('wechange_payments:payment-success', kwargs={'pk': payment.id})
        data = {
            'redirect_to': redirect_url
        }
        return JsonResponse(data)
    
    return make_payment(request, on_success_func=on_success_func)


def subscription_change_amount(request):
    """ A user-based view, that is used only by the plattform itself, used to make the 
        first payment for the start of a subscription. Will not allow making a payment 
        while another subscription is still active! """
    if not request.method=='POST':
        return HttpResponseNotAllowed(['POST'])
    if not request.user.is_authenticated:
        return HttpResponseForbidden('You must be logged in to do that!')
    
    # if the user has no active or waiting sub, we cannot change the amount of it
    active_sub = Subscription.get_active_for_user(request.user)
    waiting_sub = Subscription.get_waiting_for_user(request.user)
    if not active_sub and not waiting_sub:
        return JsonResponse({'error': _('You do not currently have a subscription!')}, status=500)
    
    # sanity check
    if active_sub and waiting_sub:
        logger.error('Critical: Sanity check for user subscription failed! User has both an active and a queued subscription!', extra={'user': request.user.email})
        return JsonResponse({'error': _('An error occured, and you cannot change your subscription amount at this time. Please contact the support!')}, status=500)
    
    # validate amount
    amount_or_error_response = _get_validated_amount(request.POST.get('amount', None))
    if isinstance(amount_or_error_response, JsonResponse):
        return amount_or_error_response
    amount = amount_or_error_response
    
    subscription = active_sub or waiting_sub
    success = change_subscription_amount(subscription, amount)
    
    if not success:
        return JsonResponse({'error': _('Your subscription amount could not be changed because of an unexpected error. Please contact the support!')}, status=500)
    
    redirect_url = reverse('wechange_payments:my-subscription')
    data = {
        'redirect_to': redirect_url
    }
    messages.success(request, _('(MSG3) Your new subscription amount was saved! Your future subscription payments will be made with this amount. Thank you for your support!'))
    return JsonResponse(data)


def _get_validated_amount(amount):
    """ Validates if a given amount is valid for payment (is a number, and in limits).
        @return: The float amount if valid, a JsonResponse with an error otherwise. """
    
    if not is_number(amount):
        return JsonResponse({'error': _('The amount submitted does not seem to be a number!')}, status=500)
    amount = float(amount)
    
    # check min/max payment amounts
    if amount > settings.PAYMENTS_MAXIMUM_ALLOWED_PAYMENT_AMOUNT:
        return JsonResponse({'error': _('The payment amount is higher than the allowed maximum amount!')}, status=500)
    if amount < settings.PAYMENTS_MINIMUM_ALLOWED_PAYMENT_AMOUNT:
        return JsonResponse({'error': _('The payment amount is lower than the allowed minimum amount!')}, status=500)
    return amount
    

def postback_endpoint(request):
    """ For providers that offer a postback URL as logging/validation """
    
    backend = get_backend()
    backend.handle_postback(request, request.POST.copy())
    return JsonResponse({'status': 'ok'})
