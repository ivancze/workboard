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
    path("boards/<int:board_pk>/cards/new/", views.card_create, name="card_create"),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/", views.card_detail, name="card_detail"
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/edit/", views.card_edit, name="card_edit"
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/edit/<str:field>/",
        views.card_field,
        name="card_field",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/move/", views.card_move, name="card_move"
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/priority/",
        views.card_priority,
        name="card_priority",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/subtasks/",
        views.subtask_add,
        name="subtask_add",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/subtasks/<int:subtask_pk>/tick/",
        views.subtask_tick,
        name="subtask_tick",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/subtasks/<int:subtask_pk>/rename/",
        views.subtask_rename,
        name="subtask_rename",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/subtasks/<int:subtask_pk>/move/",
        views.subtask_shift,
        name="subtask_shift",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/subtasks/<int:subtask_pk>/delete/",
        views.subtask_delete,
        name="subtask_delete",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/archive/",
        views.card_archive,
        name="card_archive",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/restore/",
        views.card_restore,
        name="card_restore",
    ),
    path(
        "boards/<int:board_pk>/cards/<int:pk>/delete/",
        views.card_delete,
        name="card_delete",
    ),
    path(
        "boards/<int:board_pk>/stages/<int:pk>/archive/",
        views.stage_archive_cards,
        name="stage_archive_cards",
    ),
    path("boards/<int:board_pk>/archive/", views.board_archive, name="board_archive"),
    path("boards/<int:board_pk>/members/", views.board_members, name="board_members"),
    path(
        "boards/<int:board_pk>/members/invite/", views.member_invite, name="member_invite"
    ),
    path(
        "boards/<int:board_pk>/members/<int:pk>/make-owner/",
        views.member_make_owner,
        name="member_make_owner",
    ),
    path("boards/<int:board_pk>/leave/", views.board_leave, name="board_leave"),
    path("boards/<int:board_pk>/rename/", views.board_rename, name="board_rename"),
    path("boards/<int:board_pk>/description/", views.board_describe, name="board_describe"),
    path("boards/<int:board_pk>/pet/", views.board_pet, name="board_pet"),
    path("boards/<int:board_pk>/delete/", views.board_delete, name="board_delete"),
    path(
        "boards/<int:board_pk>/members/<int:pk>/remove/",
        views.member_remove,
        name="member_remove",
    ),
]
