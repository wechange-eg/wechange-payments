# -*- coding: utf-8 -*-

from wechange_payments.conf import settings, PAYMENT_TYPE_DIRECT_DEBIT

import logging
from django.views.generic.base import TemplateView, RedirectView
from cosinnus.views.mixins.group import RequireLoggedInMixin
from wechange_payments.forms import PaymentsForm
from cosinnus.utils.urls import get_non_cms_root_url, redirect_next_or
from wechange_payments.models import Subscription, Payment
from annoying.functions import get_object_or_None
from django.urls.base import reverse
from django.views.generic.detail import DetailView
from cosinnus.utils.permissions import check_user_superuser
from django.core.exceptions import PermissionDenied

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
        and to the subscription list page if there is an active subscription. """
    
    template_name = 'wechange_payments/welcome_page.html'
    
    def get_redirect_url(self, *args, **kwargs):
        subscription = get_object_or_None(Subscription, user=self.request.user, state__in=[
            Subscription.STATE_1_CANCELLED_BUT_ACTIVE,
            Subscription.STATE_2_ACTIVE,
            Subscription.STATE_3_WATING_TO_BECOME_ACTIVE,
        ])
        if subscription:
            return reverse('wechange-payments:subscriptions')
        else:
            return reverse('wechange-payments:payment')
        
overview = OverviewView.as_view()


class SubscriptionsView(RequireLoggedInMixin, TemplateView):
    """ Redirects to the payment view if the user has no active subscriptions
        and to the subscription list page if there is an active subscription. """
    
    template_name = 'wechange_payments/subscriptions.html'
    
    def get_context_data(self, *args, **kwargs):
        context = super(SubscriptionsView, self).get_context_data(*args, **kwargs)
        active_subscription = Subscription.get_active_for_user(self.request.user)
        past_subscriptions = Subscription.objects.filter(user=self.request.user, state=Subscription.STATE_0_TERMINATED)
        waiting_subscriptions = Subscription.objects.filter(user=self.request.user, state=Subscription.STATE_3_WATING_TO_BECOME_ACTIVE)
        
        context.update({
            'active_subscription': active_subscription,
            'past_subscriptions': past_subscriptions,
            'waiting_subscriptions': waiting_subscriptions,
        })
        return context
        
subscriptions = SubscriptionsView.as_view()

