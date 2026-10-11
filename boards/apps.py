from django.apps import AppConfig


class BoardsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "boards"

    def ready(self):
        from django.contrib.auth.signals import user_logged_in

        from .models import Membership

        # Invitations are claimed the moment their person signs in.
        user_logged_in.connect(
            lambda sender, request, user, **kwargs: Membership.objects.claim_for(user),
            weak=False,
            dispatch_uid="claim_invitations",
        )
