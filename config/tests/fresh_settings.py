import json
import os
import subprocess
import sys

# Variables these tests set themselves, so none leak in from the container.
CONTROLLED = {"ALLOWED_HOSTS", "PUBLIC_HOSTNAMES"}


def settings_with(names, **variables):
    """Read settings in a fresh process, since each process reads them once."""
    environment = {key: value for key, value in os.environ.items() if key not in CONTROLLED}
    read = (
        "import json; from django.conf import settings; "
        f"print(json.dumps([getattr(settings, name) for name in {list(names)!r}]))"
    )
    output = subprocess.run(
        [sys.executable, "-c", read],
        env=environment | {"DJANGO_SETTINGS_MODULE": "config.settings"} | variables,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return json.loads(output)
