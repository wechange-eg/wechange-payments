# -*- coding: utf-8 -*-

from wechange_payments.conf import settings

import logging
from django.views.generic.base import TemplateView
from cosinnus.views.mixins.group import RequireLoggedInMixin
from wechange_payments.forms import PaymentsForm
from cosinnus.utils.urls import get_non_cms_root_url, redirect_next_or

logger = logging.getLogger('wechange-payments')



class PaymentView(RequireLoggedInMixin, TemplateView):
    
    template_name = 'wechange_payments/payment_form.html'
    
    def _get_testform_initial(self):
        initial = {
            'payment_type': 'dd',
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

