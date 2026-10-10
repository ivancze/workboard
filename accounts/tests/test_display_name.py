from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.test import RequestFactory, TestCase

from accounts.adapter import SocialAccountAdapter
from accounts.models import User

# The shape Google's userinfo endpoint actually returns, as recorded from a
# real sign-in. Note `name` alongside the split fields: the provider keeps only
# the split pair when it normalises this, which is the bug this file guards.
GOOGLE_PAYLOAD = {
    "sub": "1",
    "email": "ada@example.com",
    "email_verified": True,
    "name": "Ada Lovelace",
    "given_name": "Ada",
    "family_name": "Lovelace",
    "picture": "https://example.com/a.jpg",
}


def populate_from(payload, existing_display_name=""):
    """Run the adapter exactly as allauth would, for a given Google payload.

    `data` is produced by asking allauth's own provider to normalise the
    payload, rather than by hand, so the test cannot drift from reality the way
    a fabricated dict can.
    """
    request = RequestFactory().get("/")
    provider = get_adapter().get_provider(request, "google")
    data = provider.extract_common_fields(payload)

    sociallogin = SocialLogin(
        user=User(display_name=existing_display_name),
        account=SocialAccount(provider="google", uid=payload["sub"], extra_data=payload),
    )
    return SocialAccountAdapter().populate_user(request, sociallogin, data)


class DisplayNamePrefillTests(TestCase):
    def test_uses_the_name_google_displays(self):
        user = populate_from(GOOGLE_PAYLOAD)

        self.assertEqual(user.display_name, "Ada Lovelace")

    def test_the_normalised_data_alone_does_not_carry_the_name(self):
        """Pins the provider behaviour that caused the original bug: if a future
        allauth starts passing `name` through, this test is the one that says so."""
        request = RequestFactory().get("/")
        provider = get_adapter().get_provider(request, "google")

        data = provider.extract_common_fields(GOOGLE_PAYLOAD)

        self.assertNotIn("name", data)

    def test_falls_back_to_joining_the_split_names(self):
        payload = GOOGLE_PAYLOAD | {"name": None}

        user = populate_from(payload)

        self.assertEqual(user.display_name, "Ada Lovelace")

    def test_survives_a_profile_with_no_name_at_all(self):
        payload = GOOGLE_PAYLOAD | {"name": None, "given_name": None, "family_name": None}

        user = populate_from(payload)

        self.assertEqual(user.display_name, "")

    def test_does_not_overwrite_a_name_the_user_chose(self):
        user = populate_from(GOOGLE_PAYLOAD, existing_display_name="Ada")

        self.assertEqual(user.display_name, "Ada")

    def test_truncates_an_absurdly_long_name_rather_than_failing_signup(self):
        payload = GOOGLE_PAYLOAD | {"name": "A" * 400}

        user = populate_from(payload)

        self.assertEqual(len(user.display_name), 150)
