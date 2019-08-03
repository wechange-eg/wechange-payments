# -*- coding: utf-8 -*-

from django import forms
from django.utils.translation import ugettext_lazy as _

from django_countries.fields import CountryField
from wechange_payments.conf import settings


PAYMENT_CHOICES = {
    'cc': _('Credit Card'),
    'dd': _('Direct Debit'),
    'paypal': _('Paypal'),
}


class PaymentsForm(forms.Form):
    """ This form is being used only for pre-filling values, and not for posting or validating.
        All requests are sent straight to the API from frontend. """
    
    payment_type = forms.ChoiceField(choices=[(type, PAYMENT_CHOICES[type]) for type in settings.PAYMENTS_ACCEPTED_PAYMENT_METHODS])
    amount = forms.FloatField()
    address = forms.CharField()
    city = forms.CharField()
    postal_code = forms.IntegerField()
    country = CountryField().formfield()
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.EmailField()
    
    tos_accept = forms.BooleanField(required=True)
    
    # payment-specific-fields
    iban = forms.CharField()
    bic = forms.CharField()
    account_holder = forms.CharField()
    
    
    
    