from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .models import User


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Fills the display name from the provider so nobody has to type it.

    Prefilling matters because the field is then populated the moment someone
    joins, rather than sitting blank until they bother to set it.
    """

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        if not user.display_name:
            user.display_name = self.extract_display_name(sociallogin, data)
        return user

    @staticmethod
    def extract_display_name(sociallogin, data):
        """A name to call this person by, preferring portable sources.

        `data` is allauth's provider-agnostic vocabulary, so reading the split
        name pair from it works for any provider we might add later. The raw
        payload is the fallback: it carries the provider's own rendering of the
        name, which is the only source that survives a profile where the split
        fields are absent.

        The order is a deliberate trade. Joining the pair imposes
        given-then-family order, which is wrong for the many locales that put
        the family name first, and the raw rendering would get that right. We
        take portability first and accept that, because every provider fills
        the pair while only some supply a single name at all.
        """
        parts = (data.get("first_name"), data.get("last_name"))
        name = " ".join(part.strip() for part in parts if part and part.strip())

        if not name:
            raw = getattr(sociallogin.account, "extra_data", None) or {}
            name = (raw.get("name") or "").strip()

        return name[: User._meta.get_field("display_name").max_length]
