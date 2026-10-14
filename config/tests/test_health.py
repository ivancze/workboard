from django.test import TestCase


class HealthPageTests(TestCase):
    def test_renders(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)

    def test_reports_a_migrated_database(self):
        response = self.client.get("/health")

        self.assertGreater(response.context["applied_migrations"], 0)

    def test_reports_the_database_it_actually_reached(self):
        response = self.client.get("/health")

        self.assertIn("PostgreSQL", response.context["database_version"])


class LivenessTests(TestCase):
    def test_responds(self):
        response = self.client.get("/livez")

        self.assertEqual(response.status_code, 200)

    def test_never_touches_the_database(self):
        # Render probes this every few seconds. One query each time would keep
        # Neon's compute awake around the clock, past the free plan's hours.
        with self.assertNumQueries(0):
            self.client.get("/livez")
