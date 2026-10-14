from django.test import SimpleTestCase

from .fresh_settings import settings_with


def hosts_with(**variables):
    return settings_with(["ALLOWED_HOSTS", "CSRF_TRUSTED_ORIGINS"], **variables)


class PublicHostnameTests(SimpleTestCase):
    def test_every_public_hostname_is_allowed_and_trusted_over_https(self):
        allowed, trusted = hosts_with(PUBLIC_HOSTNAMES="workboard.example.run.app,example.web.app")

        self.assertEqual(allowed, ["workboard.example.run.app", "example.web.app"])
        self.assertEqual(trusted, ["https://workboard.example.run.app", "https://example.web.app"])

    def test_development_hosts_are_allowed_but_never_trusted_as_origins(self):
        allowed, trusted = hosts_with(ALLOWED_HOSTS="localhost,127.0.0.1")

        self.assertEqual(allowed, ["localhost", "127.0.0.1"])
        self.assertEqual(trusted, [])
