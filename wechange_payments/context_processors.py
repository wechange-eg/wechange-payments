# -*- coding: utf-8 -*-
from wechange_payments.models import Subscription


def active_subscription(request):
    context = dict()
    context['active_subscription'] = Subscription.get_active_for_user(request.user)
    return context
