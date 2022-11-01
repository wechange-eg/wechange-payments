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
from django.utils import translation

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
PAYMENT_EVENT_SUBSCRIPTION_TERMINATED = 'terminated_subscription'
PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED = 'suspended_subscription'
PAYMENT_EVENT_SUBSCRIPTION_PAYMENT_PRE_NOTIFICATION = 'subscription_payment_pre_notification'

PAYMENT_EVENTS = (
    PAYMENT_EVENT_SUCCESSFUL_PAYMENT,
    PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED,
    PAYMENT_EVENT_NEW_REPLACEMENT_SUBSCRIPTION_CREATED,
    PAYMENT_EVENT_SUBSCRIPTION_AMOUNT_CHANGED,
    PAYMENT_EVENT_SUBSCRIPTION_TERMINATED,
    PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED,
    PAYMENT_EVENT_SUBSCRIPTION_PAYMENT_PRE_NOTIFICATION,
)

""" For the i18n strings, see the given Translation Pad/Doc """

MAIL_PRE = pgettext_lazy('(MAILPRE)', '(MAILPRE) with variables: %(username)s,')
MAIL_LINKS = pgettext_lazy('(MAILLINKS)', '(MAILLINKS) %(link_payment_info)s %(link_invoices)s')
MAIL_POST = pgettext_lazy('(MAILPOST)', '(MAILPOST) with variables: %(portal_name)s')

MAIL_BODY = {
    PAYMENT_EVENT_SUCCESSFUL_PAYMENT: pgettext_lazy('(MAIL2)', '(MAIL2) with variables: %(payment_method)s %(payment_amount)s %(vat_amount)s'),
    PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED: pgettext_lazy('(MAIL1a)', '(MAIL1a) with variables: %(portal_name)s %(next_debit_date)s %(payment_amount)s'),
    PAYMENT_EVENT_NEW_REPLACEMENT_SUBSCRIPTION_CREATED: pgettext_lazy('(MAIL1b)', '(MAIL1b) with variables: %(portal_name)s %(next_debit_date)s %(payment_amount)s'),
    PAYMENT_EVENT_SUBSCRIPTION_AMOUNT_CHANGED: pgettext_lazy('(MAIL3)', '(MAIL3) with variables: %(subscription_amount)s %(next_debit_date)s'),
    PAYMENT_EVENT_SUBSCRIPTION_TERMINATED: pgettext_lazy('(MAIL4)', '(MAIL4) with variables: %(portal_name)s %(link_new_payment)s %(support_email)s'),
    PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED: pgettext_lazy('(MAIL5)', '(MAIL5) with variables: %(portal_name)s %(link_new_payment)s %(link_payment_issues)s'),
    PAYMENT_EVENT_SUBSCRIPTION_PAYMENT_PRE_NOTIFICATION: pgettext_lazy('(MAIL6)', '(MAIL6) with variables: %(portal_name)s %(iban)s %(sepa_mandate)s %(sepa_creditor)s %(next_debit_date)s %(subscription_amount)s %(support_email)s'),
}
MAIL_SUBJECT = {
    PAYMENT_EVENT_SUCCESSFUL_PAYMENT: pgettext_lazy('(MAIL2s)', '(MAIL2s) with variables: -'),
    PAYMENT_EVENT_NEW_SUBSCRIPTION_CREATED: pgettext_lazy('(MAIL1s)', '(MAIL1s) with variables: %(portal_name)s'),
    PAYMENT_EVENT_NEW_REPLACEMENT_SUBSCRIPTION_CREATED: pgettext_lazy('(MAIL1s)', '(MAIL1s) with variables: %(portal_name)s'),
    PAYMENT_EVENT_SUBSCRIPTION_AMOUNT_CHANGED: pgettext_lazy('(MAIL3s)', '(MAIL3s) with variables: -'),
    PAYMENT_EVENT_SUBSCRIPTION_TERMINATED: pgettext_lazy('(MAIL4s)', '(MAIL4s) with variables: -'),
    PAYMENT_EVENT_SUBSCRIPTION_SUSPENDED: pgettext_lazy('(MAIL5s)', '(MAIL5s) with variables: -'),
    PAYMENT_EVENT_SUBSCRIPTION_PAYMENT_PRE_NOTIFICATION: pgettext_lazy('(MAIL6s)', '(MAIL6s) with variables: -'),
}


