# -*- coding: utf-8 -*-

from wechange_payments.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.utils.timezone import now
from annoying.functions import get_object_or_None

import logging
from wechange_payments.models import Subscription

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
            
    # if an active subscription has its payment is due trigger a new payment on it
    for active_sub in Subscription.objects.filter(state=Subscription.STATE_2_ACTIVE):
        if active_sub.check_payment_due() and active_sub.user.is_active:
            active_sub.book_next_payment()


def terminate_subscription(user):
    """ Ends the currently active or waiting subscription for a user """
    subscription = Subscription.get_current_for_user(user)
    subscription.state = Subscription.STATE_0_TERMINATED
    subscription.terminated = now()
    subscription.save()
    # TODO: send email!
    return True
    


