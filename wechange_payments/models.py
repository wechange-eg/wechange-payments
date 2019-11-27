# -*- coding: utf-8 -*-

import logging

from annoying.functions import get_object_or_None
from dateutil import relativedelta
from django.contrib.postgres.fields.jsonb import JSONField
from django.db import models
from django.urls.base import reverse
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django_countries.fields import CountryField

from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT, \
    PAYMENT_TYPE_CREDIT_CARD, PAYMENT_TYPE_PAYPAL
from wechange_payments.utils.utils import _get_invoice_filename


logger = logging.getLogger('wechange-payments')

USERPROFILE_SETTING_POPUP_CLOSED = 'payment_popup_closed_date'
USERPROFILE_SETTING_POPUP_CLOSED_TIMES = 'payment_popup_closed_times'
# False or missing means "existing user"
# True means newly registered user (after payments were introduced) who hasn't clicked away the popup ever
USERPROFILE_SETTING_POPUP_USER_IS_NEW = 'payment_popup_user_registered_after_payments'


class Payment(models.Model):
    """ 
        Payment model.
        
        State `STATUS_PREAUTHORIZED_UNPAID` is a special state, where a future payment
            has been authorized and saved at the payment proveider, and only needs a special
            API call to confirm and "cash in" the payment. 
            This is used for postponed subscriptions, that are created while a current 
            subscription is still running.
    """
    
    TYPE_CHOICES = (
        (PAYMENT_TYPE_DIRECT_DEBIT, _('Direct Debit (SEPA)')),
        (PAYMENT_TYPE_CREDIT_CARD, _('Credit Card')),
        (PAYMENT_TYPE_PAYPAL, _('PayPal')),
    )
    
    STATUS_NOT_STARTED = 0
    STATUS_STARTED = 1
    STATUS_COMPLETED_BUT_UNCONFIRMED = 2
    STATUS_PAID = 3
    STATUS_PREAUTHORIZED_UNPAID = 301
    STATUS_FAILED = 101
    STATUS_RETRACTED = 102
    STATUS_CANCELED = 103
    
    STATUS_CHOICES = (
        (STATUS_NOT_STARTED, _('Not started')),
        (STATUS_STARTED, _('Payment initiated but not completed by user yet')),
        (STATUS_COMPLETED_BUT_UNCONFIRMED, _('Payment processing')),
        (STATUS_PAID, _('Successfully paid')),
        (STATUS_PREAUTHORIZED_UNPAID, _('Pre-authorized for payment, but not yet paid')),
        (STATUS_FAILED, _('Failed')),
        (STATUS_RETRACTED, _('Retracted')),
        (STATUS_CANCELED, _('Canceled')),
    )
    
    # payments with this status are "done", signalling that
    # further payments may be made on a subscription
    FINALIZED_STATUSES = (
        STATUS_FAILED,
        STATUS_PAID,
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
    type = models.CharField(_('Payment Type'), blank=False,
        default=PAYMENT_TYPE_DIRECT_DEBIT, choices=TYPE_CHOICES, editable=False, max_length=50)
    last_action_at = models.DateTimeField(verbose_name=_('Last Action At'), editable=False, auto_now=True)
    completed_at = models.DateTimeField(verbose_name=_('Completed At'), editable=False, blank=True, null=True)
    status = models.PositiveSmallIntegerField(_('Payment Status'), blank=False,
        default=STATUS_NOT_STARTED, choices=STATUS_CHOICES, editable=False)
    
    is_reference_payment = models.BooleanField(verbose_name=_('Is reference payment'), default=True, editable=False, 
        help_text='Is this the reference (first) payment in a series or a subscription payment derived from a reference payment?') 
    is_postponed_payment = models.BooleanField(verbose_name=_('Is postponed payment'), default=False, editable=False, 
        help_text='Is this a postponed payment, that gets pre-authorized first, and then cashed-in at some later point?') 
    revoked = models.BooleanField(verbose_name=_('Has been revoked'), default=False)
    
    # billing address details, can be saved for some payment methods, but not necessary
    first_name = models.CharField(blank=True, null=True, max_length=255)
    last_name = models.CharField(blank=True, null=True, max_length=255)
    email = models.EmailField(blank=True, null=True)
    address = models.CharField(blank=True, null=True, max_length=255)
    city = models.CharField(blank=True, null=True, max_length=255)
    postal_code = models.CharField(blank=True, null=True, max_length=255)
    country = CountryField(blank=True, null=True)
    
    backend = models.CharField(_('Backend class used'), max_length=255)
    extra_data = JSONField(null=True, blank=True)
    
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
    """
        Subscription model. Has an initial reference payment which can be used
        to book further payments from a provider.
        The `state` of the subscription is extremely important, as it determines
        if further payments can be made from it. 
        The `next_due_date` determines if a further payment may be made at this time.
        
        States mostly exclusive, meaning if for a user, one subscription of that state
        exists, no more for that users with the same state(s) can also exist.
        This is enforced in the `save()` method.
        The two "current" states 1 and 2 are mutually exclusive, and while there is
        an active 2 subscription, there can never be a waiting (3) subscription!
        Check `EXLUSIVE_STATE_MAP` to for a full list of exclusive states.
        
        ### State transition overview:
        
        A listing of all cases that can happen, where Subscriptions are created
        or are transitioning states for one specific user.
        * Sub is a newly created Subscription (after a successful payment)
        * S<n> are existing Subscriptions with the state <n>.
        * Cycle(<result>) is the daily call to `process_due_subscription_payments` to book
            due subscription payments
        * Pattern is: <precondition> + <addition> --> <result>
        
        Case A: If PAYMENTS_POSTPONED_PAYMENTS_IMPLEMENTED == False:
        ---------------
            Postponed payments are not implemented right now. 
            Betterpayments does not support these, but another payment provider might.
            Any payment info changes trigger the current subscription to be instantly
            terminated, and a new subscription to be created, which gets the remaining
            runtime of the current subscription added to it.
        
        1. <None> + Sub --> Sub becomes S2 
                (new subscription)
        2. S2 + Sub --> S2 becomes S0, Sub becomes S2 
                (updated payment infos, old sub is terminated, new Sub gets time of old S2 added)
        3. S1 + Sub --> S1 becomes S0, Sub becomes S2 
                (canceled Subscriptions, created new subscription before next payment due, 
                old sub is terminated, new Sub gets time of old S2 added)
        4. <None> + Cycle() --> no effect 
                (user has no subscription)
        5. S2(due) + Cycle(success) --> S2
                (successfully booked a recurring payment for a due subscription)
        6. S2(due) + Cycle(payment-failure) --> S2 becomes S99
                (due subscription is suspended because payment for subscription failed 
                because of no-longer-correct payment infos) 
        7. S1(due) + Cycle() --> S1 becomes S0
                (cancelled subscription is terminated after its due date arrives, no further 
                subscriptions are waiting to be activated)
        
        Case B (NOT IMPLEMENTED): If PAYMENTS_POSTPONED_PAYMENTS_IMPLEMENTED == True:
        ---------------
        Should postponed payments ever be fully implemented, there is a
        waiting state for postponed payments, that are meant for future 
        subscriptions to wait to become active until the current one runs out.
        This is how it should act out:
        
        1. <None> + Sub --> Sub becomes S2 
                (new subscription)
        2. S2 + Sub --> S2 becomes S1, Sub becomes S3 
                (updated payment infos, becomes active next due date)
        3. S1 + Sub --> Sub becomes S3 
                (canceled Subscriptions, created new subscription before next payment due)
        4. S1,S3 + Sub  --> S1 stays S1, S3 becomes S0, Sub becomes S3 
                (updated payment infos again, or on a waiting subscription)
        5. S3 + Sub --> S3 becomes S0, Sub becomes S3 
                (only a waiting subscription, can happen if the payment provider is down 
                for multiple days)
        6. <None> + Cycle() --> no effect 
                (user has no subscription)
        7. S2 + Cycle(success) --> S2
                (successfully booked a recurring payment for subscription)
        8. S2 + Cycle(payment-failure) --> S2 becomes S99
                (subscription is suspended because payment for subscription failed 
                because of no-longer-correct payment infos) 
        9. S1,S3 + Cycle(success) --> S1 becomes S0, S3 becomes S2
                (cancelled subscription is terminated after running out, waiting 
                subscription is cashed in and activated)
        10. S1,S3 + Cycle(failure) --> S1 becomes S0, S3 becomes S99
                (cancelled subscription is terminated after running out, waiting 
                subscription is set to suspended because of failed payment)
        11. S3 + Cycle(success) --> S3 becomes S2
                (see 9.)
        12. S3 + Cycle(failure) --> S3 becomes S99
                (see 10.)
        13. S1 + Cycle() --> S1 becomes S0
                (cancelled subscription is terminated after running out, no further 
                subscriptions are waiting to be activated)
        
        Note: All payments for Subscriptions that would become S3 are made as 
            pre-authorized payments that will only be cashed in once the Cycle is being 
            called and the waiting Subscription is due.
    """
    
    # A cancelled subscription that no longer has any run-time left. There can be many of those.
    STATE_0_TERMINATED = 0
    # A cancelled subscription that still has run-time left because there was a recent payment.
    # As soon as the next_due_date arrives, this subscription will go to state 0.
    STATE_1_CANCELLED_BUT_ACTIVE = 1
    # Active
    STATE_2_ACTIVE = 2
    # A new subscription waiting for next payment due date, but with another subscription with the state STATE_1_CANCELLED_BUT_ACTIVE.
    # There can only be one subscription with state 3 active at a time.
    STATE_3_WAITING_TO_BECOME_ACTIVE = 3
    # A special state that a subscription gets put in when its payments have been unsuccessful or redacted
    # This will be kept and can be shown to the user as current subscription,
    # but can be terminated by them, and it gets terminated immediately if a
    # new subscription is made 
    STATE_99_FAILED_PAYMENTS_SUSPENDED = 99
    
    # - A subscription can only ever go from higher number states to lower number states, never back up again!
    #     (except for the special STATE_99_FAILED_PAYMENTS_SUSPENDED state)
    # - There should only ever be one subscription for each user in both states 1 and 2 combined
    STATES = [
        (STATE_0_TERMINATED, _('Terminated.')),
        (STATE_1_CANCELLED_BUT_ACTIVE, _('Cancelled, but still active')),
        (STATE_2_ACTIVE, _('Active')),
    ]
    # switch for not-implemented postponed subscriptions
    if settings.PAYMENTS_POSTPONED_PAYMENTS_IMPLEMENTED:
        STATES += [
            (STATE_3_WAITING_TO_BECOME_ACTIVE, _('Waiting, becoming active at next payment due date')),
        ]
    STATES += [
        (STATE_99_FAILED_PAYMENTS_SUSPENDED, _('Suspended, because of payment errors')),
    ]
    
    ACTIVE_STATES = (
        STATE_1_CANCELLED_BUT_ACTIVE,
        STATE_2_ACTIVE,
    )
    
    ALLOWED_TO_MAKE_NEW_SUBSCRIPTION_STATES = (
        STATE_0_TERMINATED,
        STATE_1_CANCELLED_BUT_ACTIVE,
    )
    
    # if a subsription is in any of these states, no other subscription for the same user
    # may exist. enforced at `Subscription.save()`
    EXLUSIVE_STATE_MAP = {
        STATE_1_CANCELLED_BUT_ACTIVE: (
            STATE_1_CANCELLED_BUT_ACTIVE,
            STATE_2_ACTIVE,
            STATE_99_FAILED_PAYMENTS_SUSPENDED
        ),
        STATE_2_ACTIVE: (
            STATE_1_CANCELLED_BUT_ACTIVE,
            STATE_2_ACTIVE,
            STATE_3_WAITING_TO_BECOME_ACTIVE,
            STATE_99_FAILED_PAYMENTS_SUSPENDED
        ),
        STATE_3_WAITING_TO_BECOME_ACTIVE: STATE_3_WAITING_TO_BECOME_ACTIVE,
        STATE_99_FAILED_PAYMENTS_SUSPENDED: ACTIVE_STATES,
    }
    
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
    num_attempts_recurring = models.PositiveSmallIntegerField(_('Attempts of booking recurring payment'), blank=False,
        default=0, editable=False,
        help_text='If booking a recurring payment for a subscription fails for non-payment-specific reasons, (e.g.. payment provider is down), we use this to count up attempts to retry.')
    
    next_due_date = models.DateField(verbose_name=_('Next due date'), null=True, blank=True,
        help_text='Set to the next date whenever a payment is processed successfully.')
    amount = models.FloatField(verbose_name=_('Amount'), default='0.0', editable=False,
        help_text='For security reasons, the amount can not be changed through the admin interface!')
    
    last_payment = models.ForeignKey('wechange_payments.Payment', verbose_name=_('Last Payment'), 
        on_delete=models.PROTECT, related_name='+', null=False,
        help_text='The most recent payment made.')
    
    created = models.DateTimeField(verbose_name=_('Created'), editable=False, auto_now_add=True)
    cancelled = models.DateTimeField(verbose_name=_('Cancelled by User'), editable=False, blank=True, null=True)
    terminated = models.DateTimeField(verbose_name=_('Finally terminated by System'), editable=False, blank=True, null=True)
    
    class Meta(object):
        ordering = ('created',)
        verbose_name = _('Subscription')
        verbose_name_plural = _('Subscription')
        
    def __init__(self, *args, **kwargs):
        super(Subscription, self).__init__(*args, **kwargs)
        self._old_state = self.state
        
    @classmethod
    def get_current_for_user(cls, user):
        """ Returns the currently active or canceled-but-active subscription for a user. """
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
    def get_canceled_for_user(cls, user):
        """ Returns the currently canceled-but-active subscription for a user. """
        if not user.is_authenticated:
            return None
        return get_object_or_None(cls, user=user, state=Subscription.STATE_1_CANCELLED_BUT_ACTIVE)
    
    @classmethod
    def get_waiting_for_user(cls, user):
        """ Returns the currently waiting subscription for a user. """
        if not user.is_authenticated:
            return None
        return get_object_or_None(cls, user=user, state=Subscription.STATE_3_WAITING_TO_BECOME_ACTIVE)
    
    @classmethod
    def get_suspended_for_user(cls, user):
        """ Returns the current suspended subscription for a user. """
        if not user.is_authenticated:
            return None
        return get_object_or_None(cls, user=user, state=Subscription.STATE_99_FAILED_PAYMENTS_SUSPENDED)
    
    def validate_state_and_cycle(self):
        """ This will terminate this subscription if it has been cancelled, 
            and whose next_due_date is in the past! 
            If an old subscription has been terminated, this will check if there
            is a new waiting subscription to be activated, and if so, activate it. """
        if self.check_termination_due():
            # terminate the subscription if the user cancelled it and it's past its next due_date
            self.state = self.STATE_0_TERMINATED
            self.terminated = now()
            self.save()
            logger.warn('REMOVEME: Done ended old expired sub!')
            
    def check_payment_due(self):
        """ Returns true if the subscription is active and `next_due_date` is in the past or today.
            Note: To check if a canceled subscription is due to be terminated, 
                use `self.check_termination_due()`! """
        if self.state == self.STATE_2_ACTIVE:
            return self.get_next_payment_date() <= now().date()
        return False
        
    def get_next_payment_date(self):
        """ Returns a Date of the next due payment date """
        if self.state == self.STATE_2_ACTIVE:
            return self.next_due_date
        return None
    
    def check_termination_due(self):
        if self.state == self.STATE_1_CANCELLED_BUT_ACTIVE:
            return self.next_due_date <= now().date()
        return False 
    
    def set_next_due_date(self, last_target_date):
        """ Sets the `next_due_date` based on the date of the last target date.
            This will set the due date to one month ahead of the target date's, 
            with the day of month of the reference payment, or the last day of month
            if it is a shorter month.
            Should be called after a recurring payment has been successfully made. """
        self.next_due_date = self.get_due_date_after_next(last_target_date) 
    
    def get_due_date_after_next(self, target_date=None):
        if target_date is None:
            target_date = self.next_due_date
        next_month_date = target_date + relativedelta.relativedelta(months=1)
        try:
            next_month_date.replace(day=self.reference_payment.completed_at.day)
        except:
            pass
        return next_month_date
    
    def has_pending_payment(self):
        """ Checks if a subscription's `last_payment` is still in a pending
            state, indicating that no further payments may be booked on it for now """
        last_payment = self.last_payment
        return bool(last_payment and last_payment.status not in Payment.FINALIZED_STATUSES)
    
    def save(self, *args, **kwargs):
        """ Do sanity checks: 
            - ensure Subscription.state only ever changes downwards
            - ensure that no other Subscription for the same user exists that would have the same active state """
        created = bool(self.pk is None)
        # state must be lower if changed
        if not created:
            if self.state > self._old_state:
                logger.error('Fatal: Sanity check failed for subscription: Tried to save a subscription with a state higher than it previously was!',
                    extra={'user': self.user, 'subscription_pk': self.pk, 'state': self.state, 'prev_state': self._old_state}) 
                ('Fatal: Sanity check failed for subscription: Tried to save a subscription with a state higher than it previously was!')
        # no other subscription for the user with an exclusive state may exist
        exclusive_states = Subscription.EXLUSIVE_STATE_MAP.get(self.state, [])
        if exclusive_states:
            exclusive_qs = Subscription.objects.filter(user=self.user, state__in=exclusive_states)
            if self.pk is not None:
                exclusive_qs = exclusive_qs.exclude(pk=self.pk)
            if exclusive_qs.count() > 0:
                logger.error('Fatal: Sanity check failed for subscription: \
                    Tried to save a subscription when another subscription with an exclusive state exists for the same user!',
                    extra={'user': self.user, 'subscription_pk': self.pk, 'state': self.state}) 
                raise Exception('Fatal: Sanity check failed for subscription: \
                    Tried to save a subscription when another subscription with an exclusive state exists for the same user!')
        super(Subscription, self).save(*args, **kwargs)
        

class Invoice(models.Model):
    
    # not created yet at the provider. if an invoice is stuck at this state, the api might not be available
    STATE_0_NOT_CREATED = 0
    # created at the payment provider, but not finalized or downloaded
    STATE_1_CREATED = 1
    # finalized at the provider and ready to download (depending on the provider, this step may not be necessary)
    STATE_2_FINALIZED = 2
    # final state. the invoice file was downloaded. when this state is reached, `is_ready` is set to True
    STATE_3_DOWNLOADED = 3
    
    # An invoice's states can only increase.
    STATES = (
        (STATE_0_NOT_CREATED, _('Not created at provider.')),
        (STATE_1_CREATED, _('Created, but not finalized')),
        (STATE_2_FINALIZED, _('Finalized, but not downloaded')),
        (STATE_3_DOWNLOADED, _('Downloaded and ready')),
    )
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_('User'), 
        editable=False, related_name='invoices', on_delete=models.CASCADE, null=False)
    payment = models.OneToOneField('wechange_payments.Payment', verbose_name=_('Payment'), 
        on_delete=models.PROTECT, related_name='invoice', null=False, editable=False, unique=True,
        help_text='The first payment for this subscription, which is also used to book any future payments.')
    
    state = models.PositiveSmallIntegerField(_('Invoice State'), blank=False,
        default=STATE_0_NOT_CREATED, choices=STATES, editable=False,
        help_text='An invoice\'s state can only ever increase.')
    is_ready = models.BooleanField(verbose_name=_('Is Ready'), default=False,
        help_text='An indicator flag to show that the invoice has been created in the invoice provider and can be downloaded')
    
    file = models.FileField(_('File'), blank=True, null=True, max_length=250, upload_to=_get_invoice_filename, editable=False)
    provider_id = models.CharField(_('Provider Invoice ID'), max_length=255, blank=True, null=True, editable=False)
    backend = models.CharField(_('Invoice Provider Backend class used'), max_length=255, editable=False)
    extra_data = JSONField(null=True, blank=True,
        help_text='This may contain the download path or similar IDs to retrieve the file from the provider.')
    
    created = models.DateTimeField(verbose_name=_('Created'), editable=False, auto_now_add=True)
    last_action_at = models.DateTimeField(verbose_name=_('Last Action At'), editable=False, auto_now=True,
        help_text='Used to indicate when the last attempt to retrieve the invoice from the provider was made, so not to spam them in case their API is down.')
    
    class Meta(object):
        ordering = ('-created',)
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
    
    def get_absolute_url(self):
        return reverse('wechange-payments:invoice-detail', kwargs={'pk': self.pk})

    def get_download_url(self):
        return reverse('wechange-payments:invoice-download', kwargs={'pk': self.pk})
