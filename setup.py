from setuptools import setup
import os

from wechange_payments import VERSION as PAYMENTS_VERSION

name = 'wechange-payments'
package = 'wechange_payments'

url = 'https://github.com/wechange-eg/wechange-payments'
author = 'Sascha Narr'
author_email = 'saschanarr@wechange.de'
license_ = 'GNU'
description = 'Payment implementions for Wechange'
long_description = open('README.rst').read()


def get_packages(package):
    """
    Return root package and all sub-packages.
    """
    return [dirpath for dirpath, dirnames, filenames in os.walk(package)
            if os.path.exists(os.path.join(dirpath, '__init__.py'))]


def get_package_data(package):
    """
    Return all files under the root package, that are not in a
    package themselves.
    """
    walk = [(dirpath.replace(package + os.sep, '', 1), filenames)
            for dirpath, dirnames, filenames in os.walk(package)
            if not os.path.exists(os.path.join(dirpath, '__init__.py'))]

    filepaths = []
    for base, filenames in walk:
        filepaths.extend([os.path.join(base, filename)
                          for filename in filenames])
    return {package: filepaths}


setup(
    name=name,
    version=PAYMENTS_VERSION,
    url=url,
    license=license_,
    description=description,
    long_description=long_description,
    author=author,
    author_email=author_email,
    packages=get_packages(package),
    package_data=get_package_data(package),
    install_requires=[
        'django-countries==7.2.1',
        'schwifty==2018.9.1',
    ],
)


