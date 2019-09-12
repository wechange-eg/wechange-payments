# -*- coding: utf-8 -*-

from wechange_payments.conf import settings
from django.db import models
from django.contrib.postgres.fields.jsonb import JSONField
from django.utils.translation import ugettext_lazy as _
import datetime
from dateutil import relativedelta
from django.utils.timezone import now
from annoying.functions import get_object_or_None

import logging
from django_countries.fields import CountryField

logger = logging.getLogger('wechange-payments')

class Payment(models.Model):
    
    TYPE_SEPA = 0
    
    #: Choices for :attr:`type`: ``(int, str)``
    TYPE_CHOICES = (
        (TYPE_SEPA, _('SEPA')),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, editable=False,
        related_name='payments', on_delete=models.CASCADE, null=True)
    subscription = models.ForeignKey('wechange_payments.Subscription', editable=False,
        related_name='payments', on_delete=models.SET_NULL, blank=True, null=True)
    
    vendor_transaction_id = models.CharField(_('Vendor Transaction Id'), max_length=50,
        help_text='An Id for the payment generated by the Payment Service')
    internal_transaction_id = models.CharField(_('Internal Transaction Id'), max_length=50,
        help_text='An Id for the payment generated by us')
    amount = models.FloatField(default='0.0')
    type = models.PositiveSmallIntegerField(_('Payment Type'), blank=False,
        default=TYPE_SEPA, choices=TYPE_CHOICES, editable=False)
    completed_at = models.DateTimeField(verbose_name=_('Completed At'), editable=False, auto_now_add=True)
    
    is_reference_payment = models.BooleanField(verbose_name=_('Is reference payment'), default=True, editable=False, 
        help_text='Is this the reference (first) payment in a series or a subscription payment derived from a reference payment?') 
    revoked = models.BooleanField(verbose_name=_('Has been revoked'), default=False)
    
    # billing address details, can be saved for some payment methods, but not necessary
    first_name = models.CharField(blank=True, null=True, max_length=255)
    last_name = models.CharField(blank=True, null=True, max_length=255)
    email = models.EmailField(blank=True, null=True)
    address = models.CharField(blank=True, null=True, max_length=255)
    city = models.CharField(blank=True, null=True, max_length=255)
    postal_code = models.IntegerField(blank=True, null=True)
    country = CountryField(blank=True, null=True)
    
    backend = models.CharField(_('Backend class used'), max_length=255)
    extra_data = JSONField()
    
    class Meta(object):
        app_label = 'wechange_payments'
        verbose_name = _('Payment')
        verbose_name_plural = _('Payments')
    
    def get_type_string(self):
        return dict(self.TYPE_CHOICES).get(self.type)
    

class TransactionLog(models.Model):
    
    TYPE_REQUEST = 0
    TYPE_POSTBACK = 1
    
    #: Choices for :attr:`type`: ``(int, str)``
    TYPE_CHOICES = (
        (TYPE_REQUEST, _('Direct Request')),
        (TYPE_POSTBACK, _('Received Postback')),
    )
    
    created = models.DateTimeField(verbose_name=_('Created'), editable=False, auto_now_add=True)
    url = models.CharField(_('API Endpoint URL'), max_length=150, null=True, blank=True)
    type = models.PositiveSmallIntegerField(_('Transaction Type'), blank=False,
        default=TYPE_REQUEST, choices=TYPE_CHOICES, editable=False)
    data = JSONField()
    
    class Meta(object):
        app_label = 'wechange_payments'
        verbose_name = _('Payment Transaction Log')
        verbose_name_plural = _('Payment Transaction Logs')


