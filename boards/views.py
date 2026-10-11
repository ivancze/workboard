import copy

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST, require_safe

from .forms import BoardForm, CardForm, MoveCardForm, StageForm
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
    totals = board.cards.filter(archived_at__isnull=True).aggregate(
        effort_total=Sum("effort"),
        unestimated=Count("pk", filter=Q(effort__isnull=True)),
    )

    return {
        "board": board,
        "stages": stages,
        "totals": totals,
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
def card_create(request, board_pk):
    """A blank Card, with every field but only the title required. It goes to
    the bottom of the board's first Stage, the start of the workflow."""
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    form = CardForm(request.POST or None, board=board)
    if request.method == "POST" and form.is_valid():
        card = Card.objects.create_in_first_stage(
            board=board, creator=request.user, **form.cleaned_data
        )
        messages.success(request, f"Added {card.title} to {card.stage.name}.")
        return redirect("board_detail", pk=board.pk)

    return render(
        request,
        "boards/card_create.html",
        {"board": board, "form": form, "first_stage": board.stages.first()},
    )


def get_card(request, board_pk, pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    # Through the Card's own board, so archived Cards, which have no Stage,
    # are found the same way.
    card = get_object_or_404(
        board.cards.select_related("creator", "assignee", "stage", "archived_from"),
        pk=pk,
    )
    return board, card


def back_to(request, default):
    """Where an action posted from several pages returns: the page given in
    `next`, if it is on this site, or else `default`."""
    url = request.POST.get("next")
    if url and url_has_allowed_host_and_scheme(
        url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(url)
    return redirect(default)


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
        try:
            # Its own savepoint, so a failure leaves the request's
            # transaction usable for the check below.
            with transaction.atomic():
                form.instance.save(update_fields=[*form.Meta.fields, "updated_at"])
        except DatabaseError:
            # Django's answer when the row to update is gone: deleted while
            # this edit was open.
            if Card.objects.filter(pk=card.pk).exists():
                raise
            raise Http404("That Card has just been deleted.")
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
    except Card.DoesNotExist:
        raise Http404("That Card has just been archived.")

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


@require_POST
@login_required
def card_archive(request, board_pk, pk):
    board, card = get_card(request, board_pk, pk)
    try:
        card.archive()
    except Stage.DoesNotExist:
        raise Http404("That Card's Stage has just been deleted.")
    except Card.DoesNotExist:
        raise Http404("That Card has just been deleted.")
    messages.success(request, f"Archived {card.title}.")
    return back_to(request, reverse("board_detail", args=[board.pk]))


@require_POST
@login_required
def card_restore(request, board_pk, pk):
    board, card = get_card(request, board_pk, pk)
    try:
        card.restore()
    except Card.DoesNotExist:
        raise Http404("That Card has just been deleted.")
    messages.success(request, f"Restored {card.title} to {card.stage.name}.")
    return back_to(request, reverse("board_detail", args=[board.pk]))


@require_POST
@login_required
def card_delete(request, board_pk, pk):
    board, card = get_card(request, board_pk, pk)
    card.delete()
    messages.success(request, f"Deleted {card.title}.")
    return back_to(request, reverse("board_detail", args=[board.pk]))


@require_safe
@login_required
def board_archive(request, board_pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    cards = board.cards.filter(archived_at__isnull=False).select_related(
        "archived_from"
    ).order_by("-archived_at", "-id")
    return render(
        request,
        "boards/board_archive.html",
        {"board": board, "cards": cards, "first_stage": board.stages.first()},
    )


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
def stage_archive_cards(request, board_pk, pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    stage = get_object_or_404(board.stages, pk=pk)
    try:
        expected = int(request.POST.get("expected", ""))
    except ValueError:
        expected = 0
    if expected < 1:
        return HttpResponseBadRequest("Expected must be the number of Cards confirmed.")
    try:
        archived = stage.archive_cards(expected)
    except ValidationError as error:
        messages.error(request, error.message)
    except Stage.DoesNotExist:
        raise Http404("That Stage has just been deleted.")
    else:
        messages.success(
            request,
            f"Archived {archived} Card{'s' if archived != 1 else ''} from {stage.name}.",
        )
    return redirect("board_detail", pk=board.pk)


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
