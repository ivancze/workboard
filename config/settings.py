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
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts",
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
    "allauth.account.middleware.AccountMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "allauth.account.auth_backends.AuthenticationBackend",
]

LOGIN_URL = "/accounts/google/login/"
LOGIN_REDIRECT_URL = "/"
ACCOUNT_LOGOUT_REDIRECT_URL = "/"

# Google is the only way in, so local accounts are switched off entirely: no
# password is stored, accepted, or asked for. See ADR 0002.
SOCIALACCOUNT_ONLY = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_ADAPTER = "accounts.adapter.SocialAccountAdapter"

# There are no usernames; email is the identity everywhere.
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*"]
# Google has already verified the address, and the system cannot send mail.
ACCOUNT_EMAIL_VERIFICATION = "none"

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        # Credentials inline rather than in a database SocialApp row, so there
        # is no admin interface to maintain and no fixture to seed.
        "APP": {
            "client_id": env("GOOGLE_OAUTH_CLIENT_ID", default=""),
            "secret": env("GOOGLE_OAUTH_CLIENT_SECRET", default=""),
            "key": "",
        },
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
    }
}

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
