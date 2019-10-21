# -*- coding: utf-8 -*-
from django.apps import AppConfig


class WechangePaymentsAppConfig(AppConfig):

    name = 'wechange_payments'
    verbose_name = 'Wechange Payments'

    def ready(self):
        # connect all signal listeners
        from cosinnus.conf import settings
        if not getattr(settings, 'TESTING', False):
            import wechange_payments.hooks  # noqa

