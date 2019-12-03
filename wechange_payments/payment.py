# -*- coding: utf-8 -*-

from wechange_payments.conf import settings
from django.db import transaction
from django.utils.timezone import now

import logging
from wechange_payments.models import Subscription, Payment
from wechange_payments.backends import get_backend
from datetime import timedelta
from wechange_payments.mails import PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED,\
    PAYMENT_EVENT_NEW_REPLACEMENT_SUBSCRIPTION_CREATED,\
    send_payment_event_payment_email, PAYMENT_EVENT_SUCCESSFUL_PAYMENT,\
    PAYMENT_EVENT_SUBSCRIPTION_AMOUNT_CHANGED,\
    PAYMENT_EVENT_SUBSCRIPTION_TERMINATED, PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED
from wechange_payments.utils.utils import send_admin_mail_notification

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
            
            mail_event = None
            # terminate any failed suspended subscriptions
            if suspended_sub:
                suspended_sub.state = Subscription.STATE_0_TERMINATED
                suspended_sub.terminated = now()
                suspended_sub.save()
            
            if not active_sub and not cancelled_sub:
                # 1. (new subscription)
                subscription.set_next_due_date(now().date())
                subscription.state = Subscription.STATE_2_ACTIVE
                mail_event = PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED
            elif active_sub or cancelled_sub: 
                # 2 and 3.. (updated payment infos, new sub becomes active sub, current one is terminated,
                #    remaining time is added to new sub)
                replaced_sub = active_sub or cancelled_sub
                subscription.set_next_due_date(replaced_sub.next_due_date)
                subscription.state = Subscription.STATE_2_ACTIVE
                replaced_sub.state = Subscription.STATE_0_TERMINATED
                replaced_sub.cancelled = now()
                replaced_sub.terminated = now()
                replaced_sub.save()
                mail_event = PAYMENT_EVENT_NEW_REPLACEMENT_SUBSCRIPTION_CREATED
                
            else:
                logger.critical('Payments: "Unreachable" case reached for subscription state situation for a user! Could not save the user\'s new subscription! This has to be checked out manually!.',
                    extra={'payment-id': payment.id, 'payment': payment, 'user': user})
            
            subscription.save()
            
            payment.subscription = subscription
            payment.save()
            
            if mail_event:
                send_payment_event_payment_email(payment, mail_event)
            
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
    
    # switch for not-implemented postponed subscriptions
    if settings.PAYMENTS_POSTPONED_PAYMENTS_IMPLEMENTED:
        # for each waiting sub, check to see if the user has neither an active or canceled sub 
        # (i.e. their canceled sub was just terminated)
        for waiting_sub in Subscription.objects.filter(state=Subscription.STATE_3_WAITING_TO_BECOME_ACTIVE):
            active_or_canceled_sub = Subscription.get_current_for_user(waiting_sub.user)
            if not active_or_canceled_sub:
                # if there were no active subs, activate the waiting sub. its due date should have
                # been set to the last sub at creation time.
                waiting_sub.state = Subscription.STATE_2_ACTIVE
                waiting_sub.save()

    # if an active subscription has its payment is due trigger a new payment on it
    for active_sub in Subscription.objects.filter(state=Subscription.STATE_2_ACTIVE):
        if active_sub.check_payment_due() and active_sub.user.is_active:
            try:
                if active_sub.has_pending_payment():
                    # if a  subscription's recurring payment is still pending, we do not book another payment
                    if active_sub.last_payment.last_action_at < (now() - timedelta(days=1)):
                        # but if the payment has been made over 1 day ago and is still due, we trigger a critical alert!
                        extra={'user': active_sub.user, 'subscription': active_sub, 'internal_transaction_id': str(active_sub.last_payment.internal_transaction_id)}
                        logger.critical('Payments: A recurring payment that has been started over 1 day ago still has its status at pending and has not received a postback! Only postbacks can set payments to not pending. The subscription is therefore also pending and is basically frozen. This needs to be investigated manually!', extra=extra)
                    continue
                book_next_subscription_payment(active_sub)
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
    if reference_payment.is_postponed_payment and settings.PAYMENTS_POSTPONED_PAYMENTS_IMPLEMENTED:
        if reference_payment.status == Payment.STATUS_PREAUTHORIZED_UNPAID:
            # cash in a pre-authorized payment
            payment, error = backend.cash_in_postponed_payment(reference_payment)
        elif reference_payment.status == Payment.STATUS_PAID:
            # book a new recurring payment
            payment, error = backend.make_recurring_payment(reference_payment, subscription)
        else:
            logger.error('Payments: Did not know how to make a further payment from a reference payment due to incompatible payment states!', 
                         extra={'user': subscription.user, 'subscription': subscription})
            return
    else:
        payment, error = backend.make_recurring_payment(reference_payment, subscription)

    
    if error or not payment:
        # TODO: TODO-ERROR-STATE: should we always retry when we get an error back instantly, or sometimes
        # even suspend the subscription here immediately, instead of only when a postback comes back as fail? 
        
        subscription.num_attempts_recurring += 1
        # the server might just be down, or some error could have occured that has nothing
        # to do with the actual payment. so we retry this 3 different times
        if subscription.num_attempts_recurring < 3:
            # we haven't retried 3 times, count up tries in the subscription  
            logger.error('Payments: (will retry) Trying to make the next subscription payment returned an error (from our backend or provider backend). Retrying next day.', 
                 extra={'user': subscription.user, 'subscription': subscription, 'error_message': error})
            subscription.has_problems = True
            subscription.save()
        else:
            # we have retried 3 times. appearently the problem is with the payment itself
            logger.error('Payments: (giving up) Trying to make the next subscription payment returned an error (from our backend or provider backend). Failed 3 times for this subscription and giving up.', 
                 extra={'user': subscription.user, 'subscription': subscription, 'error_message': error})
            # set the subscription to failed and email the user
            suspend_failed_subscription(subscription)
        
        return
    
    # reload subscription, was probably changed while handling the successful payment
    subscription.refresh_from_db()
    
    # clear subscription retry times on success
    subscription.has_problems = False
    subscription.num_attempts_recurring = 0
    
    subscription.last_payment = payment
    subscription.save()
    
    logger.info('Payments: Advanced the due_date of a subscription and saved it after a payment was made. ', 
        extra={'user': subscription.user, 'subscription': subscription})
    return payment


