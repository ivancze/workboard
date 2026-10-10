from django.conf import settings
from django.db import models, transaction

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
