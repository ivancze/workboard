import json
import os
import subprocess
import sys

from django.test import SimpleTestCase

READ_HOSTS = (
    "import json; from django.conf import settings; "
    "print(json.dumps([settings.ALLOWED_HOSTS, settings.CSRF_TRUSTED_ORIGINS]))"
)


def hosts_with(**variables):
    """Settings are read once per process, so each case starts a fresh one."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"ALLOWED_HOSTS", "PUBLIC_HOSTNAMES", "RENDER_EXTERNAL_HOSTNAME"}
    }
    output = subprocess.run(
        [sys.executable, "-c", READ_HOSTS],
        env=environment | {"DJANGO_SETTINGS_MODULE": "config.settings"} | variables,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(output)


class PublicHostnameTests(SimpleTestCase):
    def test_every_public_hostname_is_allowed_and_trusted_over_https(self):
        allowed, trusted = hosts_with(PUBLIC_HOSTNAMES="workboard.example.run.app,example.web.app")

        self.assertEqual(allowed, ["workboard.example.run.app", "example.web.app"])
        self.assertEqual(trusted, ["https://workboard.example.run.app", "https://example.web.app"])

    def test_renders_own_hostname_still_counts(self):
        allowed, trusted = hosts_with(RENDER_EXTERNAL_HOSTNAME="workboard.onrender.com")

        self.assertEqual(allowed, ["workboard.onrender.com"])
        self.assertEqual(trusted, ["https://workboard.onrender.com"])

    def test_development_hosts_are_allowed_but_never_trusted_as_origins(self):
        allowed, trusted = hosts_with(ALLOWED_HOSTS="localhost,127.0.0.1")

        self.assertEqual(allowed, ["localhost", "127.0.0.1"])
        self.assertEqual(trusted, [])
