import re

from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase
from django.urls import reverse

from boards.models import Board
from boards.tests.test_cards import a_user

from .fresh_settings import settings_with


class OnlyTheSessionCookieTests(TestCase):
    """Firebase Hosting forwards only the cookie named __session to Cloud Run.

    Any other cookie the site sets reaches the browser but never comes back,
    so everything a request needs has to travel in the session.
    """

    def strip_all_but_the_session(self, client):
        for name in list(client.cookies):
            if name != settings.SESSION_COOKIE_NAME:
                del client.cookies[name]

    def test_a_form_and_its_message_work_with_the_session_cookie_alone(self):
        ada = a_user()
        board = Board.objects.create_with_owner(name="Housework", owner=ada)
        client = Client(enforce_csrf_checks=True)
        client.force_login(ada)
        new = reverse("card_create", args=[board.pk])

        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', client.get(new).content.decode()).group(1)
        self.strip_all_but_the_session(client)
        response = client.post(new, {"title": "Buy milk", "csrfmiddlewaretoken": token})
        self.assertEqual(response.status_code, 302)
        self.strip_all_but_the_session(client)

        self.assertContains(client.get(response.url), "Added Buy milk to To Do.")


class SessionCookieNameTests(SimpleTestCase):
    def test_is_djangos_own_unless_configured(self):
        # Render keeps this until the custom domain switch: renaming the
        # cookie signs everyone out.
        self.assertEqual(settings_with(["SESSION_COOKIE_NAME"]), ["sessionid"])

    def test_comes_from_configuration(self):
        self.assertEqual(settings_with(["SESSION_COOKIE_NAME"], SESSION_COOKIE_NAME="__session"), ["__session"])
