import copy

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q, Sum
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_safe

from .forms import BoardForm, CardForm, MoveCardForm, NewCardForm, StageForm
from .models import Board, Card, Stage


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
    # Ordered explicitly: Django drops Meta.ordering from aggregating queries,
    # and the Stages would come back in whatever order the database likes.
    stages = board.stages.annotate(
        effort_total=Sum("cards__effort"),
        unestimated=Count("cards", filter=Q(cards__effort__isnull=True)),
    ).order_by("position", "id").prefetch_related(
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
    context = board_context(board)
    # Left by a Move button's redirect, for the next board page only: a reload
    # plays nothing. A Card is on one board, so another board ignores it.
    context["landed"] = request.session.pop("landed", None)
    return render(request, "boards/board_detail.html", context)


@login_required
def create_card(request, board_pk, stage_pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    stage = get_object_or_404(board.stages, pk=stage_pk)
    if request.method != "POST":
        return redirect("board_detail", pk=board.pk)

    form = NewCardForm(request.POST)
    if form.is_valid():
        try:
            Card.objects.create_at_end(
                stage=stage, title=form.cleaned_data["title"], creator=request.user
            )
        except Stage.DoesNotExist:
            raise Http404("That Stage has just been deleted.")
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

    target = form.cleaned_data["stage"]
    origin = card.stage_id
    try:
        card.move_to(target, form.cleaned_data["position"])
    except Stage.DoesNotExist:
        raise Http404("That Stage has just been deleted.")

    # A Card arriving in a different Stage animates on the board, and arriving
    # in the board's last Stage, its "done", also celebrates.
    landed = None
    if target.pk != origin:
        last = board.stages.order_by("position", "id").last()
        landed = {"card": card.pk, "celebrate": target.pk == last.pk}

    # A drag sends this with htmx and gets the board back, fresh from the
    # database, to replace what the page shows. A plain form gets a redirect.
    if request.headers.get("HX-Request"):
        return render(
            request, "components/board.html", {**board_context(board), "landed": landed}
        )
    if landed:
        request.session["landed"] = landed
    return redirect("board_detail", pk=board.pk)


def render_stages(request, board, *, failed=None, failed_form=None, refusal=None, add_form=None):
    """The Edit stages page. A refused change comes back as `failed`, the
    Stage concerned, with its bound form or the reason a delete was refused,
    so the error shows on that Stage's own row."""
    rows = []
    # Ordered explicitly, as in board_context: the Count drops Meta.ordering.
    for stage in board.stages.annotate(card_count=Count("cards")).order_by("position", "id"):
        form = StageForm(initial={"name": stage.name}, prefix=f"stage{stage.pk}")
        if stage == failed:
            rows.append((stage, failed_form or form, refusal))
        else:
            rows.append((stage, form, None))
    return render(
        request,
        "boards/stage_list.html",
        {"board": board, "rows": rows, "add_form": add_form or StageForm(prefix="new")},
        status=400 if failed or add_form else 200,
    )


@require_safe
@login_required
def stage_list(request, board_pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    return render_stages(request, board)


@require_POST
@login_required
def stage_create(request, board_pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    form = StageForm(request.POST, prefix="new")
    if form.is_valid():
        try:
            board.add_stage(form.cleaned_data["name"])
            return redirect("stage_list", board_pk=board.pk)
        except ValidationError as error:
            form.add_error("name", error)
    return render_stages(request, board, add_form=form)


@require_POST
@login_required
def stage_rename(request, board_pk, pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    stage = get_object_or_404(board.stages, pk=pk)
    form = StageForm(request.POST, prefix=f"stage{stage.pk}")
    if form.is_valid():
        try:
            stage.rename(form.cleaned_data["name"])
            return redirect("stage_list", board_pk=board.pk)
        except ValidationError as error:
            form.add_error("name", error)
    return render_stages(request, board, failed=stage, failed_form=form)


@require_POST
@login_required
def stage_delete(request, board_pk, pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    stage = get_object_or_404(board.stages, pk=pk)
    try:
        stage.delete_if_empty()
    except ValidationError as error:
        return render_stages(request, board, failed=stage, refusal=error.message)
    return redirect("stage_list", board_pk=board.pk)


@require_POST
@login_required
def stage_shift(request, board_pk, pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    stage = get_object_or_404(board.stages, pk=pk)
    step = {"up": -1, "down": 1}.get(request.POST.get("direction"))
    if step is None:
        return HttpResponseBadRequest("Direction must be up or down.")
    try:
        stage.shift(step)
    except Stage.DoesNotExist:
        raise Http404("That Stage has just been deleted.")
    return redirect("stage_list", board_pk=board.pk)
