# -*- coding: utf-8 -*-
from django.apps import AppConfig


class WechangePaymentsAppConfig(AppConfig):

    name = 'wechange_payments'
    verbose_name = 'Wechange Payments'

    def ready(self):
        # connect all signal listeners
        import wechange_payments.hooks  # noqa

