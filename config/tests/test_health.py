from django.test import TestCase


class HealthPageTests(TestCase):
    def test_renders(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

    def test_reports_a_migrated_database(self):
        response = self.client.get("/")

        self.assertGreater(response.context["applied_migrations"], 0)

    def test_reports_the_database_it_actually_reached(self):
        response = self.client.get("/")

        self.assertIn("PostgreSQL", response.context["database_version"])
