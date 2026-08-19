"""
Django settings for legal_consultant project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-@8x4!$5^h9&2k#m$p7w@3v!q8l#n$b^5h&2k#m$p7w@3v!q8l#n$b^5'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Наше приложение
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'core.middleware.ForceSessionSaveMiddleware',  # 👈 ДОБАВИТЬ СЮДА
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'legal_consultant.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'core/templates',  # Добавляем папку с шаблонами
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media',
            ],
        },
    },
]

WSGI_APPLICATION = 'legal_consultant.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'core/static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (user uploaded files)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Логирование
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'debug.log',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
}
# ============ НАСТРОЙКИ СЕССИЙ ============

# Используем базу данных для сессий
SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# Время жизни сессии - 7 дней
SESSION_COOKIE_AGE = 604800

# НЕ закрывать сессию при закрытии браузера
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Сохранять сессию при каждом запросе (ВАЖНО!)
SESSION_SAVE_EVERY_REQUEST = True

# Имя cookie
SESSION_COOKIE_NAME = 'sessionid'

# Cookie работает на всем сайте
SESSION_COOKIE_PATH = '/'

# Безопасность (для разработки)
SESSION_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# ---------- ДОПОЛНИТЕЛЬНЫЕ НАСТРОЙКИ ----------

# Использовать кэш для сессий (ускоряет)
# SESSION_CACHE_ALIAS = 'default'

# Сериализация данных сессии
SESSION_SERIALIZER = 'django.contrib.sessions.serializers.JSONSerializer'

# ---------- НАСТРОЙКИ CSRF ----------

CSRF_COOKIE_NAME = 'csrftoken'
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_AGE = 604800  # 7 дней
CSRF_COOKIE_PATH = '/'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = False
CSRF_USE_SESSIONS = False
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:8000', 'http://localhost:8000']

# ---------- НАСТРОЙКИ АУТЕНТИФИКАЦИИ ----------

# Перенаправление после логина
LOGIN_URL = '/admin-login/'
LOGIN_REDIRECT_URL = '/admin-dashboard/'
LOGOUT_REDIRECT_URL = '/'

AI_TYPE = 'yandex'

# YandexGPT настройки
YANDEX_API_KEY = 'ajedhpmaapg71bcdf1sf'
YANDEX_FOLDER_ID = 'b1g1lod5i6u2oo5q4qlu'
YANDEX_MODEL = 'yandexgpt-lite'  # или 'yandexgpt-pro' для более мощной модели