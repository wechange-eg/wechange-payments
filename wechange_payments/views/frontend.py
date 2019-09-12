# -*- coding: utf-8 -*-

import logging

from annoying.functions import get_object_or_None
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls.base import reverse
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _
from django.views.generic.base import TemplateView, RedirectView
from django.views.generic.detail import DetailView

from cosinnus.utils.permissions import check_user_superuser
from cosinnus.utils.urls import get_non_cms_root_url, redirect_next_or
from cosinnus.views.mixins.group import RequireLoggedInMixin
from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT
from wechange_payments.forms import PaymentsForm
from wechange_payments.models import Subscription, Payment
from wechange_payments.payment import terminate_subscription


logger = logging.getLogger('wechange-payments')



class PaymentView(RequireLoggedInMixin, TemplateView):
    
    template_name = 'wechange_payments/payment_form.html'
    
    def _get_testform_initial(self):
        initial = {
            'payment_type': PAYMENT_TYPE_DIRECT_DEBIT,
            'amount': 2.0,
            'address':'Straße 73',
            'city': 'Berlin',
            'postal_code': 11111,
            'first_name': 'Hans',
            'last_name': 'Mueller',
            'email': 'saschanarr@gmail.com',
            'iban': 'DE34100500000710217340',
            'bic': 'BELADEBEXXX',
            'account_holder': 'Hans Mueller',
            'country': 'DE',
            'tos_accept': True,
        }
        return initial
    
    def dispatch(self, request, *args, **kwargs):
        active_subscription = Subscription.get_active_for_user(self.request.user)
        if active_subscription:
            return reverse('wechange-payments:my-subscription')
        return super(PaymentView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(PaymentView, self).get_context_data(*args, **kwargs)
        
        form = PaymentsForm()
        if settings.DEBUG:
            form = PaymentsForm(initial=self._get_testform_initial())
            
        context.update({
            'form': form,
        })
        return context

payment = PaymentView.as_view()


class PaymentSuccessView(RequireLoggedInMixin, DetailView):
    
    model = Payment
    template_name = 'wechange_payments/payment_success.html'
    
    def get_context_data(self, *args, **kwargs):
        context = super(PaymentSuccessView, self).get_context_data(*args, **kwargs)
        # must be owner of the payment
        if not self.object.user == self.request.user and not check_user_superuser(self.request.user):
            raise PermissionDenied()
        context.update({
            'payment': self.object,
        })
        return context

payment_success = PaymentSuccessView.as_view()




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
    
    template_name = 'wechange_payments/welcome_page.html'
    
    def get_redirect_url(self, *args, **kwargs):
        subscription = get_object_or_None(Subscription, user=self.request.user, state__in=[
            Subscription.STATE_1_CANCELLED_BUT_ACTIVE,
            Subscription.STATE_2_ACTIVE,
            Subscription.STATE_3_WATING_TO_BECOME_ACTIVE,
        ])
        if subscription:
            return reverse('wechange-payments:my-subscription')
        else:
            return reverse('wechange-payments:payment')
        
overview = OverviewView.as_view()


class MySubscriptionView(RequireLoggedInMixin, TemplateView):
    """ Shows informations about the current subscription and lets the user
        adjust the payment amount. """
    
    template_name = 'wechange_payments/my_subscription.html'
    
    def dispatch(self, request, *args, **kwargs):
        self.current_subscription = Subscription.get_current_for_user(self.request.user)
        self.waiting_subscription = Subscription.get_waiting_for_user(self.request.user)
        if not self.current_subscription and not self.past_subscriptions and not self.waiting_subscriptions:
            return redirect('wechange-payments:payment')
        return super(MySubscriptionView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(MySubscriptionView, self).get_context_data(*args, **kwargs)
        context.update({
            'current_subscription': self.current_subscription,
            'waiting_subscription': self.waiting_subscription,
        })
        return context
        
my_subscription = MySubscriptionView.as_view()


class PaymentInfosView(RequireLoggedInMixin, TemplateView):
    """ Shows informations about the current subscription and lets the user
        adjust the payment amount. """
    
    template_name = 'wechange_payments/payment_infos.html'
    
    def dispatch(self, request, *args, **kwargs):
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
    """ TODO: invoices view. """
    
    template_name = 'wechange_payments/invoices.html'
    
    def dispatch(self, request, *args, **kwargs):
        self.invoices = None # TODO
        if not self.invoices:
            return redirect('wechange-payments:payment')
        return super(MySubscriptionView, self).dispatch(request, *args, **kwargs)
    
    def get_context_data(self, *args, **kwargs):
        context = super(MySubscriptionView, self).get_context_data(*args, **kwargs)
        context.update({
            'invoices': self.invoices,
        })
        return context

invoices = InvoicesView.as_view()


class CancelSubscriptionView(RequireLoggedInMixin, TemplateView):
    
    template_name = 'wechange_payments/cancel_subscription.html'
    
    def dispatch(self, request, *args, **kwargs):
        current_subscription = Subscription.get_current_for_user(self.request.user)
        if not current_subscription:
            return redirect('wechange-payments:overview')
        return super(CancelSubscriptionView, self).dispatch(request, *args, **kwargs)
    
    def post(self, request, *args, **kwargs):
        """ Simply posting to this view will cancel the currently running subscription """
        try:
            success = terminate_subscription(request.user)
            if success:
                messages.success(_('Your Subscription was terminated.'))
                return redirect('wechange-payments:overview')
        except Exception as e:
            logger.error('Critical: Could not cancel a subscription!', extra={'exc': force_text(e)})
            messages.error(_('There was an error terminating your subscription! Please contact the customer support!'))
        return redirect('wechange-payments:overview')

cancel_subscription = CancelSubscriptionView.as_view()


