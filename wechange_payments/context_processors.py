# -*- coding: utf-8 -*-
from datetime import timedelta
import logging

from dateutil import parser
from django.utils.timezone import now

from cosinnus.core.middleware.cosinnus_middleware import LOGIN_URLS
from cosinnus.models.group import CosinnusPortal
from wechange_payments.conf import settings
from wechange_payments.models import Subscription


logger = logging.getLogger('wechange-payments')

def current_subscription(request):
    context = dict()
    # TODO: add invoices logic
    
    current_subscription = Subscription.get_current_for_user(request.user)
    context.update({
        'current_subscription': current_subscription,
        'invoices': [], # todo
    })
    # determine if payment popup should be shown
    if not current_subscription:
        try:
            if request.user.is_authenticated \
                    and request.META.get('HTTP_REFERER', '').startswith(CosinnusPortal.get_current().get_domain()) \
                    and not any([request.path.startswith(never_path) for never_path in LOGIN_URLS]):
                clicked_away_date = request.user.cosinnus_profile.settings.get('payment_popup_closed_date', None)
                threshold_date = now() - timedelta(days=settings.PAYMENTS_POPUP_SHOW_AGAIN_DAYS)
                if clicked_away_date is None or parser.parse(clicked_away_date) < threshold_date:
                    context.update({
                        'show_payment_popup': True,
                    })
                        
        except Exception as e:
            logger.error('Error in `context_processory.show_payment_popup`: %s' % e, extra={'exception': e})
    
    return context
