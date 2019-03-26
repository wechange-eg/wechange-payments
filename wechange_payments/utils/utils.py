# -*- coding: utf-8 -*-

from importlib import import_module
    
    
def resolve_class(path_to_class):
    modulename, _, klass = path_to_class.rpartition('.')
    module = import_module(modulename)
    cls = getattr(module, klass, None)
    if cls is None:
        raise ImportError("Cannot import class %s from %s" % (
            klass, path_to_class))
    return cls




