from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, StepValueValidator
from django.db import models, transaction
from django.db.models import F
from django.utils import timezone

# Every board starts with these, in this order. Boards are expected to diverge
# from them immediately; they exist so a new board is usable rather than empty.
DEFAULT_STAGE_NAMES = ("To Do", "In Progress", "Done")


class BoardQuerySet(models.QuerySet):
    def for_user(self, user):
        """Only the boards this user is a Member of.

        Every board read starts here. Scoping at the query means a forgotten
        check yields a 404 rather than someone else's data: the failure is
        visible and harmless instead of silent and a leak.
        """
        if not user.is_authenticated:
            return self.none()
        return self.filter(memberships__user=user)


class BoardManager(models.Manager.from_queryset(BoardQuerySet)):
    def create_with_owner(self, *, name, owner):
        """Create a board that is immediately valid.

        A board with no Owner could never be administered, and one with no
        Stages has nowhere to put a Card, so both are established here in one
        transaction rather than left to the caller to remember.
        """
        with transaction.atomic():
            board = self.create(name=name)
            Membership.objects.create(
                board=board, user=owner, role=Membership.Role.OWNER
            )
            Stage.objects.bulk_create(
                Stage(board=board, name=name_, position=position)
                for position, name_ in enumerate(DEFAULT_STAGE_NAMES)
            )
        return board


class Board(models.Model):
    """The unit of both workflow and access.

    There is no organisation or team above a board: it is the only boundary
    that exists.
    """

    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = BoardManager()

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.name

    @property
    def owner(self):
        return self.memberships.get(role=Membership.Role.OWNER).user

    def lock(self):
        """Lock this board for the rest of the transaction. Taken before any
        Stage lock by everything that adds or deletes Stages, so those take
        turns: two deletes at once could otherwise leave no Stage at all."""
        Board.objects.select_for_update().get(pk=self.pk)

    def check_stage_name_free(self, name, *, exclude=None):
        """Stage names are unique on a board, ignoring case, so the Move
        buttons are never ambiguous. Checked under the board lock."""
        taken = self.stages.filter(name__iexact=name).exclude(pk=exclude)
        if taken.exists():
            raise ValidationError(f"This board already has a Stage called {taken.get().name}.")

    def add_stage(self, name):
        """Add a Stage at the end. Stage order is otherwise fixed."""
        with transaction.atomic():
            self.lock()
            self.check_stage_name_free(name)
            last = self.stages.aggregate(last=models.Max("position"))["last"]
            return self.stages.create(name=name, position=0 if last is None else last + 1)