def send_payment_event_payment_email(payment, event):
    """ Sends an email to a user for an event such ass success/errors in payments, or updates to subscriptions.
        Mail type depends on the given event.
        @param payment: Always supply a payment for this function, the subscription will be taken from its
            `subscription` relation. If all you have is a subscription, supply the `subscription.last_payment`.
        @param event: one of the values of `PAYMENT_EVENTS`. 
        @return: True if the mail was successfully relayed, False or raises otherwise. 
    """
    cur_language = translation.get_language()
    try:
        if not payment.user:
            logger.warning('Sending payment status message was ignored because no user was attached to the payment',
                    extra={'payment': payment.id})
            return 
        if not event in PAYMENT_EVENTS:
            logger.error('Could not send out a payment event email because the event type was unknown.',
                    extra={'payment': payment.id})
            return
        user = payment.user
        email = user.email
        template = 'wechange_payments/mail/mail_base.html'
        subject_template = 'wechange_payments/mail/subject_base.txt'
        portal = CosinnusPortal.get_current()
        
        # switch language to user's preference language
        translation.activate(getattr(user.cosinnus_profile, 'language', settings.LANGUAGES[0][0]))
        
        link_html = '[' + str(pgettext_lazy('(URL-LABEL)', 'Link')) + '](' + portal.get_domain() + '%s)'
        mail_html = '[%s](mailto:%s)'
        
        # prepare all possible variables
        sepa_mandate = None
        iban = None
        if payment.type == PAYMENT_TYPE_DIRECT_DEBIT:
            reference_payment = payment.subscription.reference_payment
            sepa_mandate = reference_payment.extra_data.get('sepa_mandate_token', None)
            iban = reference_payment.extra_data.get('iban', None)
            
        variables = {
            'payment': payment,
            'link_payment_info': link_html % reverse('wechange_payments:payment-infos'),
            'link_invoices': link_html % reverse('wechange_payments:invoices'),
            'link_new_payment': link_html % reverse('wechange_payments:payment'),
            'link_payment_issues': link_html % reverse('wechange_payments:suspended-subscription'),
            'portal_name': portal.name,
            'username': full_name(payment.user),
            'payment_amount': str(int(payment.amount)),
            'vat_amount': str(int(settings.PAYMENTS_INVOICE_PROVIDER_TAX_RATE_PERCENT)),
            'subscription_amount': str(int(payment.subscription.amount)),
            'next_debit_date': localize(payment.subscription.get_next_payment_date()),
            'payment_method': payment.get_type_string(),
            'support_email': mail_html % (portal.support_email, portal.support_email),
            'sepa_mandate': sepa_mandate,
            'iban': iban,
            'sepa_creditor': settings.PAYMENTS_SEPA_CREDITOR_ID,
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
            sepa_variables = {
                'payment': payment.subscription.reference_payment,
                'payment_amount': payment.amount, # the amount from the current payment, not the reference payment, in case it has changed since!
                'SETTINGS': settings,
            }
            data['mail_body'] += '\n\n-\n\n' + render_to_string('wechange_payments/mail/sepa_mandate_partial.html', sepa_variables)
        
        # send mail
        if settings.PAYMENTS_USE_HOOK_INSTEAD_OF_SEND_MAIL == True:
            signals.success_email_sender.send(sender=payment, to_user=user, template=template, subject_template=subject_template, data=data)
        else:
            subject = render_to_string(subject_template, data)
            message = render_to_string(template, data)
            mail_func = resolve_class(settings.PAYMENTS_SEND_MAIL_FUNCTION)
            mail_func(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
        return True
    except Exception as e:
        logger.warning('Payments: Sending a payment status email to the user failed!', extra={'internal_transaction_id': payment.internal_transaction_id, 'vendor_transaction_id': payment.vendor_transaction_id, 'exception': e})
        if settings.DEBUG:
            raise
        return False
        
    # switch language back to previous
    translation.activate(cur_language)
    