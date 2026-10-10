from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("boards/new/", views.create_board, name="board_create"),
    path("boards/<int:pk>/", views.board_detail, name="board_detail"),
]
