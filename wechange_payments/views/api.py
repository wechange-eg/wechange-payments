# -*- coding: utf-8 -*-

from django.http.response import JsonResponse, HttpResponseNotAllowed,\
    HttpResponseForbidden, HttpResponseNotFound
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt

from wechange_payments.backends import get_backend
from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT,\
    PAYMENT_TYPE_CREDIT_CARD, PAYMENT_TYPE_PAYPAL,\
    INSTANT_SUBSCRIPTION_PAYMENT_TYPES

import logging
from wechange_payments.models import Subscription,\
    USERPROFILE_SETTING_POPUP_CLOSED, USERPROFILE_SETTING_POPUP_CLOSED_TIMES
from wechange_payments.payment import change_subscription_amount
from django.shortcuts import redirect
from django.urls.base import reverse
from cosinnus.utils.functions import is_number
from django.contrib import messages
from django.utils.timezone import now
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from wechange_payments.forms import PaymentsForm

logger = logging.getLogger('wechange-payments')


@csrf_exempt
@never_cache
@sensitive_post_parameters('iban', 'bic', 'account_holder')
def make_payment(request, on_success_func=None, make_postponed=False):
    """ A non-user-based payment API function, that can be used for anonymous (or user-based),
        one-time donations.
        
        @param on_success_func: The function that should be called on success, or None.
            In case we use a payment method that uses a vendor-step, we will get a postback
            for a success, so we don't need a success function here in that case.
        @param make_postponed: If True, make a call that only authorizes the payment, but does
            not yet process it. """
    
    if not request.method=='POST':
        return HttpResponseNotAllowed(['POST'])
    if settings.PAYMENTS_SOFT_DISABLE_PAYMENTS:
        return HttpResponseForbidden('Making payments is currently disabled!')
    
    backend = get_backend()
    params = request.POST.copy()
    user = request.user if request.user.is_authenticated else None
    
    # validate amount
    amount_or_error_response = _get_validated_amount(params['amount'])
    if isinstance(amount_or_error_response, JsonResponse):
        return amount_or_error_response
    amount = amount_or_error_response

    # validate debit period
    debit_period_or_error_response = _get_validated_debit_period(params['debit_period'])
    if isinstance(debit_period_or_error_response, JsonResponse):
        return debit_period_or_error_response
    debit_period = debit_period_or_error_response

    # compute debit amount from monthly amount and debit_period and validate
    debit_amount_or_error_response = _get_validated_debit_amount(amount, debit_period)
    if isinstance(debit_amount_or_error_response, JsonResponse):
        return debit_amount_or_error_response
    params['debit_amount'] = debit_amount_or_error_response

    payment_type = params.get('payment_type', None)
    error = 'Payment Type "%s" is not supported!' % payment_type 
    if payment_type in settings.PAYMENTS_ACCEPTED_PAYMENT_METHODS:
        # check for valid form
        form = PaymentsForm(request.POST)
        if not payment_type == PAYMENT_TYPE_DIRECT_DEBIT:
            for field_name in ['iban', 'bic', 'account_holder']:
                # remove the SEPA fields for any other payment method so validation won't interfere
                del form.fields[field_name]
        if not form.is_valid():
            return JsonResponse({'error': _('Please correct the errors in the highlighted fields!'), 'field_errors': form.errors}, status=500)

        # get cleaned compact IBAN and BIC out of custom form cleaning
        if payment_type == PAYMENT_TYPE_DIRECT_DEBIT:
            params['iban'] = form.cleaned_data['iban']
            params['bic'] = form.cleaned_data['bic']
                
        # remove `organisation` from params if `is_organisation` was not checked
        if not params.get('is_organisation', False) and 'organisation' in params:
            del params['organisation']
            
        # check for complete parameter set
        missing_params = backend.check_missing_params(params, payment_type)
        if missing_params:
            return JsonResponse({'error': _('Please fill out all of the missing fields!'), 'missing_parameters': missing_params}, status=500)
        
        # safety catch: if we don't have the postponed flag (i.e. we are not voluntarily updating
        # the current payment with a new one), and we have an active subscription, block the payment
        if Subscription.get_active_for_user(user) and not make_postponed:
            return JsonResponse({'error': _('You currently already have an active subscription!')}, status=500)
        
        # if postponed waiting payments are not implemented, we just make a non-postponed payment
        # which will replace the current one
        if not settings.PAYMENTS_POSTPONED_PAYMENTS_IMPLEMENTED:
            make_postponed = False
        
        if payment_type == PAYMENT_TYPE_DIRECT_DEBIT:
            payment, error = backend.make_sepa_payment(params, user=user, make_postponed=make_postponed)
        elif payment_type == PAYMENT_TYPE_CREDIT_CARD:
            payment, error = backend.make_creditcard_payment(params, user=user, make_postponed=make_postponed)
        elif payment_type == PAYMENT_TYPE_PAYPAL:
            payment, error = backend.make_paypal_payment(params, user=user, make_postponed=make_postponed)
            
        if payment is not None and on_success_func is not None:
            return on_success_func(payment)
            
    if payment is None:
        # special error cases:
        # 126: Invalid bank info
        if payment_type == PAYMENT_TYPE_DIRECT_DEBIT and error.endswith('(126)'):
            return JsonResponse({'error': _('The entered payment information is invalid. Please make sure you entered everything correctly!'), 'missing_parameters': ['iban', 'bic']}, status=500)
        return JsonResponse({'error': error}, status=500)
    
    data = {}
    if 'redirect_to' in payment.extra_data:
        data.update({
            'redirect_to': payment.extra_data['redirect_to'],
            'redirect_in_popup': True,
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
    if settings.PAYMENTS_SOFT_DISABLE_PAYMENTS:
        return HttpResponseForbidden('Making payments is currently disabled!')
    
    update_payment = request.POST.get('update_payment', '0')
    update_payment = update_payment == '1'
    
    active_sub = Subscription.get_active_for_user(request.user)
    waiting_sub = Subscription.get_waiting_for_user(request.user)
    cancelled_sub = Subscription.get_canceled_for_user(request.user)
    
    # gatecheck: if the user has an existing active or waiting sub, and is not on the "update payment" page,
    # deny this payment (cancelled active subs are ok!)
    if not update_payment and (active_sub or waiting_sub):
        return JsonResponse({'error': _('You already have an active subscription and cannot start another one!')}, status=500)
    # gatecheck: if the user is calling an "update payment" call, and has no active or waiting subscription, deny that too
    if update_payment and not (active_sub or waiting_sub):
        return JsonResponse({'error': _('You do not currently have an active subscription you could update!')}, status=500)
        
    # if the user has an active, or a cancelled, but still active sub, or a waiting sub that has not 
    # been activated yet, we make special postponed payment that 
    # only saves the account data with the payment provider, but does not actually 
    # transfer any money yet. money will be transfered with the next subscription due date
    make_postponed = bool(active_sub or cancelled_sub)
    # if for some reason, there is ONLY a waiting sub, we will delete that later
    
    params = request.POST.copy()
    payment_type = params.get('payment_type', None)
    if payment_type in INSTANT_SUBSCRIPTION_PAYMENT_TYPES:
        # use the regular payment method and create a subscription if it was successful
        def on_success_func(payment):
            try:
                if payment.type == PAYMENT_TYPE_DIRECT_DEBIT and settings.PAYMENTS_SEPA_IS_INSTANTLY_SUCCESSFUL:
                    redirect_url = reverse('wechange_payments:payment-success', kwargs={'pk': payment.id})
                else:
                    redirect_url = reverse('wechange_payments:payment-process', kwargs={'pk': payment.id})
                data = {
                    'redirect_to': redirect_url
                }
            except:
                # exception logging happens inside create_subscription_for_payment!
                if settings.DEBUG:
                    raise
                # redirect to the success view with errors this point, so the user doesn't just resubmit the form
                redirect_url = reverse('wechange_payments:payment-success', kwargs={'pk': payment.id}) + '?subscription_error=1'
                data = {
                    'redirect_to': redirect_url
                }
            
            return JsonResponse(data)
    else:
        # use the regular payment method and redirect to a site the vendor provides
        on_success_func = None
        
    return make_payment(request, on_success_func=on_success_func, make_postponed=make_postponed)


def subscription_change_amount(request):
    """ A user-based view, that is used only by the plattform itself, used to make the 
        first payment for the start of a subscription. Will not allow making a payment 
        while another subscription is still active! """
    if not request.method=='POST':
        return HttpResponseNotAllowed(['POST'])
    if not request.user.is_authenticated:
        return HttpResponseForbidden('You must be logged in to do that!')
    if settings.PAYMENTS_SOFT_DISABLE_PAYMENTS:
        return HttpResponseForbidden('Making payments is currently disabled!')
    
    # if the user has no active or waiting sub, we cannot change the amount of it
    active_sub = Subscription.get_active_for_user(request.user)
    waiting_sub = Subscription.get_waiting_for_user(request.user)
    if not active_sub and not waiting_sub:
        return JsonResponse({'error': _('You do not currently have a subscription!')}, status=500)
    
    # sanity check
    if active_sub and waiting_sub:
        logger.error('Critical: Sanity check for user subscription failed! User has both an active and a queued subscription!', extra={'user': request.user.email})
        return JsonResponse({'error': _('An error occured, and you cannot change your subscription amount at this time. Please contact our support!')}, status=500)
    
    # validate amount
    amount_or_error_response = _get_validated_amount(request.POST.get('amount', None))
    if isinstance(amount_or_error_response, JsonResponse):
        return amount_or_error_response
    amount = amount_or_error_response

    # validate debit period
    debit_period_or_error_response = _get_validated_debit_period(request.POST.get('debit_period', None))
    if isinstance(debit_period_or_error_response, JsonResponse):
        return debit_period_or_error_response
    debit_period = debit_period_or_error_response

    subscription = active_sub or waiting_sub
    amount_changed = subscription.amount != amount
    debit_period_changed = subscription.debit_period != debit_period
    if not amount_changed and not debit_period_changed:
        messages.success(
            request,
            _('The amount and debiting period you selected were the same as before, so we did not change anything!')
        )
    else:
        success = change_subscription_amount(subscription, amount, debit_period)
        if not success:
            return JsonResponse({'error': _('Your subscription amount or debit poriod could not be changed because of an unexpected error. Please contact our support!')}, status=500)
        change_message = _('Your changes have been saved! ')
        if amount_changed and debit_period_changed:
            change_message += _('Starting with the next payment your new debiting period and new amount will be used. ')
        elif amount_changed:
            change_message += _('From now on your new chosen contribution amount will be paid. ')
        else:  # debit_period_changed
            change_message += _('Starting with the next payment your new debiting period will be used. ')
        change_message += _('Thank you very much for your support!')
        messages.success(request, change_message)
    
    redirect_url = reverse('wechange_payments:my-subscription')
    data = {
        'redirect_to': redirect_url
    }
    return JsonResponse(data)


def _get_validated_amount(amount):
    """ Validates if a given amount is valid for payment (is a number, and in limits).
        @return: The float amount if valid, a JsonResponse with an error otherwise. """
    
    if not is_number(amount):
        return JsonResponse({'error': _('The amount submitted does not seem to be a number!')}, status=500)
    amount = float(amount)
    
    # check min/max of monthly payment amounts
    if amount > settings.PAYMENTS_MAXIMUM_ALLOWED_MONTHLY_AMOUNT:
        return JsonResponse({'error': _('The monthly amount is higher than the allowed maximum amount!')}, status=500)
    if amount < settings.PAYMENTS_MINIMUM_ALLOWED_MONTHLY_AMOUNT:
        return JsonResponse({'error': _('The monthly amount is lower than the allowed minimum amount!')}, status=500)
    return amount


def _get_validated_debit_period(debit_period):
    """ Validates if a given debit_period is a valid choice.
        @return: The debit_period choice if valid, a JsonResponse with an error otherwise. """
    if not debit_period:
        return JsonResponse({'error': 'The debiting period is not set!'}, status=500)
    if debit_period not in Subscription.DEBIT_PERIODS:
        return JsonResponse({'error': 'The debiting period choice is not valid!'}, status=500)
    return debit_period

def _get_validated_debit_amount(amount, debit_period):
    """ Validates the payment amount computed from the monthly amount and debit period.
        @return: The debit_amount if valid, a JsonResponse with an error otherwise. """
    debit_amount = amount * Subscription.DEBIT_PERIOD_MONTHS[debit_period]

    # check min/max payment amounts
    if debit_amount > settings.PAYMENTS_MAXIMUM_ALLOWED_PAYMENT_AMOUNT:
        return JsonResponse({'error': _('The payment amount is higher than the allowed maximum amount!')}, status=500)
    if debit_amount < settings.PAYMENTS_MINIMUM_ALLOWED_PAYMENT_AMOUNT:
        return JsonResponse({'error': _('The payment amount is lower than the allowed minimum amount!')}, status=500)
    return debit_amount


def success_endpoint(request):
    """ For providers with payment flows that redirect back to our site after a success """
    backend = get_backend()
    valid_payment = backend.handle_success_redirect(request, request.GET.dict())
    if valid_payment:
        return redirect(reverse('wechange-payments:payment-process', kwargs={'pk': valid_payment.pk}))
    messages.warning(request, str(_('The payment session could not be found.')) + ' ' + str(_('Please contact our support for assistance!')))
    return redirect('wechange-payments:overview')


def error_endpoint(request):
    """ For providers with payment flows that redirect back to our site after an error """
    backend = get_backend()
    valid_error_target = backend.handle_error_redirect(request, request.GET.dict())
    if valid_error_target:
        messages.error(request, str(_('The payment process was cancelled or could not be completed.')) + ' ' + str(_('Please try again or contact our support for assistance!')))
    else:
        messages.error(request, str(_('This payment session has expired.')) + ' ' + str(_('Please try again or contact our support for assistance!')))
    return redirect('wechange-payments:overview')

@csrf_exempt
@never_cache
def postback_endpoint(request):
    """ For providers that offer a postback URL as logging/validation """
    backend = get_backend()
    success = backend.handle_postback(request, request.POST.dict())
    if not success:
        return HttpResponseNotFound() 
    return JsonResponse({'status': 'ok'})


def snooze_popup(request):
    """ Sets the user profile settings `USERPROFILE_SETTING_POPUP_CLOSED` to now. """
    if not request.method=='POST':
        return HttpResponseNotAllowed(['POST'])
    if not request.user.is_authenticated:
        return HttpResponseForbidden('You must be logged in to do that!')
    try:
        profile = request.user.cosinnus_profile
        profile.settings[USERPROFILE_SETTING_POPUP_CLOSED] = now()
        profile.settings[USERPROFILE_SETTING_POPUP_CLOSED_TIMES] = profile.settings.get(USERPROFILE_SETTING_POPUP_CLOSED_TIMES, 0) + 1
        profile.save(update_fields=['settings'])
    except Exception as e:
        logger.error('Error in `api.snooze_popup`: %s' % e, extra={'exception': e})
    return JsonResponse({'status': 'ok'})
