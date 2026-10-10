from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class SignedOutHomeTests(TestCase):
    def test_offers_google_sign_in(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sign in with Google")

    def test_leaks_no_template_syntax(self):
        """Django's {# #} comments are single-line only, so a multi-line one
        renders as visible text rather than disappearing."""
        response = self.client.get("/")

        self.assertNotContains(response, "{#")
        self.assertNotContains(response, "{%")

    def test_offers_nothing_else(self):
        response = self.client.get("/")

        self.assertNotContains(response, 'type="password"')
        self.assertNotContains(response, "Sign up")


class SignedInHomeTests(TestCase):
    def test_greets_by_display_name(self):
        user = User.objects.create_user(email="ada@example.com", display_name="Ada")
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, "Hello, Ada")

    def test_falls_back_to_email_when_unnamed(self):
        user = User.objects.create_user(email="ada@example.com")
        self.client.force_login(user)

        response = self.client.get("/")

        self.assertContains(response, "ada@example.com")


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ada@example.com", display_name="Ada")

    def test_requires_signing_in(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 302)

    def test_changes_the_name_used_everywhere(self):
        self.client.force_login(self.user)

        self.client.post(reverse("profile"), {"display_name": "Ada L"})

        self.user.refresh_from_db()
        self.assertEqual(self.user.display_name, "Ada L")
        self.assertContains(self.client.get("/"), "Hello, Ada L")


class NoCredentialsTests(TestCase):
    def test_no_usable_password_is_ever_stored(self):
        user = User.objects.create_user(email="ada@example.com")

        self.assertFalse(user.has_usable_password())

    def test_email_is_the_identity_so_it_must_be_unique(self):
        User.objects.create_user(email="ada@example.com")

        with self.assertRaises(IntegrityError):
            User.objects.create_user(email="ada@example.com")

    def test_the_user_model_has_no_username(self):
        field_names = {f.name for f in User._meta.get_fields()}

        self.assertNotIn("username", field_names)
        self.assertEqual(User.USERNAME_FIELD, "email")


class SignOutTests(TestCase):
    def test_signing_out_returns_to_the_signed_out_state(self):
        user = User.objects.create_user(email="ada@example.com", display_name="Ada")
        self.client.force_login(user)
        self.assertContains(self.client.get("/"), "Hello, Ada")

        self.client.post(reverse("account_logout"))

        response = self.client.get("/")
        self.assertContains(response, "Sign in with Google")
        self.assertNotContains(response, "Hello, Ada")

    def test_signing_out_needs_a_post_not_a_link(self):
        """A GET logout would let any page sign a user out with an <img> tag."""
        user = User.objects.create_user(email="ada@example.com")
        self.client.force_login(user)

        self.client.get(reverse("account_logout"))

        self.assertContains(self.client.get("/"), "ada@example.com")