class Subscription(models.Model):
    
    # A cancelled subscription that no longer has any run-time left. There can be many of those.
    STATE_0_TERMINATED = 0
    # A cancelled subscription that still has run-time left because there was a recent payment.
    # As soon as the next_due_date arrives, this subscription will go to state 0.
    STATE_1_CANCELLED_BUT_ACTIVE = 1
    # Active
    STATE_2_ACTIVE = 2
    # A new subscription waiting for next payment due date, but with another subscription with the state STATE_1_CANCELLED_BUT_ACTIVE.
    # There can only be one subscription with state 3 active at a time.
    STATE_3_WATING_TO_BECOME_ACTIVE = 3
    
    # - A subscription can only ever go from higher number states to lower number states, never back up again!
    # - There should only ever be one subscription for each user in both states 1 and 2 combined
    STATES = (
        (STATE_0_TERMINATED, _('Terminated.')),
        (STATE_1_CANCELLED_BUT_ACTIVE, _('Cancelled, but still active')),
        (STATE_2_ACTIVE, _('Active')),
        (STATE_3_WATING_TO_BECOME_ACTIVE, _('Waiting, becoming active at next payment due date')),
    )
    
    ACTIVE_STATES = (
        STATE_1_CANCELLED_BUT_ACTIVE,
        STATE_2_ACTIVE
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('User'), 
        editable=False, related_name='subscriptions', on_delete=models.CASCADE, null=False)
    reference_payment = models.OneToOneField('wechange_payments.Payment', verbose_name=_('Reference Payment'), 
        on_delete=models.PROTECT, related_name='+', null=False,
        help_text='The first payment for this subscription, which is also used to book any future payments.')
    
    # `payments` is the incoming reverse relation from Payment -> Subscription
    
    state = models.PositiveSmallIntegerField(_('Subscription State'), blank=False,
        default=STATE_0_TERMINATED, choices=STATES, editable=False,
        help_text='A subscription can only ever go from higher number states to lower number states, never back up again!')
    has_problems = models.BooleanField(verbose_name=_('Has Problems'), default=False,
        help_text='An indicator flag that there were payment problems with the subscription\'s last payment. The subscription stays in active state however!')
    next_due_date = models.DateField(verbose_name=_('Next due date'), null=True, blank=True,
        help_text='Set to the next date whenever a payment is processed successfully.')
    
    amount = models.FloatField(verbose_name=_('Amount'), default='0.0', editable=False,
        help_text='For security reasons, the amount can not be changed through the admin interface!')
    created = models.DateTimeField(verbose_name=_('Created'), editable=False, auto_now_add=True)
    last_payment = models.ForeignKey('wechange_payments.Payment', verbose_name=_('Last Payment'), 
        on_delete=models.PROTECT, related_name='+', null=False,
        help_text='The most recent payment made.')
    terminated = models.DateTimeField(verbose_name=_('Created'), editable=False, blank=True, null=True)
    
    class Meta(object):
        ordering = ('created',)
        verbose_name = _('Subscription')
        verbose_name_plural = _('Subscription')
        
    @classmethod
    def get_current_for_user(cls, user):
        """ Returns the currently active or waiting subscription for a user. """
        if not user.is_authenticated:
            return None
        return get_object_or_None(cls, user=user, state__in=Subscription.ACTIVE_STATES)
        
    @classmethod
    def get_active_for_user(cls, user):
        """ Returns the currently active subscription for a user. """
        if not user.is_authenticated:
            return None
        return get_object_or_None(cls, user=user, state=Subscription.STATE_2_ACTIVE)

    @classmethod
    def get_waiting_for_user(cls, user):
        """ Returns the currently waiting subscription for a user. """
        if not user.is_authenticated:
            return None
        return get_object_or_None(cls, user=user, state=Subscription.STATE_3_WATING_TO_BECOME_ACTIVE)
    
    def validate_state_and_cycle(self):
        """ This will terminate this subscription if it has been cancelled, 
            and whose next_due_date is in the past! 
            If an old subscription has been terminated, this will check if there
            is a new waiting subscription to be activated, and if so, activate it. """
        if self.state == self.STATE_1_CANCELLED_BUT_ACTIVE and self.get_next_payment_date() <= now().date():
            # terminate the subscription if the user cancelled it and it's past its next due_date
            self.state = self.STATE_0_TERMINATED
            self.save(update_fields=['state'])
            # after a termination, look if there is a waiting sub
            waiting_sub = get_object_or_None(Subscription, user=self.user, state=Subscription.STATE_3_WATING_TO_BECOME_ACTIVE)
            if waiting_sub:
                # if there was a waiting sub, activate it and set it to the due date of the old one
                # sanity check: there cannot be an active subscription if we want to activate this one!
                if Subscription.get_current_for_user(waiting_sub.user) is None:
                    waiting_sub.state = Subscription.STATE_2_ACTIVE
                    waiting_sub.next_due_date = self.next_due_date
                    waiting_sub.save()
                else:
                    logger.error('Payments: Critical sanity check fail: Tried to activate a waiting subscription for a user, but there was already an active subscription!. ', extra={'user': waiting_sub.user, 'subscription': waiting_sub})
        
    
    def check_payment_due(self):
        """ Returns true if the subscription is active and `next_due_date` is in the past or today. """
        if self.state == self.STATE_2_ACTIVE:
            return self.get_next_payment_date() <= now().date()
        return False
        
    def get_next_payment_date(self):
        """ Returns a Date of the next due payment date """
        if self.state == self.STATE_2_ACTIVE:
            self.next_due_date
        return None
    
    def set_next_due_date(self, last_target_date):
        """ Sets the `next_due_date` based on the date of the last target date.
            This will set the due date to the target date's next month, with the day of month of the reference payment,
            or the last day of month if it is a shorter month.
            Called after a recurring payment has been successfully made. """
        next_month_date = last_target_date + relativedelta.relativedelta(months=1)
        try:
            next_month_date.replace(day=self.reference_payment.completed_at.day)
        except:
            pass
        self.next_due_date = next_month_date
    
    def book_next_payment(self):
        """ Will create and book a new payment (using the reference payment as target) 
            for the current `amount` of money.
            Afterwards, will set the next due date for this subscription. """
        if not self.user.is_active:
            logger.warn('Payments: Prevented making a new continuous booking for a user that is inactive!', extra={'user': self.user, 'subscription': self})
            return
        raise Exception('NYI: book_next_payment')
        payment = None # todo: book a new payment
        payment.subscription = self
        self.set_next_due_date(self.next_due_date)
        self.last_payment = payment
        self.save()
        logger.info('Payments: Advanced the due_date of a subscription and saved it after a payment was made. ', extra={'user': self.user, 'subscription': self})


    
