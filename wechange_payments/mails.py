# -*- coding: utf-8 -*-

from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT

import logging
from cosinnus.utils.functions import resolve_class
from django.template.loader import render_to_string
from wechange_payments import signals
from django.utils.translation import pgettext_lazy
from cosinnus.models.group import CosinnusPortal
from cosinnus.templatetags.cosinnus_tags import full_name
from django.urls.base import reverse
from django.templatetags.l10n import localize

logger = logging.getLogger('wechange-payments')

# email templates depending on payment statuses and types, see `EMAIL_TEMPLATES_STATUS_MAP`
EMAIL_TEMPLATES_SUCCESS = {
    'wechange_payments/mail/sepa_payment_success.html',
    'wechange_payments/mail/sepa_payment_success_subj.txt'
}

PAYMENT_EVENT_SUCCESSFUL_PAYMENT = 'successful_payment'
PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED = 'new_subscription'
PAYMENT_EVENT_NEW_REPLACEMENT_SUBSCRIPTION_CREATED = 'replaced_subscription'
PAYMENT_EVENT_SUBSCRIPTION_AMOUNT_CHANGED = 'admount_changed'
PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED = 'suspended_subscription'
PAYMENT_EVENT_SUBSCRIPTION_TERMINATED = 'terminated_subscription'

PAYMENT_EVENTS = (
    PAYMENT_EVENT_SUCCESSFUL_PAYMENT,
    PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED,
    PAYMENT_EVENT_NEW_REPLACEMENT_SUBSCRIPTION_CREATED,
    PAYMENT_EVENT_SUBSCRIPTION_AMOUNT_CHANGED,
    PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED,
    PAYMENT_EVENT_SUBSCRIPTION_TERMINATED,
)

""" For the i18n strings, see the given Translation Pad/Doc """

MAIL_PRE = pgettext_lazy('(MAILPRE)', '(MAILPRE) with variables: %(username)s,')
MAIL_LINKS = pgettext_lazy('(MAILLINKS)', '(MAILLINKS) %(link_payment_info)s %(link_invoices)s')
MAIL_POST = pgettext_lazy('(MAILPOST)', '(MAILPOST) with variables: %(portal_name)s')

MAIL_BODY = {
    PAYMENT_EVENT_SUCCESSFUL_PAYMENT: pgettext_lazy('(MAIL2)', '(MAIL2) with variables: %(payment_method)s %(contribution_amount)s'),
    PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED: pgettext_lazy('(MAIL1a)', '(MAIL1a) with variables: %(portal_name)s %(next_debit_date)s %(contribution_amount)s'),
    PAYMENT_EVENT_NEW_REPLACEMENT_SUBSCRIPTION_CREATED: pgettext_lazy('(MAIL1b)', '(MAIL1b) with variables: %(portal_name)s %(next_debit_date)s %(contribution_amount)s'),
    PAYMENT_EVENT_SUBSCRIPTION_AMOUNT_CHANGED: pgettext_lazy('(MAIL3)', '(MAIL3) with variables: %(contribution_amount)s %(next_debit_date)s'),
    PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED: pgettext_lazy('(MAIL4)', '(MAIL4) with variables: %(portal_name)s %(link_new_payment)s %(support_email)s'),
    PAYMENT_EVENT_SUBSCRIPTION_TERMINATED: pgettext_lazy('(MAIL5)', '(MAIL5) with variables: %(portal_name)s %(link_new_payment)s %(link_payment_issues)s'),
}
MAIL_SUBJECT = {
    PAYMENT_EVENT_SUCCESSFUL_PAYMENT: pgettext_lazy('(MAIL2s)', '(MAIL2s) with variables: -'),
    PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED: pgettext_lazy('(MAIL1s)', '(MAIL1s) with variables: %(portal_name)s'),
    PAYMENT_EVENT_NEW_REPLACEMENT_SUBSCRIPTION_CREATED: pgettext_lazy('(MAIL1s)', '(MAIL1s) with variables: %(portal_name)s'),
    PAYMENT_EVENT_SUBSCRIPTION_AMOUNT_CHANGED: pgettext_lazy('(MAIL3s)', '(MAIL3s) with variables: -'),
    PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED: pgettext_lazy('(MAIL4s)', '(MAIL4s) with variables: -'),
    PAYMENT_EVENT_SUBSCRIPTION_TERMINATED: pgettext_lazy('(MAIL5s)', '(MAIL5s) with variables: -'),
}


def send_payment_event_payment_email(payment, event):
    """ Sends an email to a user for an event such ass success/errors in payments, or updates to subscriptions.
        Mail type depends on the given event.
        @param payment: Always supply a payment for this function, the subscription will be taken from its
            `subscription` relation. If all you have is a subscription, supply the `subscription.last_payment`.
        @param event: one of the values of `PAYMENT_EVENTS`. 
    """
    try:
        if not payment.user:
            logger.warning('Sending payment status message was ignored because no user was attached to the payment',
                    extra={'payment': payment.id})
            return 
        if not event in PAYMENT_EVENTS:
            logger.error('Could not send out a payment event email because the event type was unknown.',
                    extra={'payment': payment.id})
            return
        
        email = payment.user.email
        template = 'wechange_payments/mail/mail_base.html'
        subject_template = 'wechange_payments/mail/subject_base.txt'
        portal = CosinnusPortal.get_current()
        
        # prepare all possible variables
        variables = {
            'payment': payment,
            'link_payment_info': reverse('wechange_payments:payment-infos'),
            'link_invoices': reverse('wechange_payments:invoices'),
            'link_new_payment': reverse('wechange_payments:payment'),
            'link_payment_issues': reverse('wechange_payments:suspended-subscription'),
            'portal_name': portal.name,
            'username': full_name(payment.user),
            'contribution_amount': str(payment.amount),
            'next_debit_date': localize(payment.subscription.get_next_payment_date().date())     ,
            'payment_method': payment.get_type_string(),
            'support_email': portal.support_email,
        }
        # compose email parts
        data = {
            'mail_pre': MAIL_PRE % variables,
            'mail_links': MAIL_LINKS % variables,
            'mail_post': MAIL_POST % variables,
            'mail_body': MAIL_BODY.get(event) % variables,
            'mail_subject': MAIL_SUBJECT.get(event) % variables,
        }
        # add SEPA mandate info to mail body for successful SEPA payment email
        if payment.type == PAYMENT_TYPE_DIRECT_DEBIT and event == PAYMENT_EVENT_SUCCESSFUL_PAYMENT:
            data['mail_body'] += '\n\n' + render_to_string('wechange_payments/mail/sepa_mandate_partial.html', variables)
        
        # send mail
        if settings.PAYMENTS_USE_HOOK_INSTEAD_OF_SEND_MAIL == True:
            signals.success_email_sender.send(sender=payment, to_email=email, template=template, subject_template=subject_template, data=data)
        else:
            subject = render_to_string(subject_template, data)
            message = render_to_string(template, data)
            mail_func = resolve_class(settings.PAYMENTS_SEND_MAIL_FUNCTION)
            mail_func(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
    except Exception as e:
        logger.warning('Payments: Sending a payment status email to the user failed!', extra={'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id, 'exception': e})
        