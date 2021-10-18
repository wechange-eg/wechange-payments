# -*- coding: utf-8 -*-
from datetime import timedelta
import logging

from dateutil import parser
from django.utils.timezone import now

from cosinnus.core.middleware.cosinnus_middleware import LOGIN_URLS
from cosinnus.models.group import CosinnusPortal
from wechange_payments.conf import settings
from wechange_payments.models import Subscription,\
    USERPROFILE_SETTING_POPUP_CLOSED, USERPROFILE_SETTING_POPUP_CLOSED_TIMES,\
    USERPROFILE_SETTING_POPUP_USER_IS_NEW
from cosinnus.utils.group import get_cosinnus_group_model


logger = logging.getLogger('wechange-payments')

def current_subscription(request):
    # enabled only if payments are enabled
    if not getattr(settings, 'COSINNUS_PAYMENTS_ENABLED', False) and not \
            (getattr(settings, 'COSINNUS_PAYMENTS_ENABLED_ADMIN_ONLY', False) and request.user.is_superuser):
        return {}
    
    context = dict()
    
    current_subscription = Subscription.get_current_for_user(request.user)
    suspended_subscription = Subscription.get_suspended_for_user(request.user)
    context.update({
        'current_subscription': current_subscription,
        'suspended_subscription': suspended_subscription,
    })
    # determine if payment popup should be shown
    if not current_subscription:
        try:
            excepted_urls = LOGIN_URLS + ['/account/', '/payments/',]
            if request.user.is_authenticated \
                    and request.META.get('HTTP_REFERER', '').startswith(CosinnusPortal.get_current().get_domain()) \
                    and not any([request.path.startswith(never_path) for never_path in excepted_urls]):
                profile = request.user.cosinnus_profile
                clicked_away_date = profile.settings.get(USERPROFILE_SETTING_POPUP_CLOSED, None)
                threshold_date = now() - timedelta(days=settings.PAYMENTS_POPUP_SHOW_AGAIN_DAYS)
                if clicked_away_date is None or parser.parse(clicked_away_date) < threshold_date:
                    do_add_popup = True
                    
                    # if the user would be shown a payments popup, but they are in any premium conference
                    # that is younger than 1y, we postpone their nag-popup time by 1y after the conference ends
                    if settings.COSINNUS_CONFERENCES_ENABLED:
                        from cosinnus.models.conference import CosinnusConferencePremiumBlock
                        premium_conference_delay = timedelta(weeks=52)
                        
                        user_group_ids = get_cosinnus_group_model().objects.get_for_user_pks(request.user)
                        blocks_from_user_groups = CosinnusConferencePremiumBlock.objects.filter(conference__id__in=user_group_ids)
                        block_group_ids = list(set(blocks_from_user_groups.values_list('conference_id', flat=True)))
                        permanently_premium_groups = get_cosinnus_group_model().objects.filter(id__in=user_group_ids, is_premium_permanently=True)
                        permanently_premium_group_ids = list(set(permanently_premium_groups.values_list('id', flat=True)))
                        
                        sorted_premium_groups = get_cosinnus_group_model().objects.filter(id__in=block_group_ids+permanently_premium_group_ids)\
                                .filter(to_date__gte=now()-premium_conference_delay).order_by('-to_date')
                        if sorted_premium_groups.count() > 0:
                            # a premium group of less than year's end date exists, postpone for the newest
                            do_add_popup = False
                            postpone_date = (sorted_premium_groups[0].to_date + premium_conference_delay) - timedelta(days=settings.PAYMENTS_POPUP_SHOW_AGAIN_DAYS)
                            # snooze popup into the future
                            profile = request.user.cosinnus_profile
                            profile.settings[USERPROFILE_SETTING_POPUP_CLOSED] = str(postpone_date)
                            profile.save(update_fields=['settings'])
                            
                    if do_add_popup:
                        context.update({
                            'show_payment_popup': True,
                            'payment_popup_times_closed_before': profile.settings.get(USERPROFILE_SETTING_POPUP_CLOSED_TIMES, 0),
                            'payment_popup_user_registered_after_payments': profile.settings.get(USERPROFILE_SETTING_POPUP_USER_IS_NEW, False),
                        })
                        
        except Exception as e:
            logger.error('Error in `context_processory.show_payment_popup`: %s' % e, extra={'exception': e})
            if settings.DEBUG:
                raise
    
    return context
