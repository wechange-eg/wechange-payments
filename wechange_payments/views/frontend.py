# -*- coding: utf-8 -*-

from datetime import timedelta
import logging

from annoying.functions import get_object_or_None
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.dispatch.dispatcher import receiver
from django.http.response import HttpResponseForbidden, HttpResponseNotFound, FileResponse
from django.shortcuts import redirect
from django.urls.base import reverse
from django.utils.encoding import force_text
from django.utils.formats import date_format
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
from django.views.generic.base import TemplateView, RedirectView
from django.views.generic.detail import DetailView

from cosinnus.core.signals import userprofile_ceated
from cosinnus.models.group import CosinnusPortal
from cosinnus.utils.permissions import check_user_superuser
from cosinnus.utils.urls import get_non_cms_root_url, redirect_next_or
from cosinnus.views.mixins.group import RequireLoggedInMixin
from wechange_payments.backends import get_invoice_backend
from wechange_payments.conf import settings
from wechange_payments.forms import PaymentsForm
from wechange_payments.models import Subscription, Payment, \
    USERPROFILE_SETTING_POPUP_CLOSED, Invoice
from wechange_payments.payment import cancel_subscription as do_cancel_subscription
from wechange_payments.tests.example_data import TEST_DATA_SEPA_PAYMENT_FORM


logger = logging.getLogger('wechange-payments')


