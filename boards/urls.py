from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("boards/new/", views.create_board, name="board_create"),
    path("boards/<int:pk>/", views.board_detail, name="board_detail"),
    path("boards/<int:board_pk>/stages/", views.stage_list, name="stage_list"),
    path("boards/<int:board_pk>/stages/new/", views.stage_create, name="stage_create"),
    path(
        "boards/<int:board_pk>/stages/<int:pk>/rename/",
        views.stage_rename,
        name="stage_rename",
    ),
    path(
        "boards/<int:board_pk>/stages/<int:pk>/move/",
        views.stage_shift,
        name="stage_shift",
    ),
    path(
        "boards/<int:board_pk>/stages/<int:pk>/delete/",
        views.stage_delete,
        name="stage_delete",
    ),
    path(
        "boards/<int:board_pk>/stages/<int:stage_pk>/cards/new/",
        views.create_card,
        name="card_create",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/", views.card_detail, name="card_detail"
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/edit/", views.card_edit, name="card_edit"
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/move/", views.card_move, name="card_move"
    ),
]
