from django.urls import path

from . import views

urlpatterns = [
    path("healthz", views.health, name="health"),
]
