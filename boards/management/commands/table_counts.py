from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Print every table's row count, to compare two databases after a copy."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            for table in sorted(connection.introspection.table_names(cursor)):
                cursor.execute(f"select count(*) from {connection.ops.quote_name(table)}")
                self.stdout.write(f"{table} {cursor.fetchone()[0]}")
