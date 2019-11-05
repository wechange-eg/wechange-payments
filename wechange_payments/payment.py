# -*- coding: utf-8 -*-

from wechange_payments.conf import settings
from django.db import transaction
from django.utils.timezone import now

import logging
from wechange_payments.models import Subscription, Payment
from wechange_payments.backends import get_backend

logger = logging.getLogger('wechange-payments')


def create_subscription_for_payment(payment):
    """ Creates the subscription object for a user after the initial payment 
        for the subscription has completed successfully. 
        
        This handles all state changes of current or waiting subscriptions, depending 
        on the states of the existing subscriptions. All entry API functions are safely
        gate-kept, so we can assume here that this was well-checked for states.
        I.e. if this call comes to pass, and the user may create a new subscription.
        Should they have an active subscription, they must have called update_payment, 
        so cancel the current subscription, and create a new, waiting one (in that
        case the payment will have been made to be postponed).
    """
    
    try:
        user = payment.user
        active_sub = Subscription.get_active_for_user(user)
        waiting_sub = Subscription.get_waiting_for_user(user)
        cancelled_sub = Subscription.get_canceled_for_user(user)
        suspended_sub = Subscription.get_suspended_for_user(user)
        
        subscription = Subscription(
            user=payment.user,
            reference_payment=payment,
            amount=payment.amount,
            last_payment=payment,
        )
        
        # the numbers refer to the state-change cases in `Subscription`'s docstring!
        with transaction.atomic():
            
            # terminate any failed suspended subscriptions
            if suspended_sub:
                suspended_sub.state = Subscription.STATE_0_TERMINATED
                suspended_sub.terminated = now()
                suspended_sub.save()
            
            if not active_sub and not waiting_sub and not cancelled_sub:
                # 1. (new subscription)
                subscription.set_next_due_date(now().date())
                subscription.state = Subscription.STATE_2_ACTIVE
            elif active_sub and not waiting_sub and not cancelled_sub: 
                # 2. (updated payment infos, becomes active next due date)
                subscription.next_due_date = active_sub.next_due_date 
                subscription.state = Subscription.STATE_3_WATING_TO_BECOME_ACTIVE
                active_sub.state = Subscription.STATE_1_CANCELLED_BUT_ACTIVE
                active_sub.cancelled = now()
                active_sub.save()
            elif not active_sub and not waiting_sub and cancelled_sub:
                # 3. (canceled Subscriptions, created new subscription before next payment due)
                subscription.next_due_date = cancelled_sub.next_due_date 
                subscription.state = Subscription.STATE_3_WATING_TO_BECOME_ACTIVE
            elif not active_sub and waiting_sub:
                # 4. and 5. (updated payment infos again, 
                # or replaced a waiting subscription before it became active)
                # this may mean there is currently a cancelled sub, but we leave that alone here
                subscription.next_due_date = waiting_sub.next_due_date
                subscription.state = Subscription.STATE_3_WATING_TO_BECOME_ACTIVE
                waiting_sub.state = Subscription.STATE_0_TERMINATED
                waiting_sub.terminated = now()
                waiting_sub.save()
            else:
                logger.critical('Payments: "Unreachable" case reached for subscription state situation for a user! Could not save the user\'s new subscription! This has to be checked out manually!.',
                    extra={'payment-id': payment.id, 'payment': payment, 'user': user})
            
            subscription.save()
            
            payment.subscription = subscription
            payment.save()
            
            logger.info('Payments: Successfully created a new subscription for a user.',
                        extra={'payment-id': payment.id, 'payment': payment, 'user': user})
    except Exception as e:
        logger.error('Payments: Critical! A user made a successful payment, but there was an error while creating his subscription! Find out what happened, create a subscription for them, and contact them!',
            extra={'payment-id': payment.id, 'payment': payment, 'user': payment.user, 'exception': e})
        raise
    
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
    


