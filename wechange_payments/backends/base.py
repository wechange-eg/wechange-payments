# -*- coding: utf-8 -*-

from wechange_payments.conf import settings
from django.core.exceptions import ImproperlyConfigured


class BaseBackend(object):
    
    required_setting_keys = []
    
    def __init__(self):
        for key in self.required_setting_keys:
            if not getattr(settings, key, None):
                raise ImproperlyConfigured('Setting "%s" is required for backend "%s"!' 
                            % (key, self.__class__.__name__))


