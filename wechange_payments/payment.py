# -*- coding: utf-8 -*-

from wechange_payments.conf import settings
from django.utils.timezone import now

import logging
from wechange_payments.models import Subscription, Payment
from wechange_payments.backends import get_backend

logger = logging.getLogger('wechange-payments')


def create_subscription_for_payment(payment):
    """ Creates the subscription object for a user after the initial payment 
        for the subscription has completed successfully. 
        
        This handles all cancellations of current or waiting subscriptions, depending 
        on the states of the existing subscriptions. All entry API functions are safely
        gate-kept, so we can assume here that this was well-checked for states.
        I.e. if this call comes to pass, and the user has an active subscription, 
        they must have called update_payment, so cancel the current subscription,
        and create a new, postponed one.
    """
        
    # if the user has an existing active sub, we will not create a second subscription
    # this case should never happen, as sanity checks on payments should prevent it!
    # (cancelled active subs are ok!)
    active_sub = Subscription.get_current_for_user(payment.user)
    if active_sub and active_sub.state != Subscription.STATE_1_CANCELLED_BUT_ACTIVE:
        logger.error('Payments: CRITICAL! create_subscription_for_payment() was called after a payment, but there is already an active payment for this user! You need to take action and make sure the payment will result in a proper subscription, or refund the user!', 
                        extra={'payment-id': payment.id, 'payment': payment, 'active-subscription-id': active_sub.id, 'active-subscription': active_sub, 'user': payment.user})
        return
    
    subscription = Subscription(
        user=payment.user,
        reference_payment=payment,
        amount=payment.amount,
        last_payment=payment,
    )
    # TODO cases: 
    #     A: no subs at all: 
    #            create new sub with state 2
    #     B: active sub (state 2), none other: 
    #            set active sub to state 1, create new with state 3
    #     C: canceled sub (state 1), none other:
    #            leave sub canceled, create new with state 3
    #     D: canceled sub (state 1), waiting sub (state 3):
    #            leave sub canceled, "delete" waiting sub
    #            by setting to 0, create new sub with state 3
    #     E: only waiting sub (state 3), no others:
    #            delete waiting sub by setting it to 0, then case A
    #     X: All other cases should not happen and need to be logged 
    #        with a critical error, so we can check out the case manually!
    
    
    # if we have an active cancelled subscription, use its next due date as date for the new sub
    if active_sub:
        # important! set the waiting sub's due date correctly to that of the current one!
        subscription.next_due_date = active_sub.next_due_date 
        subscription.state = Subscription.STATE_3_WATING_TO_BECOME_ACTIVE
    else:
        subscription.set_next_due_date(now().date())
        subscription.state = Subscription.STATE_2_ACTIVE
    
    subscription.save()
    
    # todo: if we just instated a waiting sub during an active one, set the current
    # active one's state to 1!
    
    payment.subscription = subscription
    payment.save()
    
    logger.info('Payments: Successfully created a new subscription for a user.',
                extra={'payment-id': payment.id, 'payment': payment, 'user': payment.user})

    return subscription


