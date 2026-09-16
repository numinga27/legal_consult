"""Production settings; persistent data and secrets live outside release directories."""
import os
from .settings import *  # noqa: F403

DEBUG = False
SECRET_KEY = os.environ['DJANGO_SECRET_KEY']
ALLOWED_HOSTS = os.environ['DJANGO_ALLOWED_HOSTS'].split(',')
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.sqlite3',
    'NAME': os.environ['DJANGO_DB_PATH'],
    'OPTIONS': {'timeout': 30},
    'TEST': {'NAME': ':memory:'},
}}
STATIC_ROOT = os.environ['DJANGO_STATIC_ROOT']
MEDIA_ROOT = os.environ['DJANGO_MEDIA_ROOT']
CSRF_TRUSTED_ORIGINS = os.environ.get('DJANGO_CSRF_ORIGINS', '').split(',')
SESSION_COOKIE_SECURE = os.environ.get('DJANGO_HTTPS', '0') == '1'
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
RELEASE_SHA = os.environ.get('APP_RELEASE', 'unknown')
YANDEX_API_KEY = os.environ.get('YANDEX_API_KEY', '')
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'handlers': {'console': {'class': 'logging.StreamHandler'}},
           'root': {'handlers': ['console'], 'level': 'WARNING'}}
