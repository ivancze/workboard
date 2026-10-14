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

# Every other provider lists the addresses the site is served on here, comma
# separated: Cloud Run's, Firebase's, and later the custom domain.
PUBLIC_HOSTNAMES = env.list("PUBLIC_HOSTNAMES", default=[])
if RENDER_HOSTNAME:
    PUBLIC_HOSTNAMES.append(RENDER_HOSTNAME)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[]) + PUBLIC_HOSTNAMES
CSRF_TRUSTED_ORIGINS = [f"https://{hostname}" for hostname in PUBLIC_HOSTNAMES]

# Firebase Hosting passes requests to Cloud Run addressed to Cloud Run's own
# hostname, with the one the browser used in X-Forwarded-Host. Sign-in builds
# Google's callback address from the host, so behind Firebase it has to come
# from that header. ALLOWED_HOSTS still checks whatever it says.
USE_X_FORWARDED_HOST = env.bool("USE_X_FORWARDED_HOST", default=False)

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
    # Before staticfiles: WhiteNoise serves static in development too, marking
    # it max-age=0, where runserver's handler leaves browsers to cache the
    # stylesheet heuristically and show a stale one after each rebuild.
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.forms",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts",
    "boards",
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

# Widgets render through project templates, so form controls carry the design
# system's classes rather than browser defaults. See docs/frontend.md.
FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

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
                "boards.context_processors.board_filter",
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
# static/css/app.css is built by bin/tailwind and never committed.
STATICFILES_DIRS = [BASE_DIR / "static"]
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

# Firebase Hosting, in front of Cloud Run, forwards one cookie only, and it must
# be named __session. So the CSRF token and messages live in the session rather
# than cookies of their own, and nothing may add another cookie. Render keeps
# Django's name until the custom domain switch, since renaming the cookie signs
# everyone out. See docs/deployment.md.
SESSION_COOKIE_NAME = env("SESSION_COOKIE_NAME", default="sessionid")
CSRF_USE_SESSIONS = True
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"
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
# The team's timezone. A Due date is a plain date, but deciding that one "has
# passed" needs a today, and on UTC a Card would turn overdue up to eight hours
# late for a team in Kuala Lumpur.
TIME_ZONE = "Asia/Kuala_Lumpur"
