"""PythonAnywhere WSGI entry point for KabayaniTrack.

Copy this file's contents into the WSGI configuration file shown on the
PythonAnywhere "Web" tab, then replace the three placeholders below.
"""

import os
import sys

# PythonAnywhere project location.
project_home = os.path.expanduser('~/KabayaniTrack')
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.environ['DJANGO_SETTINGS_MODULE'] = 'mysite.settings'
os.environ['DJANGO_DEBUG'] = '0'
os.environ['DJANGO_SECRET_KEY'] = os.environ.get('DJANGO_SECRET_KEY', '').strip() or 'django-insecure-dev-only-change-me'
os.environ['DJANGO_ALLOWED_HOSTS'] = 'Fluxxify.pythonanywhere.com'
os.environ['DJANGO_CSRF_TRUSTED_ORIGINS'] = 'https://Fluxxify.pythonanywhere.com'

from django.core.wsgi import get_wsgi_application  # noqa: E402

application = get_wsgi_application()
