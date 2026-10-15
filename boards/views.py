import copy
import random

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.views.decorators.http import require_POST, require_safe

from accounts.models import User

from .forms import (
    BoardDescriptionForm,
    BoardForm,
    BoardPetForm,
    CardForm,
    CardPriorityForm,
    DeleteBoardForm,
    InviteForm,
    MoveCardForm,
    StageForm,
)
from .models import Board, Card, Membership, Stage, lock_membership

# Shown under a board's name while it has no Board description, a different
# one on each visit. Never stored: it belongs to the product, not the board.
PLAYFUL_DESCRIPTIONS = [
    "Let them cook",
    "On top of things",
    "One card at a time",
    "Making it happen",
    "Busy little bees",
    "Small steps, big wins",
    "Things are moving",
    "Progress over perfection",
    "Getting stuff done",
    "All hands on deck",
]


def home(request):
    """A sign-in prompt, or the boards this user belongs to."""
    if not request.user.is_authenticated:
        return render(request, "boards/home.html")

    # Also claimed at sign-in. Here too, because a sign-in lasts weeks and an
    # invitation made meanwhile would otherwise wait for the next one.
    Membership.objects.claim_for(request.user)
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


def filter_query(request):
    """The board's filter as a query string to carry along ("?assignee=me"),
    or "" with none. Every way back to the board keeps it."""
    value = request.GET.get("assignee", "")
    return f"?{urlencode({'assignee': value})}" if value else ""


def board_url(board, request):
    return reverse("board_detail", args=[board.pk]) + filter_query(request)


class AssigneeFilter:
    """The board narrowed to one Assignee's Cards: `?assignee=me`, the viewer;
    `unassigned`; or a Member's id. Hidden Cards are only out of view, and
    the board's totals still count them.

    A value that names no Member of this board, such as someone since
    removed, filters nothing and sets `unknown`, so the board says so.
    """

    def __init__(self, request, board):
        self.value = request.GET.get("assignee", "")
        self.lookup = None
        self.unknown = False
        if self.value == "me":
            self.lookup = {"assignee": request.user}
        elif self.value == "unassigned":
            self.lookup = {"assignee__isnull": True}
        elif self.value:
            member = (
                board.memberships.filter(user_id=self.value, user__isnull=False).first()
                if self.value.isdigit()
                else None
            )
            if member:
                self.lookup = {"assignee_id": member.user_id}
            else:
                self.value, self.unknown = "", True

    def cards(self):
        return Q(**self.lookup)

    def stage_cards(self):
        return Q(**{f"cards__{field}": value for field, value in self.lookup.items()})


def board_context(board, request):
    """Everything the board's Stages and totals need, for the page and for
    the fragment that replaces them after a drag, narrowed by its filter."""
    shown = AssigneeFilter(request, board)
    cards = Card.objects.select_related("assignee")
    # Effort totals are summed by the database, so a large board costs the
    # same two queries as a small one. Each total travels with the count of
    # Unestimated Cards it could not include.
    # Ordered explicitly: Django drops Meta.ordering from aggregating queries,
    # and the Stages would come back in whatever order the database likes.
    stages = board.stages.annotate(
        effort_total=Sum("cards__effort"),
        unestimated=Count("cards", filter=Q(cards__effort__isnull=True)),
        card_count=Count("cards"),
    ).order_by("position", "id")
    on_board = board.cards.filter(archived_at__isnull=True)
    totals = on_board.aggregate(
        effort_total=Sum("effort"),
        unestimated=Count("pk", filter=Q(effort__isnull=True)),
    )
    shown_totals = None
    if shown.lookup:
        # Beside the board's totals, never instead of them: filtered figures
        # carry their own label, so they can't pass for the board's.
        cards = cards.filter(shown.cards())
        here = shown.stage_cards()
        stages = stages.annotate(
            shown_effort=Sum("cards__effort", filter=here),
            shown_unestimated=Count("cards", filter=here & Q(cards__effort__isnull=True)),
            shown_count=Count("cards", filter=here),
        )
        shown_totals = on_board.filter(shown.cards()).aggregate(
            effort_total=Sum("effort"),
            unestimated=Count("pk", filter=Q(effort__isnull=True)),
        )

    return {
        "board": board,
        "stages": stages.prefetch_related(Prefetch("cards", queryset=cards)),
        "totals": totals,
        "shown_totals": shown_totals,
        "assignee_filter": shown,
        "members": User.objects.filter(memberships__board=board).order_by(
            "display_name", "email"
        ),
    }


