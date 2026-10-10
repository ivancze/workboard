from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BoardForm
from .models import Board


def home(request):
    """A sign-in prompt, or the boards this user belongs to."""
    if not request.user.is_authenticated:
        return render(request, "boards/home.html")

    return render(
        request,
        "boards/home.html",
        {"boards": Board.objects.for_user(request.user), "form": BoardForm()},
    )


@login_required
def create_board(request):
    if request.method != "POST":
        return redirect("home")

    form = BoardForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "boards/home.html",
            {"boards": Board.objects.for_user(request.user), "form": form},
        )

    board = Board.objects.create_with_owner(
        name=form.cleaned_data["name"], owner=request.user
    )
    return redirect("board_detail", pk=board.pk)


@login_required
def board_detail(request, pk):
    # Scoped by membership, so a non-member gets a 404 rather than a 403: the
    # response does not reveal whether the board exists at all.
    board = get_object_or_404(Board.objects.for_user(request.user), pk=pk)

    return render(request, "boards/board_detail.html", {"board": board})
