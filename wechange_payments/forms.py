# -*- coding: utf-8 -*-

from django import forms
from django.utils.translation import gettext_lazy as _

from django_countries.fields import CountryField
from wechange_payments.conf import settings, PAYMENT_TYPE_CREDIT_CARD,\
    PAYMENT_TYPE_PAYPAL, PAYMENT_TYPE_DIRECT_DEBIT
from wechange_payments.models import DebitPeriodMixin
    
from schwifty import IBAN, BIC


PAYMENT_CHOICES = {
    PAYMENT_TYPE_DIRECT_DEBIT: _('Direct Debit (SEPA)'),
    PAYMENT_TYPE_CREDIT_CARD: _('Credit Card'),
    PAYMENT_TYPE_PAYPAL: _('Paypal'),
}


class PaymentsForm(forms.Form):
    """ This form is being used for pre-filling values, and for validation.
        All requests are sent straight to the API from frontend. """
    
    payment_type = forms.ChoiceField(choices=[(type, PAYMENT_CHOICES[type]) for type in settings.PAYMENTS_ACCEPTED_PAYMENT_METHODS])
    amount = forms.FloatField()
    debit_period = forms.ChoiceField(choices=DebitPeriodMixin.DEBIT_PERIOD_CHOICES)
    
    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.EmailField()
    address = forms.CharField()
    city = forms.CharField()
    postal_code = forms.CharField()
    country = CountryField().formfield()
    
    is_organisation = forms.BooleanField(required=False)
    organisation = forms.CharField(required=False)
    
    tos_check = forms.BooleanField(required=True)
    
    if settings.COSINNUS_SIGNUP_REQUIRES_PRIVACY_POLICY_CHECK:
        privacy_policy_check = forms.BooleanField(required=True)
    
    # payment-specific-fields
    iban = forms.CharField()
    bic = forms.CharField()
    account_holder = forms.CharField()
    
    def clean_iban(self):
        input_iban = self.cleaned_data['iban']
        try:
            iban_obj = IBAN(input_iban)
        except ValueError:
            raise forms.ValidationError(_('The IBAN you entered does not seem to be correct!'))
        return iban_obj.compact
    
    def clean_bic(self):
        input_bic = self.cleaned_data['bic']
        try:
            bic_obj = BIC(input_bic)
        except ValueError:
            raise forms.ValidationError(_('The BIC you entered does not seem to be correct!'))
        return bic_obj.compact
    