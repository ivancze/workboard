import sys

import django
from django.db import connection
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