@login_required
def board_detail(request, pk):
    # Scoped by membership, so a non-member gets a 404 rather than a 403: the
    # response does not reveal whether the board exists at all.
    board = get_object_or_404(Board.objects.for_user(request.user), pk=pk)
    context = board_context(board, request)
    if context["assignee_filter"].unknown:
        messages.info(
            request, "That person is not a Member of this board, so every Card is shown."
        )
    # Left by a Move button's redirect, for the next board page only: a reload
    # plays nothing. A Card is on one board, so another board ignores it.
    context["landed"] = request.session.pop("landed", None)
    context["is_owner"] = board.is_owner(request.user)
    context["playful"] = random.choice(PLAYFUL_DESCRIPTIONS)
    return render(request, "boards/board_detail.html", context)


@login_required
def card_create(request, board_pk):
    """A blank Card, with every field but only the title required. It goes to
    the bottom of the board's first Stage, the start of the workflow."""
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    form = CardForm(request.POST or None, board=board)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                lock_assignee(board, form)
                card = Card.objects.create_in_first_stage(
                    board=board, creator=request.user, **form.cleaned_data
                )
        except Membership.DoesNotExist:
            pass  # the form now says why
        except Board.DoesNotExist:
            raise Http404("That board has just been deleted.")
        else:
            messages.success(request, f"Added {card.title} to {card.stage.name}.")
            return redirect(board_url(board, request))

    return render(
        request,
        "boards/card_create.html",
        {"board": board, "form": form, "first_stage": board.stages.first()},
    )


def lock_assignee(board, form):
    """Lock the chosen Assignee's membership while their Card is saved, so a
    removal can't slip in between. If they were removed since the form was
    checked, say so on the field and raise Membership.DoesNotExist."""
    assignee = form.cleaned_data.get("assignee")
    if assignee is None:
        return
    try:
        lock_membership(board, assignee)
    except Membership.DoesNotExist:
        form.add_error("assignee", f"{assignee.name} is no longer a Member of this board.")
        raise


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
    # The board's last Stage reads as finished, so an overdue Card there loses
    # its red, as on its tile. An archived Card has no Stage.
    in_last_stage = card.stage_id is not None and card.stage_id == board.stages.last().pk
    return render(
        request,
        "boards/card_detail.html",
        {"board": board, "card": card, "in_last_stage": in_last_stage},
    )


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
                lock_assignee(board, form)
                form.instance.save(update_fields=[*form.Meta.fields, "updated_at"])
        except Membership.DoesNotExist:
            return render(
                request,
                "boards/card_edit.html",
                {"board": board, "card": card, "form": form},
                status=400,
            )
        except DatabaseError:
            # Django's answer when the row to update is gone: deleted while
            # this edit was open.
            if Card.objects.filter(pk=card.pk).exists():
                raise
            raise Http404("That Card has just been deleted.")
        return redirect(
            reverse("card_detail", args=[board.pk, card.pk]) + filter_query(request)
        )

    return render(
        request, "boards/card_edit.html", {"board": board, "card": card, "form": form}
    )


@require_POST
@login_required
def card_priority(request, board_pk, pk):
    """Priority from the dropdown on a Card's tile, by any Member, as on the
    edit page. With htmx it answers with the board, swapped in place as after
    a drag. Without JavaScript, it goes back to the board."""
    board, card = get_card(request, board_pk, pk)
    form = CardPriorityForm(request.POST, instance=card)
    if not form.is_valid():
        return HttpResponseBadRequest("No such Priority.")
    # Only this field: a full save would write back whatever else was loaded.
    form.instance.save(update_fields=["priority", "updated_at"])
    if request.headers.get("HX-Request"):
        return render(request, "components/board.html", board_context(board, request))
    return redirect(board_url(board, request))


@require_POST
@login_required
def card_move(request, board_pk, pk):
    board, card = get_card(request, board_pk, pk)
    form = MoveCardForm(request.POST, board=board)
    if "stage" in form.errors:
        raise Http404("No such Stage on this board.")
    if not form.is_valid():
        return HttpResponseBadRequest("A neighbouring Card must be named by its id.")

    target = form.cleaned_data["stage"]
    origin = card.stage_id
    try:
        card.move_to(
            target, before=form.cleaned_data["before"], after=form.cleaned_data["after"]
        )
    except Stage.DoesNotExist:
        raise Http404("That Stage has just been deleted.")
    except Card.DoesNotExist:
        raise Http404("That Card has just been archived.")

    # A drag sends this with htmx and gets the board back, fresh from the
    # database, to replace what the page shows. The browser has already
    # animated the drop (board.js), so this board marks nothing.
    if request.headers.get("HX-Request"):
        return render(request, "components/board.html", board_context(board, request))

    # A Move from the menu gets a redirect, and the board it loads animates a
    # Card arriving in a different Stage; arriving in the board's last Stage,
    # its "done", also celebrates.
    if target.pk != origin:
        last = board.stages.order_by("position", "id").last()
        request.session["landed"] = {"card": card.pk, "celebrate": target.pk == last.pk}
    return redirect(board_url(board, request))


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
    return back_to(request, board_url(board, request))


