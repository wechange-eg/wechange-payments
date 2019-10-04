# -*- coding: utf-8 -*-

import hashlib
from importlib import import_module
from os import path
from uuid import uuid4

from django.utils.encoding import force_text

from cosinnus.utils.files import get_cosinnus_media_file_folder
from wechange_payments.conf import settings


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


