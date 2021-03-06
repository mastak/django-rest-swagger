import os
from setuptools import setup
from rest_framework_swagger import VERSION


README = """
Django REST Swagger

An API documentation generator for Swagger UI and Django REST Framework version 2.3+

Installation
From pip:

pip install django-rest-swagger

Project @ https://github.com/marcgibbons/django-rest-swagger
Docs @ http://django-rest-swagger.readthedocs.org/
"""

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))
install_requires = [
    'django>=1.5',
    'djangorestframework>=2.3.5',
    'PyYAML>=3.10',
]

import platform

version = platform.python_version_tuple()
if version < ('2','7'):
    install_requires.append('importlib>=1.0.1')
    install_requires.append('ordereddict>=1.1')

setup(
    name='django-rest-swagger',
    version=VERSION,
    packages=['rest_framework_swagger'],
    package_data={'rest_framework_swagger': ['rest_framework_swagger/templates/rest_framework_swagger/*', 'rest_framework_swagger/static/rest_framework_swagger/*']},
    include_package_data=True,
    license='FreeBSD License',
    description='Swagger UI for Django REST Framework 2.3+',
    long_description=README,
    install_requires=install_requires,
    url='https://github.com/mzakabluk/django-rest-swagger.git',
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
    ],
)
