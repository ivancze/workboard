import copy

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q, Sum
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe

from .forms import BoardForm, CardForm, MoveCardForm, NewCardForm
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


def board_context(board):
    """Everything the board's Stages and totals need, for the page and for
    the fragment that replaces them after a drag."""
    # Effort totals are summed by the database, so a large board costs the
    # same two queries as a small one. Each total travels with the count of
    # Unestimated Cards it could not include.
    stages = board.stages.annotate(
        effort_total=Sum("cards__effort"),
        unestimated=Count("cards", filter=Q(cards__effort__isnull=True)),
    ).prefetch_related(
        Prefetch("cards", queryset=Card.objects.select_related("assignee"))
    )
    totals = Card.objects.filter(stage__board=board).aggregate(
        effort_total=Sum("effort"),
        unestimated=Count("pk", filter=Q(effort__isnull=True)),
    )

    return {
        "board": board,
        "stages": stages,
        "totals": totals,
        # No auto ids: the form repeats once per Stage, and its label wraps its
        # input instead.
        "form": NewCardForm(auto_id=False),
    }


@login_required
def board_detail(request, pk):
    # Scoped by membership, so a non-member gets a 404 rather than a 403: the
    # response does not reveal whether the board exists at all.
    board = get_object_or_404(Board.objects.for_user(request.user), pk=pk)
    return render(request, "boards/board_detail.html", board_context(board))


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


def get_card(request, board_pk, pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    card = get_object_or_404(
        Card.objects.filter(stage__board=board).select_related("creator", "assignee"),
        pk=pk,
    )
    return board, card


# Read-only: edits go to card_edit, so a stray POST here is refused rather than
# silently dropped.
@require_safe
@login_required
def card_detail(request, board_pk, pk):
    board, card = get_card(request, board_pk, pk)
    return render(request, "boards/card_detail.html", {"board": board, "card": card})


@login_required
def card_edit(request, board_pk, pk):
    board, card = get_card(request, board_pk, pk)

    # The form gets its own copy so a rejected edit cannot leak into the saved
    # Card the page names in its heading.
    form = CardForm(request.POST or None, instance=copy.copy(card), board=board)
    if request.method == "POST" and form.is_valid():
        # Only the form's own fields. A full save would write back the Stage
        # and position as loaded, undoing a move made while this was open.
        form.instance.save(update_fields=[*form.Meta.fields, "updated_at"])
        return redirect("card_detail", board_pk=board.pk, pk=card.pk)

    return render(
        request, "boards/card_edit.html", {"board": board, "card": card, "form": form}
    )


@require_POST
@login_required
def card_move(request, board_pk, pk):
    board, card = get_card(request, board_pk, pk)
    form = MoveCardForm(request.POST, board=board)
    if "stage" in form.errors:
        raise Http404("No such Stage on this board.")
    if not form.is_valid():
        return HttpResponseBadRequest("Position must be a whole number from 0.")

    card.move_to(form.cleaned_data["stage"], form.cleaned_data["position"])
    # A drag sends this with htmx and gets the board back, fresh from the
    # database, to replace what the page shows. A plain form gets a redirect.
    if request.headers.get("HX-Request"):
        return render(request, "components/board.html", board_context(board))
    return redirect("board_detail", pk=board.pk)
