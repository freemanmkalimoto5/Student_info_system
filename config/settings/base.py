"""
Shared settings. development.py and production.py both import * from here
and override only what needs to differ (DEBUG, DATABASES, ALLOWED_HOSTS, etc).
"""
from pathlib import Path
from decouple import config

# Base directory = project root (three levels up from this file:
# config/settings/base.py -> config/settings -> config -> root)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Local apps
    'apps.students',
    'apps.qrcodes',
    'apps.verification',
    'apps.accounts',
    'apps.pocketmoney',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.AdminProfileMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        # Project-wide templates folder, in addition to each app's own
        # templates/ folder (Django checks both because APP_DIRS=True).
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.accounts.context_processors.site_settings',
                'apps.accounts.context_processors.role_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database is defined per-environment (development.py / production.py)

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Dar_es_Salaam'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JS, images shipped with the app)
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'  # collectstatic target for production

# Media files (student photos, generated QR codes, generated ID card PDFs)
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Base URL used when building the verification link encoded in QR codes.
# In development this is your local server; in production, set SITE_URL
# in .env to your real domain, e.g. https://school.example.com
SITE_URL = config('SITE_URL', default='http://127.0.0.1:8000')

# WhatsApp notifications via a self-hosted WAHA server
# (https://waha.devlike.pro/). Leave WAHA_BASE_URL blank to disable
# sending entirely — the app logs what it would have sent instead of
# failing. Numbers with a leading 0 are assumed local and get
# WHATSAPP_COUNTRY_CODE prepended (default: Tanzania, 255).
WAHA_BASE_URL = config('WAHA_BASE_URL', default='')
WAHA_API_KEY = config('WAHA_API_KEY', default='')
WAHA_SESSION = config('WAHA_SESSION', default='default')
WHATSAPP_COUNTRY_CODE = config('WHATSAPP_COUNTRY_CODE', default='255')

# Where "login required" redirects to, used once verification/admin views
# are locked down later.
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'students:list'
