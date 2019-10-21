# -*- coding: utf-8 -*-

from wechange_payments.conf import PAYMENT_TYPE_DIRECT_DEBIT

TEST_DATA_SEPA_PAYMENT_FORM = {
    'payment_type': PAYMENT_TYPE_DIRECT_DEBIT,
    'amount': 2.0,
    'address':'Straße 73',
    'city': 'Berlin',
    'postal_code': 11111,
    'first_name': 'Hans',
    'last_name': 'Mueller',
    'email': 'test@mail.com',
    'iban': 'DE34100500000710217340',
    'bic': 'BELADEBEXXX',
    'account_holder': 'Hans Mueller',
    'country': 'DE',
    'tos_check': True,
    'privacy_policy_check': True,
}