# -*- coding: utf-8 -*-

from wechange_payments.conf import settings

import logging
from django.views.generic.base import TemplateView
from cosinnus.views.mixins.group import RequireLoggedInMixin
from wechange_payments.forms import PaymentsForm

logger = logging.getLogger('wechange-payments')



class PaymentView(RequireLoggedInMixin, TemplateView):
    
    template_name = 'wechange_payments/payment_form.html'
    
    def get_context_data(self, *args, **kwargs):
        context = super(PaymentView, self).get_context_data(*args, **kwargs)
        context.update({
            'form': PaymentsForm(initial={'country': 'de'}),
        })
        return context

payment = PaymentView.as_view()
