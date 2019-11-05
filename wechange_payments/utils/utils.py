# -*- coding: utf-8 -*-

import hashlib
from importlib import import_module
from os import path
from uuid import uuid4

from django.utils.encoding import force_text

from cosinnus.utils.files import get_cosinnus_media_file_folder
from wechange_payments.conf import settings
from django.contrib.auth import get_user_model


def resolve_class(path_to_class):
    modulename, _, klass = path_to_class.rpartition('.')
    module = import_module(modulename)
    cls = getattr(module, klass, None)
    if cls is None:
        raise ImportError("Cannot import class %s from %s" % (
            klass, path_to_class))
    return cls


def _get_invoice_filename(instance, filename, folder_type='invoices', base_folder='payments'):
    _, ext = path.splitext(filename)
    filedir = path.join(get_cosinnus_media_file_folder(), base_folder, folder_type)
    my_uuid = force_text(uuid4())
    name = '%s%s%s' % (settings.SECRET_KEY, my_uuid , filename)
    newfilename = 'invoice_' + hashlib.sha1(name.encode('utf-8')).hexdigest() + ext
    return path.join(filedir, newfilename)


def send_admin_mail_notification(subject, content):
    """ Sends a very simple mail to all admins """
    from cosinnus.models.group import CosinnusPortal
    from cosinnus.core.mail import send_mail_or_fail
    
    template = 'wechange_payments/utils/email_blank_template.html'
    admins = get_user_model().objects.exclude(is_active=False).\
                        filter(id__in=CosinnusPortal.get_current().admins)
    for user in admins:
        send_mail_or_fail(user.email, subject, template, {'content': content})
