# -*- coding: utf-8 -*-
from wechange_payments.models import Subscription


def current_subscription(request):
    context = dict()
    # TODO: add invoices logic
    context.update({
        'current_subscription': Subscription.get_current_for_user(request.user),
        'invoices': [], # todo
    })
    return context