@require_POST
@login_required
def card_restore(request, board_pk, pk):
    board, card = get_card(request, board_pk, pk)
    try:
        card.restore()
    except Card.DoesNotExist:
        raise Http404("That Card has just been deleted.")
    messages.success(request, f"Restored {card.title} to {card.stage.name}.")
    return back_to(request, board_url(board, request))


@require_POST
@login_required
def card_delete(request, board_pk, pk):
    board, card = get_card(request, board_pk, pk)
    card.delete()
    messages.success(request, f"Deleted {card.title}.")
    return back_to(request, board_url(board, request))


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


def require_owner(board, user):
    """Inviting and removing are the Owner's alone. A Member reaching these
    gets a 403: they can see the board, so a 404 would only mislead."""
    if not board.is_owner(user):
        raise PermissionDenied("Only the board's Owner can do that.")


def render_members(request, board, *, invite_form=None, status=200):
    """The Members page. Everyone on the board sees who else is; only the
    Owner gets the Invite form and the Withdraw and Remove buttons."""
    assigned = dict(
        board.cards.filter(assignee__isnull=False)
        .values_list("assignee")
        .annotate(n=Count("pk"))
        .values_list("assignee", "n")
    )
    members = [
        (membership, assigned.get(membership.user_id, 0))
        for membership in board.memberships.filter(user__isnull=False)
        .select_related("user")
        .order_by("-role", "user__display_name", "user__email")
    ]
    others = len(members) - 1
    return render(
        request,
        "boards/members.html",
        {
            "board": board,
            "members": members,
            "pending": board.memberships.filter(user__isnull=True).order_by("created_at"),
            "is_owner": board.is_owner(request.user),
            "others": others,
            "mine_assigned": assigned.get(request.user.pk, 0),
            "invite_form": invite_form or InviteForm(),
        },
        status=status,
    )