class PaymentView(RequireLoggedInMixin, TemplateView):
    
    template_name = 'wechange_payments/payment_form.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(PaymentView, self).dispatch(request, *args, **kwargs)
        
        active_subscription = Subscription.get_active_for_user(self.request.user)
        if active_subscription:
            return redirect('wechange-payments:my-subscription')
        processing_payment = get_object_or_None(Payment, user=request.user, status=Payment.STATUS_COMPLETED_BUT_UNCONFIRMED)
        if processing_payment:
            return redirect(reverse('wechange-payments:payment-process', kwargs={'pk': processing_payment.pk}))
        return super(PaymentView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(PaymentView, self).get_context_data(*args, **kwargs)
        
        initial = {}
        if settings.DEBUG:
            initial = TEST_DATA_SEPA_PAYMENT_FORM
        if self.request.user.first_name:
            initial['first_name'] = self.request.user.first_name
        if self.request.user.last_name:
            initial['last_name'] = self.request.user.last_name
        initial['email'] = self.request.user.email
        form = PaymentsForm(initial=initial)
            
        context.update({
            'form': form,
        })
        return context

payment = PaymentView.as_view()


class PaymentUpdateView(PaymentView):
    
    def dispatch(self, request, *args, **kwargs):
        messages.warning(request, "TODO: Achtung: Eigentlich sollte hier das Bezahlformular erscheinen, und eine neue Bezahlung direkt veranlasst werden können (die im Hintergrund das alte Abo kündigt). Das wird aber in den nächsten Tagen erst implementiert. Bis dahin muss man über 'Zahlungen einstellen' sein Abo erstmal beenden!")
        return super(PaymentUpdateView, self).dispatch(request, *args, **kwargs)

payment_update = PaymentUpdateView.as_view()

class PaymentSuccessView(RequireLoggedInMixin, DetailView):
    """ This view shows the "thank-you" screen once the Payment+Subscription is complete. """
    
    model = Payment
    template_name = 'wechange_payments/payment_success.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(PaymentSuccessView, self).dispatch(request, *args, **kwargs)
        
        self.object = self.get_object()
        # must be owner of the payment
        if not self.object.user == self.request.user and not check_user_superuser(self.request.user):
            raise PermissionDenied()
        # if the payment has not been completed, redirect to the process page
        if self.object.status == Payment.STATUS_STARTED or self.object.status == Payment.STATUS_COMPLETED_BUT_UNCONFIRMED:
            return redirect(reverse('wechange-payments:payment-process', kwargs={'pk': self.object.pk}))
        elif self.object.status != Payment.STATUS_PAID:
            messages.error(request, str(_('There was an error with your payment.')) + ' ' + str(_('Please contact our support for assistance!')))
            return redirect('wechange-payments:overview')
        return super(PaymentSuccessView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(PaymentSuccessView, self).get_context_data(*args, **kwargs)
        context.update({
            'payment': self.object,
        })
        return context

payment_success = PaymentSuccessView.as_view()


class PaymentProcessView(RequireLoggedInMixin, DetailView):
    """ A view that will be redirected to while a payment is still being processed.
        It will automatically refresh itself, wait for the Payment to be set to STATUS_PAID
        (in the background, initiated by a postback request from Better Payment) and
        then redirect to the payment success view. """
    
    model = Payment
    template_name = 'wechange_payments/payment_process.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(PaymentProcessView, self).dispatch(request, *args, **kwargs)
        
        self.object = self.get_object()
        # must be owner of the payment
        if not self.object.user == self.request.user and not check_user_superuser(self.request.user):
            raise PermissionDenied()
        # if the payment has been completed, redirect to the success page
        if self.object.status == Payment.STATUS_PAID:
            return redirect(reverse('wechange-payments:payment-success', kwargs={'pk': self.object.pk}))
        elif self.object.status not in [Payment.STATUS_STARTED, Payment.STATUS_COMPLETED_BUT_UNCONFIRMED]:
            messages.error(self.request, str(_('This payment session has expired.')) + ' ' + str(_('Please try again or contact our support for assistance!')))
            return redirect('wechange-payments:overview')
        return super(PaymentProcessView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(PaymentProcessView, self).get_context_data(*args, **kwargs)
        late_process = self.object.last_action_at < now() - timedelta(seconds=settings.PAYMENTS_LATE_PAYMENT_PROCESS_MESSAGE_SECONDS)
        context.update({
            'show_taking_long_message': late_process,
            'payment': self.object,
        })
        return context

payment_process = PaymentProcessView.as_view()


class WelcomePageView(RequireLoggedInMixin, TemplateView):
    """ A welcome page that introduces the user to payments after registering. """
    
    template_name = 'wechange_payments/welcome_page.html'
    
    def get_context_data(self, *args, **kwargs):
        context = super(WelcomePageView, self).get_context_data(*args, **kwargs)
        context.update({
            'next_url': redirect_next_or(self.request, get_non_cms_root_url())
        })
        return context
        
welcome_page = WelcomePageView.as_view()



class OverviewView(RequireLoggedInMixin, RedirectView):
    """ Redirects to the payment view if the user has no active subscriptions
        and to the my subscription view if there is an active subscription. """
    
    def get_redirect_url(self, *args, **kwargs):
        subscription = get_object_or_None(Subscription, user=self.request.user, state__in=[
            Subscription.STATE_1_CANCELLED_BUT_ACTIVE,
            Subscription.STATE_2_ACTIVE,
            Subscription.STATE_3_WATING_TO_BECOME_ACTIVE,
        ])
        if not subscription or subscription.state in Subscription.ALLOWED_TO_MAKE_NEW_SUBSCRIPTION_STATES:
            return reverse('wechange-payments:payment')
        else:
            return reverse('wechange-payments:my-subscription')
        
overview = OverviewView.as_view()


class MySubscriptionView(RequireLoggedInMixin, TemplateView):
    """ Shows informations about the active or queued subscription and lets the user
        adjust the payment amount. """
    
    template_name = 'wechange_payments/my_subscription.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(MySubscriptionView, self).dispatch(request, *args, **kwargs)
        
        current_subscription = Subscription.get_current_for_user(self.request.user)
        waiting_subscription = Subscription.get_waiting_for_user(self.request.user)
        
        if current_subscription and current_subscription.state == Subscription.STATE_1_CANCELLED_BUT_ACTIVE and waiting_subscription:
            self.cancelled_subscription = current_subscription
            self.subscription = waiting_subscription
        elif current_subscription and current_subscription.state == Subscription.STATE_2_ACTIVE:
            self.cancelled_subscription = None
            self.subscription = current_subscription
        elif waiting_subscription:
            # theoretically, we shouldn't have a waiting subscription without a cancelled
            # on, because then the waiting one should've been activated. but maybe
            # there were payment problems on the waiting one, so better include the case
            self.cancelled_subscription = None
            self.subscription = waiting_subscription
        else:
            return redirect('wechange-payments:payment')
        return super(MySubscriptionView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(MySubscriptionView, self).get_context_data(*args, **kwargs)
        context.update({
            'subscription': self.subscription,
            'cancelled_subscription': self.cancelled_subscription,
        })
        return context
        
my_subscription = MySubscriptionView.as_view()


class PaymentInfosView(RequireLoggedInMixin, TemplateView):
    """ Shows informations about the current subscription and lets the user
        adjust the payment amount. """
    
    template_name = 'wechange_payments/payment_infos.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(PaymentInfosView, self).dispatch(request, *args, **kwargs)
        
        self.current_subscription = Subscription.get_current_for_user(self.request.user)
        self.last_payment = None
        if self.current_subscription:
            self.last_payment = self.current_subscription.last_payment
        self.waiting_subscription = Subscription.get_waiting_for_user(self.request.user)
        self.subscription = self.waiting_subscription or self.current_subscription
        if not self.subscription:
            return redirect('wechange-payments:payment')
        return super(PaymentInfosView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(PaymentInfosView, self).get_context_data(*args, **kwargs)
        context.update({
            'subscription': self.subscription,
            'last_payment': self.last_payment,
        })
        return context
        
payment_infos = PaymentInfosView.as_view()


class PastSubscriptionsView(RequireLoggedInMixin, TemplateView):
    """ Shows a list of past subscriptions. """
    
    template_name = 'wechange_payments/past_subscriptions.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(PastSubscriptionsView, self).dispatch(request, *args, **kwargs)
        
        self.past_subscriptions = Subscription.objects.filter(user=self.request.user, state=Subscription.STATE_0_TERMINATED)
        if not self.past_subscriptions:
            return redirect('wechange-payments:payment')
        return super(PastSubscriptionsView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(MySubscriptionView, self).get_context_data(*args, **kwargs)
        context.update({
            'past_subscriptions': self.past_subscriptions,
        })
        return context
        
past_subscriptions = PastSubscriptionsView.as_view()


class InvoicesView(RequireLoggedInMixin, TemplateView):
    """ Invoices list view """
    
    template_name = 'wechange_payments/invoices/invoice_list.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(InvoicesView, self).dispatch(request, *args, **kwargs)
        
        self.invoices = Invoice.objects.filter(user=request.user)
        if self.invoices.count() == 0:
            return redirect('wechange-payments:overview')
        return super(InvoicesView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(InvoicesView, self).get_context_data(*args, **kwargs)
        context.update({
            'invoices': self.invoices,
        })
        return context

invoices = InvoicesView.as_view()


class InvoiceDetailView(DetailView):
    """ Invoice detail view. 
        If the invoice accessed is not yet ready, we call the provider API invoice creation API
        in the background (honoring the API retry delay) and show the user a message. """

    model = Invoice
    template_name = 'wechange_payments/invoices/invoice_detail.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(InvoiceDetailView, self).dispatch(request, *args, **kwargs)
        
        # must be owner of the invoice
        self.object = self.get_object()
        if not self.object.user == self.request.user and not check_user_superuser(self.request.user):
            raise PermissionDenied()
        
        # immediately download a ready invoice instead of showing its detail page
        if self.object.is_ready and self.object.file:
            return redirect(reverse('wechange-payments:invoice-download', kwargs={'pk': self.object.pk}))
        
        # for non-ready invoices, re-try API invoice creation in background if the retry delay is up
        if not self.object.is_ready:
            if now() > self.object.last_action_at + timedelta(minutes=settings.PAYMENTS_INVOICE_PROVIDER_RETRY_MINUTES):
                invoice_backend = get_invoice_backend()
                invoice_backend.create_invoice(self.object, threaded=True)
        
        return super(InvoiceDetailView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(InvoiceDetailView, self).get_context_data(*args, **kwargs)
        # determine if we show a "it's taking longer than expected, there might be a problem" message
        context.update({
            'long_creation_notice': bool(now() > self.object.created + timedelta(days=1)),
        })
        return context

invoice_detail = InvoiceDetailView.as_view()


class InvoiceDownloadView(DetailView):
    """ Lets the user download the FileField file of an Invoice
        while the user never gets to see the server file path.
        Mime type is always pdf. """
        
    model = Invoice
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(InvoiceDownloadView, self).dispatch(request, *args, **kwargs)
        
        # must be owner of the invoice
        self.object = self.get_object()
        if not self.object.user == self.request.user and not check_user_superuser(self.request.user):
            raise PermissionDenied()
        if not self.object.is_ready or not self.object.file:
            return HttpResponseNotFound()
        return super(InvoiceDownloadView, self).dispatch(request, *args, **kwargs)
    
    def render_to_response(self, context, **response_kwargs):
        invoice = self.object
        path = invoice.file and invoice.file.path
        if not path:
            return HttpResponseNotFound()
    
        response = FileResponse(open(path, 'rb'), content_type='application/pdf')
        short_date = date_format(invoice.created, format='SHORT_DATE_FORMAT', use_l10n=True)
        filename = '%s-%s-%s.pdf' % (CosinnusPortal.get_current().name, force_text(_('Invoice')), short_date)
        # To inspect details for the below code, see http://greenbytes.de/tech/tc2231/
        user_agent = self.request.META.get('HTTP_USER_AGENT', [])
        if u'WebKit' in user_agent:
            # Safari 3.0 and Chrome 2.0 accepts UTF-8 encoded string directly.
            filename_header = 'filename=%s' % filename
        elif u'MSIE' in user_agent:
            filename_header = ''
        else:
            # For others like Firefox, we follow RFC2231 (encoding extension in HTTP headers).
            filename_header = 'filename*=UTF-8\'\'%s' % filename
        response['Content-Disposition'] = 'attachment; ' + filename_header
        return response
    
invoice_download = InvoiceDownloadView.as_view()


class CancelSubscriptionView(RequireLoggedInMixin, TemplateView):
    
    template_name = 'wechange_payments/cancel_subscription.html'
    
    def dispatch(self, request, *args, **kwargs):
        if not self.request.user.is_authenticated:
            return super(CancelSubscriptionView, self).dispatch(request, *args, **kwargs)
        
        current_subscription = Subscription.get_active_for_user(self.request.user)
        if not current_subscription:
            return redirect('wechange-payments:overview')
        return super(CancelSubscriptionView, self).dispatch(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        """ Simply posting to this view will cancel the currently running subscription """
        try:
            success = do_cancel_subscription(request.user)
            if success:
                messages.success(request, _('(MSG1) Your current Subscription was terminated.'))
                return redirect('wechange-payments:overview')
        except Exception as e:
            logger.error('Critical: Could not cancel a subscription!', extra={'exc': force_text(e)})
            messages.error(request, _('(MSG2) There was an error terminating your subscription! Please contact the customer support!'))
            if settings.DEBUG:
                raise
        return redirect('wechange-payments:overview')

cancel_subscription = CancelSubscriptionView.as_view()


def debug_delete_subscription(request):
    """ DEBUG VIEW, completely removes a subscription or processing payment. Only works during the test phase! """
    if not getattr(settings, 'COSINNUS_PAYMENTS_TEST_PHASE', False):
        return HttpResponseForbidden('Not available.')
    if not request.user.is_authenticated:
        return HttpResponseForbidden('You must be logged in to do that!')
    subscription = Subscription.get_current_for_user(request.user)
    if subscription:
        subscription.state = Subscription.STATE_0_TERMINATED
        subscription.save()
    processing_payment = get_object_or_None(Payment, user=request.user, status=Payment.STATUS_COMPLETED_BUT_UNCONFIRMED)
    if processing_payment:
        processing_payment.status = Payment.STATUS_FAILED
        processing_payment.save()
    return redirect('wechange-payments:overview')


@receiver(userprofile_ceated)
def delay_payment_popup_for_new_user(sender, profile, **kwargs):
    """ Delays the user's payment popup window by some time after a fresh registration """
    profile.settings[USERPROFILE_SETTING_POPUP_CLOSED] = now() + timedelta(days=settings.PAYMENTS_POPUP_DELAY_FOR_NEW_USERS_DAYS)
    profile.save(update_fields=['settings'])
