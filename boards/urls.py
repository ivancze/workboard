from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("boards/new/", views.create_board, name="board_create"),
    path("boards/<int:pk>/", views.board_detail, name="board_detail"),
    path(
        "boards/<int:board_pk>/stages/<int:stage_pk>/cards/new/",
        views.create_card,
        name="card_create",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/", views.card_detail, name="card_detail"
    ),
]
