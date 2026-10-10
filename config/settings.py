from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)

# Render publishes the service's own hostname. Reading it means the deployed
# host is never hardcoded, which matters because Render appends a suffix when
# the requested subdomain is already taken by someone else.
RENDER_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default="")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = []
if RENDER_HOSTNAME:
    ALLOWED_HOSTS.append(RENDER_HOSTNAME)
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_HOSTNAME}")

DATABASES = {"default": env.db("DATABASE_URL")}

# No persistent connections by default. Neon bills compute by the hour and
# suspends an idle compute after five minutes; its docs do not say whether an
# open-but-idle connection counts as activity, so this avoids depending on the
# answer. A connection handshake per request costs little in-region. Raise
# CONN_MAX_AGE if the database stops being billed for uptime.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=0)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = DATABASES["default"]["CONN_MAX_AGE"] > 0

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "OPTIONS": {"context_processors": []},
    }
]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Compressed but not hashed. Hashed filenames would need a manifest built
    # by collectstatic, and the development bind mount hides the one baked into
    # the image, so templates would fail locally for files the manifest lacks.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Gated on an explicit flag rather than `not DEBUG`, because Django forces
# DEBUG off while running tests, and an SSL redirect would turn every test
# request into a 301.
HTTPS_ONLY = env.bool("HTTPS_ONLY", default=False)
SECURE_SSL_REDIRECT = HTTPS_ONLY
SESSION_COOKIE_SECURE = HTTPS_ONLY
CSRF_COOKIE_SECURE = HTTPS_ONLY
# Deliberately an hour, not a year: HSTS cannot be revoked for the hostname
# once a browser has seen it, so a short window stays recoverable.
SECURE_HSTS_SECONDS = 3600 if HTTPS_ONLY else 0
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Both concern HSTS on a hostname we do not own. includeSubDomains would cover
# subdomains of an onrender.com name that will never exist, and preloading
# requires controlling the registered domain, which Render does. Silenced so a
# genuinely new warning from `check --deploy` stands out.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