def handle_successful_payment(payment):
    """ Handles the actions after a successful payment was made,
        triggered either after an instantly successful payment or after  a postback was received.
        Either creates a new subscription or advances a current subscription's
        due_date for a recurring payment. """
    # trigger email sending, invoice generation, etc
    send_payment_event_payment_email(payment, PAYMENT_EVENT_SUCCESSFUL_PAYMENT)
    
    # process payment for subscription
    if payment.is_reference_payment:
        # if this is the first and thus reference payment, we trigger creating a new subscription
        create_subscription_for_payment(payment)
        logger.info('Payments: Successfully created a subscription for an initial payment from a postback.', 
                    extra={'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id})
    else:
        # advance the subscription due date for a recurring payment that was 
        # marked as successful by a postback
        subscription = payment.subscription
        if subscription:
            subscription.set_next_due_date(subscription.next_due_date) 
            subscription.save()
            logger.info('Payments: Successfully advanced the due date of a subscription after a recurring payment from a postback.', 
                        extra={'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id})
        else:
            logger.critical('Payments: Received a success postback for a previously unpaid recurring payment from a postback, but there was no subscription attached that we could advance the due date for! This needs to be investigated!', 
                            extra={'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id})
                    

def handle_payment_refunded(payment, status=None):
    """ Handles the case when we receive notification of a refunded payment.
        Since we have no automatism for this yet, we send out an email to the portal admins. """
    
    extra = {'betterpayment_status_code': str(status), 'internal_transaction_id': str(payment.internal_transaction_id), 'vendor_transaction_id': str(payment.vendor_transaction_id)}
    content = ('We received a Refund or Chargeback for a payment in the WECHANGE Geschäftsmodell.\n' +\
        '\n' +\
        'Since we have no automatic handling of this, we will need to manually handle this. This includes setting the user subscription to TERMINATED, and also putting the chargeback into our Billing System!\n' +\
        '\n' +\
        'Payment Details:\n' +\
        'betterpayment_status_code: %(betterpayment_status_code)s\n' +\
        'internal_transaction_id: %(internal_transaction_id)s\n' +\
        'vendor_transaction_id: %(vendor_transaction_id)s\n') % extra 
    send_admin_mail_notification('WECHANGE Payments: Received a Refund or chargeback!', content)
    logger.critical('NYI: Received a postback for a refund, but refunding logic not yet implemented! (A mail was also sent!', extra=extra)
    suspend_failed_subscription(payment.subscription, payment=payment)


def suspend_failed_subscription(subscription, payment=None):
    """ For various reasons, like failed payments to refunds pulled on a payment,
        this sets a subscription into a suspended "has problems and failed" state, where
        no further payments will be made from.
        The subscriptions cannot recover from this back into an active state, and the
        user will have to make a new subscription. 
        @param payment: If there is a payment that specifically failed the subscription, 
            for example from a refund, pass it here
        """
    if subscription.state in Subscription.ACTIVE_STATES:
        subscription.state = Subscription.STATE_99_FAILED_PAYMENTS_SUSPENDED
        subscription.has_problems = True
        if payment:
            subscription.last_payment = payment
        subscription.save()
        logger.info('Payments: Suspended a subscription for a user because of one or more failed payments',
            extra={'user': subscription.user.id, 'subscription_id': subscription.id})
        send_payment_event_payment_email(subscription.last_payment, PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED)


def cancel_subscription(user):
    """ Cancels the currently active or waiting subscription for a user """
    subscription = Subscription.get_current_for_user(user)
    subscription.state = Subscription.STATE_1_CANCELLED_BUT_ACTIVE
    subscription.cancelled = now()
    subscription.save()
    send_payment_event_payment_email(subscription.last_payment, PAYMENT_EVENT_SUBSCRIPTION_TERMINATED)
    return True
    

def change_subscription_amount(subscription, amount):
    """ Ends the currently active or waiting subscription for a user """
    # check min/max payment amounts
    if amount > settings.PAYMENTS_MAXIMUM_ALLOWED_PAYMENT_AMOUNT or \
            amount < settings.PAYMENTS_MINIMUM_ALLOWED_PAYMENT_AMOUNT:
        return False
    subscription.amount = amount
    subscription.save()
    send_payment_event_payment_email(subscription.last_payment, PAYMENT_EVENT_SUBSCRIPTION_AMOUNT_CHANGED)
    return True
    


