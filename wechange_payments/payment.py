# -*- coding: utf-8 -*-

from wechange_payments.conf import settings
from django.utils.timezone import now

import logging
from wechange_payments.models import Subscription
from wechange_payments.backends import get_backend

logger = logging.getLogger('wechange-payments')


def create_subscription_for_payment(payment):
    """ Creates the subscription object for a user after the initial payment 
        for the subscription has completed successfully. """
        
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
    # if we have an active cancelled subscription, use its next due date as date for the new sub
    if active_sub:
        subscription.next_due_date = active_sub.next_due_date
        subscription.state = Subscription.STATE_3_WATING_TO_BECOME_ACTIVE
    else:
        subscription.set_next_due_date(now().date())
        subscription.state = Subscription.STATE_2_ACTIVE
    
    subscription.save()
    
    payment.subscription = subscription
    payment.save()
    
    logger.info('Payments: Successfully created a new subscription for a user.',
                extra={'payment-id': payment.id, 'payment': payment, 'user': payment.user})

    return subscription


def process_due_subscription_payments():
    """ Main loop for subscription management. Checks all subscriptions for
        validity, terminates expired subscriptions, activates waiting subscriptions
        and triggers payments on active subscriptions where a payment is due. """
    # TODO: add portal-specific subscriptions?
    # check for terminating subs, and activate valid waiting subs, afterwards all active subs will be valid 
    for ending_sub in Subscription.objects.filter(state=Subscription.STATE_1_CANCELLED_BUT_ACTIVE):
        try:
            ending_sub.validate_state_and_cycle()
        except Exception as e:
            logger.error('Payments: Exception during the call validate_state_and_cycle on a subscription! This is critical and needs to be fixed!', 
                         extra={'user': ending_sub.user, 'subscription': ending_sub, 'exception': e})
            if settings.DEBUG:
                raise
            
    # if an active subscription has its payment is due trigger a new payment on it
    for active_sub in Subscription.objects.filter(state=Subscription.STATE_2_ACTIVE):
        logger.warn('REMOVEME: Checking sub for renewability')
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
    # check due date has passed 
    if not subscription.check_payment_due():
        return 
    
    # book a new payment
    backend = get_backend()
    payment, error = backend.make_recurring_payment(subscription.reference_payment)
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
    


