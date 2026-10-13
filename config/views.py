import sys

import django
from django.db import connection
from django.http import HttpResponse
from django.shortcuts import render


def health(request):
    """Render proof that the application reached a migrated database.

    Reading django_migrations means the page cannot render unless Postgres is
    both reachable and migrated, which is the whole point of the skeleton.
    """
    with connection.cursor() as cursor:
        cursor.execute("select count(*) from django_migrations")
        (applied_migrations,) = cursor.fetchone()
        cursor.execute("select version()")
        (database_version,) = cursor.fetchone()

    return render(
        request,
        "health.html",
        {
            "applied_migrations": applied_migrations,
            "database_version": database_version,
            "django_version": django.get_version(),
            "python_version": sys.version.split()[0],
        },
    )


def liveness(request):
    """Answer Render's health check without touching the database.

    Render probes every few seconds, and any query keeps Neon's compute from
    suspending, which on the free plan's CU-hours runs out mid-month. The
    pre-deploy migrate has already proved the database is reachable.
    """
    return HttpResponse("ok", content_type="text/plain")
