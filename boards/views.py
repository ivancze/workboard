import copy

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import BoardForm, CardForm, NewCardForm
from .models import Board, Card


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

    return render(
        request,
        "boards/board_detail.html",
        {
            "board": board,
            "stages": board.stages.prefetch_related("cards"),
            # No auto ids: the form repeats once per Stage, and its label
            # wraps its input instead.
            "form": NewCardForm(auto_id=False),
        },
    )


@login_required
def create_card(request, board_pk, stage_pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    stage = get_object_or_404(board.stages, pk=stage_pk)
    if request.method != "POST":
        return redirect("board_detail", pk=board.pk)

    form = NewCardForm(request.POST)
    if form.is_valid():
        Card.objects.create_at_end(
            stage=stage, title=form.cleaned_data["title"], creator=request.user
        )
    return redirect("board_detail", pk=board.pk)


@login_required
def card_detail(request, board_pk, pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    card = get_object_or_404(
        Card.objects.filter(stage__board=board).select_related("creator"), pk=pk
    )

    # The form gets its own copy so a rejected edit cannot leak into the saved
    # Card the page displays alongside it.
    form = CardForm(request.POST or None, instance=copy.copy(card))
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("card_detail", board_pk=board.pk, pk=card.pk)

    return render(
        request, "boards/card_detail.html", {"board": board, "card": card, "form": form}
    )