@require_safe
@login_required
def board_members(request, board_pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    return render_members(request, board)


@require_POST
@login_required
def member_invite(request, board_pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    require_owner(board, request.user)
    form = InviteForm(request.POST)
    if form.is_valid():
        try:
            invited = board.invite(form.cleaned_data["email"])
        except ValidationError as error:
            form.add_error("email", error)
        else:
            messages.success(
                request,
                f"Invited {invited.email}. Let them know: the board appears when "
                "they sign in with Google using that address.",
            )
            return redirect("board_members", board_pk=board.pk)
    return render_members(request, board, invite_form=form, status=400)


@require_POST
@login_required
def member_remove(request, board_pk, pk):
    """Withdraws a Pending member, or removes a Member."""
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    require_owner(board, request.user)
    membership = get_object_or_404(board.memberships.select_related("user"), pk=pk)
    try:
        cleared = membership.remove()
    except ValidationError as error:
        messages.error(request, error.message)
    else:
        if membership.is_pending:
            messages.success(request, f"Withdrew the invitation for {membership.email}.")
        else:
            unassigned = (
                f" {cleared} Card{'s' if cleared != 1 else ''} they were assigned "
                f"{'are' if cleared != 1 else 'is'} now unassigned." if cleared else ""
            )
            messages.success(request, f"Removed {membership.user.name}.{unassigned}")
    return redirect("board_members", board_pk=board.pk)


@require_POST
@login_required
def member_make_owner(request, board_pk, pk):
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    require_owner(board, request.user)
    try:
        new_owner = board.hand_over(request.user, pk)
    except ValidationError as error:
        messages.error(request, error.message)
    else:
        messages.success(request, f"{new_owner.user.name} is now the Owner.")
    return redirect("board_members", board_pk=board.pk)


@require_POST
@login_required
def board_leave(request, board_pk):
    """A Member leaves of their own accord, exactly as if removed. The Owner
    can't: a board must keep one, so they hand over first, or delete it."""
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    membership = board.memberships.get(user=request.user)
    if membership.role == Membership.Role.OWNER:
        messages.error(request, "The Owner cannot leave. Make someone else Owner first, or delete the board.")
        return redirect("board_members", board_pk=board.pk)
    try:
        cleared = membership.remove()
    except ValidationError as error:
        # Made Owner while this was on its way.
        messages.error(request, error.message)
        return redirect("board_members", board_pk=board.pk)
    unassigned = (
        f" {cleared} Card{'s' if cleared != 1 else ''} assigned to you there "
        f"{'are' if cleared != 1 else 'is'} now unassigned." if cleared else ""
    )
    messages.success(request, f"You left {board.name}.{unassigned}")
    return redirect("home")


@login_required
def board_rename(request, board_pk):
    """The Owner's alone, like deleting. The form gets its own copy, so a
    refused name never shows in the page's link back to the board.

    The pencil beside the board's name asks with htmx, and edits the name in
    place: it gets the bare form, then the heading back. Without JavaScript,
    the pencil is a link to this page, which redirects to the board."""
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    require_owner(board, request.user)
    form = BoardForm(request.POST or None, instance=copy.copy(board))
    in_place = request.headers.get("HX-Request")
    if request.method == "POST" and form.is_valid():
        form.instance.save(update_fields=["name"])
        if in_place:
            return render(
                request,
                "components/board_heading.html",
                {"board": form.instance, "is_owner": True, "retitle": True},
            )
        messages.success(request, f"Renamed the board to {form.instance.name}.")
        return redirect("board_detail", pk=board.pk)
    return render(
        request,
        "components/board_rename_form.html" if in_place else "boards/board_rename.html",
        {"board": board, "form": form},
        status=400 if form.is_bound else 200,
    )


@login_required
def board_describe(request, board_pk):
    """The Owner's, like renaming, and edited in place the same way: htmx
    gets the bare form, then the description back. Without JavaScript, the
    description is a link to this page, which redirects to the board."""
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    require_owner(board, request.user)
    form = BoardDescriptionForm(request.POST or None, instance=copy.copy(board))
    in_place = request.headers.get("HX-Request")
    if request.method == "POST" and form.is_valid():
        form.instance.save(update_fields=["description"])
        if in_place:
            return render(
                request,
                "components/board_description.html",
                {
                    "board": form.instance,
                    "is_owner": True,
                    "playful": random.choice(PLAYFUL_DESCRIPTIONS),
                },
            )
        messages.success(request, "Saved the board's description.")
        return redirect("board_detail", pk=board.pk)
    return render(
        request,
        "components/board_description_form.html" if in_place else "boards/board_describe.html",
        {"board": board, "form": form},
        status=400 if form.is_bound else 200,
    )


@require_POST
@login_required
def board_pet(request, board_pk):
    """The board's pet, chosen by any Member from its ⋯ menu. With htmx it
    answers with the pet, and the menu out of band so its tick moves. The pet
    sits outside #board, so a drag or a refresh never resets it. Without
    JavaScript, it goes back to the board."""
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    form = BoardPetForm(request.POST, instance=board)
    if not form.is_valid():
        return HttpResponseBadRequest("No such pet.")
    form.instance.save(update_fields=["pet"])
    if request.headers.get("HX-Request"):
        context = {"board": board, "is_owner": board.is_owner(request.user)}
        return HttpResponse(
            render_to_string("components/pet.html", context, request)
            + render_to_string("components/board_menu.html", {**context, "oob": True}, request)
        )
    return redirect(board_url(board, request))


@login_required
def board_delete(request, board_pk):
    """The one place that deliberately slows the Owner down: the whole board
    goes, with no undo, only once its name is typed exactly."""
    board = get_object_or_404(Board.objects.for_user(request.user), pk=board_pk)
    require_owner(board, request.user)
    form = DeleteBoardForm(request.POST or None, board=board)
    if request.method == "POST" and form.is_valid():
        name = board.name
        board.destroy()
        messages.success(request, f"Deleted the board {name}.")
        return redirect("home")
    return render(
        request,
        "boards/board_delete.html",
        {
            "board": board,
            "form": form,
            "cards": board.cards.filter(archived_at__isnull=True).count(),
            "archived": board.cards.filter(archived_at__isnull=False).count(),
            "stages": board.stages.count(),
            "members": board.memberships.filter(user__isnull=False).count(),
            "pending": board.memberships.filter(user__isnull=True).count(),
        },
        status=400 if form.is_bound else 200,
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
    return redirect(board_url(board, request))


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
