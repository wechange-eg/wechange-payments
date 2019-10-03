# -*- coding: utf-8 -*-

from django import template
from wechange_payments.models import Invoice

register = template.Library()

@register.filter
def has_invoices(user):
    """ Template filter to check if the given user has any invoices """
    return Invoice.objects.filter(user=user).count() > 0
