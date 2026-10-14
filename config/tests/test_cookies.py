import re

from django.test import Client, TestCase
from django.urls import reverse

from boards.models import Board
from boards.tests.test_cards import a_user


class OnlyTheSessionCookieTests(TestCase):
    """Firebase Hosting forwards only the cookie named __session to Cloud Run.

    Any other cookie the site sets reaches the browser but never comes back,
    so everything a request needs has to travel in the session.
    """

    def strip_all_but_the_session(self, client):
        for name in list(client.cookies):
            if name != "__session":
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

