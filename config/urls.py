from django.urls import include, path

from . import views

urlpatterns = [
    # Not /healthz: Cloud Run's front end keeps that exact path for itself.
    path("health", views.health, name="health"),
    path("accounts/", include("allauth.urls")),
    path("", include("accounts.urls")),
    path("", include("boards.urls")),
]
