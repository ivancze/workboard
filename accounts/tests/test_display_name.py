from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.test import RequestFactory, TestCase

from accounts.adapter import SocialAccountAdapter
from accounts.models import User

# The shape Google's userinfo endpoint actually returns, as recorded from a
# real sign-in. Note `name` alongside the split pair: the provider keeps only
# the pair when it normalises this, which is the trap these tests guard.
GOOGLE_PAYLOAD = {
    "sub": "1",
    "email": "ada@example.com",
    "email_verified": True,
    "name": "Ada Lovelace",
    "given_name": "Ada",
    "family_name": "Lovelace",
    "picture": "https://example.com/a.jpg",
}

# The same person as a provider in a family-name-first locale would render
# them. The two sources disagree here, which is what makes precedence testable
# at all: with GOOGLE_PAYLOAD both routes produce the same string, so a test
# using it would pass whichever source won.
FAMILY_FIRST_PAYLOAD = GOOGLE_PAYLOAD | {"name": "Lovelace Ada"}


def populate_from(payload, existing_display_name=""):
    """Run the adapter exactly as allauth would, for a given provider payload.

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
    def test_prefers_the_split_pair_from_the_normalised_data(self):
        user = populate_from(FAMILY_FIRST_PAYLOAD)

        self.assertEqual(user.display_name, "Ada Lovelace")

    def test_falls_back_to_the_providers_own_rendering(self):
        payload = FAMILY_FIRST_PAYLOAD | {"given_name": None, "family_name": None}

        user = populate_from(payload)

        self.assertEqual(user.display_name, "Lovelace Ada")

    def test_uses_whichever_half_of_the_pair_exists(self):
        payload = GOOGLE_PAYLOAD | {"name": None, "family_name": None}

        user = populate_from(payload)

        self.assertEqual(user.display_name, "Ada")

    def test_survives_a_profile_with_no_name_at_all(self):
        payload = GOOGLE_PAYLOAD | {
            "name": None,
            "given_name": None,
            "family_name": None,
        }

        user = populate_from(payload)

        self.assertEqual(user.display_name, "")

    def test_does_not_overwrite_a_name_the_user_chose(self):
        user = populate_from(GOOGLE_PAYLOAD, existing_display_name="Ada")

        self.assertEqual(user.display_name, "Ada")

    def test_truncates_an_absurd_name_rather_than_failing_signup(self):
        payload = GOOGLE_PAYLOAD | {"given_name": "A" * 400}

        user = populate_from(payload)

        self.assertEqual(len(user.display_name), 150)

    def test_the_normalised_data_carries_no_single_name_field(self):
        """Pins the provider behaviour that makes the fallback necessary: if a
        future allauth starts passing `name` through, this test says so."""
        request = RequestFactory().get("/")
        provider = get_adapter().get_provider(request, "google")

        data = provider.extract_common_fields(GOOGLE_PAYLOAD)

        self.assertNotIn("name", data)
