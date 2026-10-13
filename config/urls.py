from django.urls import include, path

from . import views

urlpatterns = [
    path("healthz", views.health, name="health"),
    path("livez", views.liveness, name="liveness"),
    path("accounts/", include("allauth.urls")),
    path("", include("accounts.urls")),
    path("", include("boards.urls")),
]
