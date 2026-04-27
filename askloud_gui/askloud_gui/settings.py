"""
Django settings for Askloud GUI.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Askloud data root — where data/ and config/ directories live.
# Defaults to the parent of this Django project (the cloud_inventory_claude repo root).
ASKLOUD_BASE_DIR = os.environ.get(
    "ASKLOUD_BASE_DIR",
    str(BASE_DIR.parent)
)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "askloud-gui-dev-secret-key-change-in-production")

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() != "false"

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "askloud_gui.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "askloud_gui.wsgi.application"

DATABASES = {}

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
