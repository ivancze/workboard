from decimal import Decimal

from django.conf import settings
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


def lock_stages(*stage_ids):
    """Lock Stages for the rest of the transaction, so their Card order can be
    rewritten without another request interleaving.

    Always locked in id order: two requests locking the same pair can then only
    queue behind each other, never wait on each other forever.
    """
    list(Stage.objects.select_for_update().filter(pk__in=stage_ids).order_by("pk"))


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
            return self.create(stage=stage, position=end_of(stage.pk), **fields)


class Card(models.Model):
    """One unit of work, sitting in exactly one Stage."""

    stage = models.ForeignKey(Stage, on_delete=models.CASCADE, related_name="cards")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField()
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
            )
        ]

    def __str__(self):
        return self.title

    def move_to(self, stage):
        """Move this Card to the bottom of another Stage of its board.

        Both Stages' Card order stays contiguous: the old Stage closes the gap,
        and the new one gains the next position. Every write to Card order
        holds the lock of each Stage it touches, so these locks alone keep
        concurrent moves and additions from interleaving.
        """
        while True:
            with transaction.atomic():
                # Stages are locked before any Card. Locking the Card first
                # deadlocks: closing the gap rewrites other Cards, which a
                # concurrent move may hold while it waits for these Stages.
                origin = Card.objects.values_list("stage_id", flat=True).get(pk=self.pk)
                if origin == stage.pk:
                    return
                lock_stages(origin, stage.pk)
                card = Card.objects.get(pk=self.pk)
                if card.stage_id != origin:
                    continue  # moved by someone else before the lock; start over

                Card.objects.filter(
                    stage_id=origin, position__gt=card.position
                ).update(position=F("position") - 1)
                card.stage = stage
                card.position = end_of(stage.pk)
                card.save(update_fields=["stage", "position", "updated_at"])
                break

        self.stage, self.position = card.stage, card.position

    @property
    def is_overdue(self):
        """Its Due date has passed. A Card due today is not yet overdue.

        "Today" is the team's date, from TIME_ZONE, not the server's.
        """
        return self.due_date is not None and self.due_date < timezone.localdate()
