from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

from .models import User


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Fills the display name from Google so nobody has to type it.

    Prefilling matters because the field is then populated the moment someone
    joins, rather than sitting blank until they bother to set it.
    """

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        if not user.display_name:
            user.display_name = self.google_display_name(sociallogin, data)
        return user

    @staticmethod
    def google_display_name(sociallogin, data):
        """The person's name as Google writes it.

        Google's provider normalises its response into `data` as `first_name`
        and `last_name` only, discarding the profile's own `name`. So the name
        Google actually displays has to be read back out of the raw payload,
        with the split fields as a fallback.
        """
        raw = getattr(sociallogin.account, "extra_data", None) or {}
        name = (raw.get("name") or "").strip()
        if not name:
            parts = (data.get("first_name"), data.get("last_name"))
            name = " ".join(part.strip() for part in parts if part and part.strip())
        return name[: User._meta.get_field("display_name").max_length]