def process_due_subscription_payments():
    """ Main loop for subscription management. Checks all subscriptions for
        validity, terminates expired subscriptions, activates waiting subscriptions
        and triggers payments on active subscriptions where a payment is due. """
        
    # check for terminating subs, and activate valid waiting subs, afterwards all active subs will be valid 
    for ending_sub in Subscription.objects.filter(state=Subscription.STATE_1_CANCELLED_BUT_ACTIVE):
        try:
            ending_sub.validate_state_and_cycle()
        except Exception as e:
            logger.error('Payments: Exception during the call validate_state_and_cycle on a subscription! This is critical and needs to be fixed!', 
                         extra={'user': ending_sub.user, 'subscription': ending_sub, 'exception': e})
            if settings.DEBUG:
                raise
    
    # for each waiting sub, check to see if the user has neither an active or canceled sub 
    # (i.e. their canceled sub was just terminated)
    for waiting_sub in Subscription.objects.filter(state=Subscription.STATE_3_WATING_TO_BECOME_ACTIVE):
        active_or_canceled_sub = Subscription.get_current_for_user(waiting_sub.user)
        if not active_or_canceled_sub:
            # if there were no active subs, activate the waiting sub. its due date should have
            # been set to the last sub at creation time.
            waiting_sub.state = Subscription.STATE_2_ACTIVE
            waiting_sub.save()
            logger.warn('REMOVEME: Done activated a waiting sub after terminating an old expired sub!')

    # if an active subscription has its payment is due trigger a new payment on it
    for active_sub in Subscription.objects.filter(state=Subscription.STATE_2_ACTIVE):
        logger.warn('REMOVEME: Checking sub for renewability')
        # Note: this will cash in both regular active subs and just-now-activated-waiting-subs
        if active_sub.check_payment_due() and active_sub.user.is_active:
            try:
                logger.warn('REMOVEME: Starting sub recurrent payment')
                book_next_subscription_payment(active_sub)
                logger.warn('REMOVEME: Finished sub recurrent payment')
            except Exception as e:
                logger.error('Payments: Exception while trying to book the next subscruption payment for a due subscription!', 
                         extra={'user': active_sub.user, 'subscription': active_sub, 'exception': e})
                if settings.DEBUG:
                    raise
    

def book_next_subscription_payment(subscription):
    """ Will create and book a new payment (using the reference payment as target) 
        for the current `amount` of money.
        Afterwards, will set the next due date for this subscription. """
    # check due date has passed and state is active!
    if not subscription.check_payment_due() or not subscription.state == Subscription.STATE_2_ACTIVE:
        logger.error('Payments: Prevented a call to a subscription payment on an inactive or not due subscription!', 
                         extra={'user': subscription.user, 'subscription': subscription})
        return 
    
    backend = get_backend()
    reference_payment = subscription.reference_payment
    
    # make a cash-in call on a preauthorized payment, or a recurring call on a previously cashed payment 
    if reference_payment.is_postponed_payment and reference_payment.status == Payment.STATUS_PREAUTHORIZED_UNPAID:
        # cash in a pre-authorized payment
        payment, error = backend.cash_in_postponed_payment(reference_payment)
    elif (reference_payment.is_postponed_payment and reference_payment.status == Payment.STATUS_PAID) or not reference_payment.is_postponed_payment:
        # book a new recurring payment
        payment, error = backend.make_recurring_payment(reference_payment)
    else:
        logger.error('Payments: Did not know how to make a further payment from a reference payment due to incompatible payment states!', 
                         extra={'user': subscription.user, 'subscription': subscription})
        return
    
    if error or not payment:
        logger.error('Payments: Trying to make the next subscription payment returned an error (from our backend or provider backend)', 
                         extra={'user': subscription.user, 'subscription': subscription, 'error_message': error})
    
    # advance subscription due date and save payment to subscription
    subscription.set_next_due_date(subscription.next_due_date)
    subscription.last_payment = payment
    subscription.save()
    payment.subscription = subscription
    payment.save()
    logger.info('Payments: Advanced the due_date of a subscription and saved it after a payment was made. ', 
        extra={'user': subscription.user, 'subscription': subscription})
    logger.warn('REMOVEME: Done new sub payment')
    return payment


def cancel_subscription(user):
    """ Cancels the currently active or waiting subscription for a user """
    subscription = Subscription.get_current_for_user(user)
    subscription.state = Subscription.STATE_1_CANCELLED_BUT_ACTIVE
    subscription.cancelled = now()
    subscription.save()
    # TODO: send email!
    return True
    

def change_subscription_amount(subscription, amount):
    """ Ends the currently active or waiting subscription for a user """
    # check min/max payment amounts
    if amount > settings.PAYMENTS_MAXIMUM_ALLOWED_PAYMENT_AMOUNT or \
            amount < settings.PAYMENTS_MINIMUM_ALLOWED_PAYMENT_AMOUNT:
        return False
    subscription.amount = amount
    subscription.save()
    # TODO: send email!
    return True
    


