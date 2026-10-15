"""Django settings for Office Jukebox project.

Compatible with Python 3.10+, Django 5.x, Neon PostgreSQL, Supabase, and WhiteNoise.
"""

from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file if present
load_dotenv(BASE_DIR / ".env")

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "django-insecure-office-jukebox-change-in-production-^9*1)k@8s3&v2!q5z",
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "True").strip().lower() in ("true", "1", "yes")

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("ALLOWED_HOSTS", "*").split(",")
    if host.strip()
]

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "music",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "jukebox.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "music.context_processors.jukebox_context",
            ],
        },
    },
]

WSGI_APPLICATION = "jukebox.wsgi.application"
ASGI_APPLICATION = "jukebox.asgi.application"

# Database configuration: PostgreSQL (Neon / Supabase) with SQLite fallback
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=True if "neon.tech" in DATABASE_URL or "supabase.co" in DATABASE_URL else False,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cache configuration (in-memory caching for search queries and rate limiting)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "office-jukebox-cache",
        "TIMEOUT": 900,  # 15 minutes default
    }
}

# Session settings
SESSION_COOKIE_NAME = "office_jukebox_session"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 days
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True

# CSRF settings
csrf_origins = os.getenv("CSRF_TRUSTED_ORIGINS", "")
if csrf_origins:
    CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in csrf_origins.split(",") if origin.strip()]
else:
    CSRF_TRUSTED_ORIGINS = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]

# YouTube Data API v3 configuration
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()

# Reverse proxy & IP detection settings
# When hosted behind reverse proxies (Render, AWS ALB, Cloudflare, NGINX, ngrok),
# specify how many proxy hops to trust when parsing X-Forwarded-For.
NUM_PROXIES = int(os.getenv("NUM_PROXIES", "1"))
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Referrer Policy for YouTube Embeds & API
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Production security headers
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