class Membership(models.Model):
    """The link between a user and a board, carrying their role.

    Memberships are the only record of who can see what.
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MEMBER = "member", "Member"

    board = models.ForeignKey(
        Board, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["board", "user"], name="one_membership_per_user_per_board"
            )
        ]

    def __str__(self):
        return f"{self.user} on {self.board} ({self.role})"


class Stage(models.Model):
    """A named step in a board's workflow.

    Every Card sits in exactly one Stage at a time, and moving a Card between
    Stages is how work progresses.
    """

    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=50)
    position = models.PositiveIntegerField()

    class Meta:
        # `id` breaks ties so the order is total: two Stages sharing a position
        # must still come back in a stable order rather than whatever the
        # database happens to return.
        ordering = ["position", "id"]

    def __str__(self):
        return self.name

    def rename(self, name):
        with transaction.atomic():
            self.board.lock()
            self.board.check_stage_name_free(name, exclude=self.pk)
            self.name = name
            self.save(update_fields=["name"])

    def shift(self, step):
        """Move this Stage one place earlier (-1) or later (+1) in the board's
        Stage order. Its Cards go with it: they belong to the Stage, not to a
        place on the board. Does nothing at either end.

        The board's Stages are renumbered 0..n-1 under the board lock, so
        simultaneous presses take turns and gaps left by deletes close up.
        """
        with transaction.atomic():
            self.board.lock()
            order = list(self.board.stages.all())
            here = next((i for i, stage in enumerate(order) if stage.pk == self.pk), None)
            if here is None:
                raise Stage.DoesNotExist("This Stage was deleted first.")
            there = here + step
            if 0 <= there < len(order):
                order[here], order[there] = order[there], order[here]
            for position, stage in enumerate(order):
                if stage.position != position:
                    Stage.objects.filter(pk=stage.pk).update(position=position)

    def delete_if_empty(self):
        """Delete this Stage, or refuse with the reason.

        Only an empty Stage goes, so deleting never takes Cards with it. The
        Stage's lock is the one every write to Card order holds, so no Card
        can arrive between the check and the delete.
        """
        with transaction.atomic():
            self.board.lock()
            lock_stages(self.pk)
            held = self.cards.count()
            if held:
                raise ValidationError(
                    f"Still holds {held} Card{'s' if held != 1 else ''}. Move "
                    f"{'them' if held != 1 else 'it'} out first."
                )
            if self.board.stages.count() == 1:
                raise ValidationError("A board needs at least one Stage.")
            self.delete()

    def archive_cards(self, expected):
        """Archive every Card in this Stage, if it holds the `expected` number:
        the count the person confirmed. A Card added or moved in since then
        refuses the whole action, so nothing is archived that they didn't
        agree to. Returns how many were archived.

        One update under the Stage lock. The Stage ends empty, so there is no
        gap to close.
        """
        with transaction.atomic():
            lock_stages(self.pk)
            held = self.cards.count()
            if held != expected:
                raise ValidationError(
                    f"{self.name} now holds {held} Card{'s' if held != 1 else ''}, "
                    f"not {expected}. Nothing was archived."
                )
            now = timezone.now()
            self.cards.update(
                stage=None,
                position=None,
                archived_at=now,
                archived_from=self,
                updated_at=now,
            )
            return held


def lock_stages(*stage_ids):
    """Lock Stages for the rest of the transaction, so their Card order can be
    rewritten without another request interleaving.

    Always locked in id order: two requests locking the same pair can then only
    queue behind each other, never wait on each other forever. A Stage deleted
    by a request that got there first raises Stage.DoesNotExist.
    """
    locked = Stage.objects.select_for_update().filter(pk__in=stage_ids).order_by("pk")
    if len(locked) != len(set(stage_ids)):
        raise Stage.DoesNotExist("A Stage was deleted before it could be locked.")


def end_of(stage_id):
    last = Card.objects.filter(stage_id=stage_id).aggregate(last=models.Max("position"))
    return 0 if last["last"] is None else last["last"] + 1


class CardManager(models.Manager):
    def create_at_end(self, *, stage, **fields):
        """Create a Card at the bottom of its Stage's Card order.

        A new Card has not been prioritised by anyone yet, so it waits below
        the Cards that have.
        """
        with transaction.atomic():
            lock_stages(stage.pk)
            return self.create(
                board=stage.board, stage=stage, position=end_of(stage.pk), **fields
            )

    def create_in_first_stage(self, *, board, **fields):
        """Create a Card at the bottom of the board's first Stage, where every
        new Card starts. If that Stage is deleted before it can be locked,
        another is first by then, so choose again.
        """
        while True:
            stage = board.stages.order_by("position", "id").first()
            try:
                return self.create_at_end(stage=stage, **fields)
            except Stage.DoesNotExist:
                continue


class Card(models.Model):
    """One unit of work, sitting in exactly one Stage, or in its board's
    archive.

    An archived Card has no Stage and no position: it has left Card order. It
    remembers the Stage it left, for Restore, and keeps its board, which is
    how the archive and every access check still find it.
    """

    # PROTECT, like the Stage: deleting a board must not take Cards with it by
    # accident, archived ones included.
    board = models.ForeignKey(Board, on_delete=models.PROTECT, related_name="cards")
    # PROTECT: deleting a Stage must never take its Cards with it. Only an
    # empty Stage is deleted (Stage.delete_if_empty); this is the backstop.
    # Null while archived, so `stage.cards` holds only the Cards on the board.
    stage = models.ForeignKey(
        Stage, on_delete=models.PROTECT, null=True, blank=True, related_name="cards"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    # SET_NULL: archived Cards don't keep their Stage from being deleted.
    # Restore then uses the board's first Stage.
    archived_from = models.ForeignKey(
        Stage, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # PROTECT: the Creator is a historical fact that survives leaving the board,
    # so deleting the User must not silently rewrite or erase it.
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    # SET_NULL: the Assignee is a current responsibility, not history, so a
    # deleted User leaves the Card visibly unassigned.
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Free text, never matched to Users: they are people outside the board.
    contact_persons = models.CharField(max_length=200, blank=True)
    # A plain date with no time or timezone, and advisory only: nothing in the
    # system sorts, filters, blocks or notifies on it.
    due_date = models.DateField(null=True, blank=True)
    # A bare number in the team's own unit, in steps of 0.5. Null is
    # Unestimated, which is not the same as zero: zero says this is free,
    # Unestimated says nobody has looked yet. No ceiling beyond the column's.
    effort = models.DecimalField(
        max_digits=12,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), StepValueValidator(Decimal("0.5"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Recorded for a future display and Card history; nothing shows it yet.
    updated_at = models.DateTimeField(auto_now=True)

    objects = CardManager()

    class Meta:
        # Card order is set by hand and read as priority; `id` only breaks ties.
        ordering = ["position", "id"]
        constraints = [
            # The backstop for Card order. Deferred to commit, because closing
            # a gap shifts positions one row at a time through duplicates.
            models.UniqueConstraint(
                fields=["stage", "position"],
                name="one_card_per_position_per_stage",
                deferrable=models.Deferrable.DEFERRED,
            ),
            # A Card is on the board, in a Stage at a position, or archived,
            # with neither. Never half of each.
            models.CheckConstraint(
                condition=models.Q(
                    archived_at__isnull=True,
                    stage__isnull=False,
                    position__isnull=False,
                    archived_from__isnull=True,
                )
                | models.Q(
                    archived_at__isnull=False, stage__isnull=True, position__isnull=True
                ),
                name="on_the_board_or_archived",
            ),
        ]

    def __str__(self):
        return self.title

    def move_to(self, stage, position=None):
        """Move this Card to `position` in `stage`, which may be its own Stage.

        Without a position it goes to the bottom of another Stage, and stays
        put in its own. A position past either end is taken as that end. Card
        order stays contiguous in every Stage touched: the Cards between the
        old place and the new shift by one to make room or close the gap.

        Every write to Card order holds the lock of each Stage it touches, so
        these locks alone keep concurrent moves and additions from
        interleaving.
        """
        while True:
            with transaction.atomic():
                # Stages are locked before any Card. Locking the Card first
                # deadlocks: closing the gap rewrites other Cards, which a
                # concurrent move may hold while it waits for these Stages.
                origin = Card.objects.values_list("stage_id", flat=True).get(pk=self.pk)
                if origin is None:
                    raise Card.DoesNotExist("This Card was archived.")
                if origin == stage.pk and position is None:
                    return
                lock_stages(origin, stage.pk)
                card = Card.objects.get(pk=self.pk)
                if card.stage_id != origin:
                    continue  # moved by someone else before the lock; start over

                siblings = Card.objects.filter(stage_id=stage.pk).exclude(pk=card.pk)
                if origin == stage.pk:
                    target = min(position, end_of(stage.pk) - 1)
                    if target > card.position:
                        siblings.filter(
                            position__gt=card.position, position__lte=target
                        ).update(position=F("position") - 1)
                    elif target < card.position:
                        siblings.filter(
                            position__gte=target, position__lt=card.position
                        ).update(position=F("position") + 1)
                else:
                    Card.objects.filter(
                        stage_id=origin, position__gt=card.position
                    ).update(position=F("position") - 1)
                    end = end_of(stage.pk)
                    target = end if position is None else min(position, end)
                    siblings.filter(position__gte=target).update(position=F("position") + 1)

                card.stage = stage
                card.position = target
                card.save(update_fields=["stage", "position", "updated_at"])
                break

        self.stage, self.position = card.stage, card.position

    def archive(self):
        """Take this Card off the board into its archive, remembering its
        Stage for Restore. The Cards below it move up to close the gap. An
        archived Card stays as it is.

        Locks as move_to does: the Stage first, then the Card.
        """
        while True:
            with transaction.atomic():
                origin = Card.objects.values_list("stage_id", flat=True).get(pk=self.pk)
                if origin is None:
                    break
                lock_stages(origin)
                card = Card.objects.get(pk=self.pk)
                if card.stage_id != origin:
                    continue  # moved by someone else before the lock; start over

                Card.objects.filter(
                    stage_id=origin, position__gt=card.position
                ).update(position=F("position") - 1)
                card.stage, card.position = None, None
                card.archived_at, card.archived_from_id = timezone.now(), origin
                card.save(
                    update_fields=[
                        "stage", "position", "archived_at", "archived_from", "updated_at"
                    ]
                )
                break

        self.refresh_from_db(fields=["stage", "position", "archived_at", "archived_from"])

    def restore(self):
        """Return this archived Card to the bottom of the Stage it was archived
        from, or of the board's first Stage if that one has been deleted. A
        Card on the board stays as it is.
        """
        while True:
            with transaction.atomic():
                card = Card.objects.get(pk=self.pk)
                if card.archived_at is None:
                    break
                target = card.archived_from_id or (
                    self.board.stages.order_by("position", "id")
                    .values_list("pk", flat=True)
                    .first()
                )
                try:
                    lock_stages(target)
                except Stage.DoesNotExist:
                    continue  # deleted before the lock; choose again

                came_from = card.archived_from_id
                card = Card.objects.get(pk=self.pk)
                if card.archived_at is None:
                    break  # restored by someone else meanwhile
                if card.archived_from_id != came_from:
                    continue  # restored and archived again elsewhere; choose again
                card.stage_id, card.position = target, end_of(target)
                card.archived_at, card.archived_from = None, None
                card.save(
                    update_fields=[
                        "stage", "position", "archived_at", "archived_from", "updated_at"
                    ]
                )
                break

        self.refresh_from_db(fields=["stage", "position", "archived_at", "archived_from"])

    def delete(self, *args, **kwargs):
        """Destroy this Card for good. On the board, the Cards below it move
        up to close the gap, under the Stage lock as for a move. An archived
        Card is outside Card order, so it needs no lock. Deleting a Card that
        is already gone does nothing.
        """
        while True:
            with transaction.atomic():
                origin = Card.objects.filter(pk=self.pk).values_list("stage_id", flat=True).first()
                if origin is None:
                    # Archived, or gone. Checked again as the row is deleted:
                    # a Card restored meanwhile is skipped and taken again from
                    # the top, so its Stage isn't left with a gap.
                    deleted, _ = Card.objects.filter(pk=self.pk, stage__isnull=True).delete()
                    if deleted or not Card.objects.filter(pk=self.pk).exists():
                        break
                    continue
                lock_stages(origin)
                position = (
                    Card.objects.filter(pk=self.pk, stage_id=origin)
                    .values_list("position", flat=True)
                    .first()
                )
                if position is None:
                    continue  # moved, archived or deleted before the lock; start over
                Card.objects.filter(pk=self.pk).delete()
                Card.objects.filter(stage_id=origin, position__gt=position).update(
                    position=F("position") - 1
                )
                break

    @property
    def is_overdue(self):
        """Its Due date has passed. A Card due today is not yet overdue, and
        an archived Card never is: archiving is how work stops being overdue.

        "Today" is the team's date, from TIME_ZONE, not the server's.
        """
        return (
            self.archived_at is None
            and self.due_date is not None
            and self.due_date < timezone.localdate()
        )
