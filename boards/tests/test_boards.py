from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from boards.models import Board, Membership, Stage


def a_user(email="ada@example.com"):
    return User.objects.create_user(email=email, display_name=email.split("@")[0])


class CreatingABoardTests(TestCase):
    def setUp(self):
        self.user = a_user()
        self.client.force_login(self.user)

    def test_the_creator_becomes_the_owner(self):
        self.client.post(reverse("board_create"), {"name": "Housework"})

        board = Board.objects.get(name="Housework")
        self.assertEqual(board.owner, self.user)
        self.assertEqual(
            board.memberships.get(user=self.user).role, Membership.Role.OWNER
        )

    def test_a_new_board_has_the_three_default_stages_in_order(self):
        self.client.post(reverse("board_create"), {"name": "Housework"})

        board = Board.objects.get(name="Housework")
        self.assertEqual(
            [stage.name for stage in board.stages.all()],
            ["To Do", "In Progress", "Done"],
        )

    def test_the_default_stages_start_empty(self):
        self.client.post(reverse("board_create"), {"name": "Housework"})

        response = self.client.get(
            reverse("board_detail", args=[Board.objects.get().pk])
        )

        self.assertContains(response, "No cards yet.", count=3)

    def test_a_board_needs_a_name(self):
        self.client.post(reverse("board_create"), {"name": ""})

        self.assertFalse(Board.objects.exists())

    def test_creating_requires_signing_in(self):
        self.client.logout()

        self.client.post(reverse("board_create"), {"name": "Housework"})

        self.assertFalse(Board.objects.exists())

    def test_a_half_built_board_is_never_left_behind(self):
        """Owner and Stages are created in one transaction with the board, so
        there is no window in which a board exists unadministered or empty."""
        self.client.post(reverse("board_create"), {"name": "Housework"})

        for board in Board.objects.all():
            self.assertEqual(board.memberships.filter(role="owner").count(), 1)
            self.assertEqual(board.stages.count(), 3)


class HomePageTests(TestCase):
    def setUp(self):
        self.ada = a_user("ada@example.com")
        self.grace = a_user("grace@example.com")
        self.adas_board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.graces_board = Board.objects.create_with_owner(
            name="Secret Plans", owner=self.grace
        )

    def test_lists_the_boards_you_belong_to(self):
        self.client.force_login(self.ada)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Housework")

    def test_and_nobody_elses(self):
        self.client.force_login(self.ada)

        response = self.client.get(reverse("home"))

        self.assertNotContains(response, "Secret Plans")

    def test_a_member_who_is_not_the_owner_still_sees_it(self):
        Membership.objects.create(
            board=self.graces_board, user=self.ada, role=Membership.Role.MEMBER
        )
        self.client.force_login(self.ada)

        response = self.client.get(reverse("home"))

        self.assertContains(response, "Secret Plans")


class BoardAccessTests(TestCase):
    """The security boundary. Every one of these is about what a signed-in
    stranger can reach by guessing an identifier."""

    def setUp(self):
        self.ada = a_user("ada@example.com")
        self.grace = a_user("grace@example.com")
        self.graces_board = Board.objects.create_with_owner(
            name="Secret Plans", owner=self.grace
        )

    def test_a_non_member_cannot_reach_a_board_by_guessing_its_id(self):
        self.client.force_login(self.ada)

        response = self.client.get(
            reverse("board_detail", args=[self.graces_board.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_the_response_does_not_reveal_that_the_board_exists(self):
        """404 rather than 403: a permission error would confirm the board is
        real, which is a disclosure in itself."""
        self.client.force_login(self.ada)

        response = self.client.get(
            reverse("board_detail", args=[self.graces_board.pk])
        )

        self.assertNotEqual(response.status_code, 403)
        self.assertNotContains(response, "Secret Plans", status_code=404)

    def test_a_member_can_reach_it(self):
        Membership.objects.create(
            board=self.graces_board, user=self.ada, role=Membership.Role.MEMBER
        )
        self.client.force_login(self.ada)

        response = self.client.get(
            reverse("board_detail", args=[self.graces_board.pk])
        )

        self.assertEqual(response.status_code, 200)

    def test_an_anonymous_visitor_is_sent_to_sign_in(self):
        response = self.client.get(
            reverse("board_detail", args=[self.graces_board.pk])
        )

        self.assertEqual(response.status_code, 302)


class ScopingHelperTests(TestCase):
    """Unit tests for the helper every board read goes through."""

    def setUp(self):
        self.ada = a_user("ada@example.com")
        self.grace = a_user("grace@example.com")
        Board.objects.create_with_owner(name="Housework", owner=self.ada)
        Board.objects.create_with_owner(name="Secret Plans", owner=self.grace)

    def test_returns_only_boards_the_user_is_a_member_of(self):
        self.assertEqual(
            [b.name for b in Board.objects.for_user(self.ada)], ["Housework"]
        )

    def test_returns_nothing_for_an_anonymous_user(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertEqual(Board.objects.for_user(AnonymousUser()).count(), 0)

    def test_does_not_duplicate_a_board_when_joined(self):
        """A membership join can multiply rows; a user with one membership must
        still see exactly one board."""
        self.assertEqual(Board.objects.for_user(self.ada).count(), 1)


class StageTests(TestCase):
    def test_stages_come_back_in_position_order_not_insertion_order(self):
        board = Board.objects.create(name="Bare")
        Stage.objects.create(board=board, name="Third", position=2)
        Stage.objects.create(board=board, name="First", position=0)
        Stage.objects.create(board=board, name="Second", position=1)

        self.assertEqual(
            [s.name for s in board.stages.all()], ["First", "Second", "Third"]
        )

    def test_a_tied_position_still_yields_a_stable_order(self):
        """Nothing should create ties, but a non-deterministic board would be a
        baffling bug, so the ordering is total."""
        board = Board.objects.create(name="Bare")
        first = Stage.objects.create(board=board, name="A", position=0)
        second = Stage.objects.create(board=board, name="B", position=0)

        self.assertEqual([s.pk for s in board.stages.all()], [first.pk, second.pk])

    def test_the_seeded_stages_are_positioned_from_zero(self):
        board = Board.objects.create_with_owner(name="Housework", owner=a_user())

        self.assertEqual([s.position for s in board.stages.all()], [0, 1, 2])
