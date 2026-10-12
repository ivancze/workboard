import threading

from django.core.exceptions import ValidationError

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from boards.models import Board, Card, Membership, Stage

from .test_cards import a_card, a_user
from .test_members import verified


def owners(board):
    return list(
        board.memberships.filter(role=Membership.Role.OWNER).values_list("user__email", flat=True)
    )


class HandingOverOwnershipTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.graces = Membership.objects.create(board=self.board, user=self.grace)
        self.client.force_login(self.ada)
        self.members_url = reverse("board_members", args=[self.board.pk])

    def make_owner(self, membership_pk):
        return self.client.post(reverse("member_make_owner", args=[self.board.pk, membership_pk]))

    def text(self, url):
        return " ".join(self.client.get(url).content.decode().split())

    def test_the_owner_hands_over_and_becomes_a_plain_member(self):
        response = self.make_owner(self.graces.pk)

        self.assertRedirects(response, self.members_url, fetch_redirect_response=False)
        self.assertEqual(owners(self.board), ["grace@example.com"])
        self.assertEqual(self.board.memberships.get(user=self.ada).role, "member")
        self.assertIn("grace is now the Owner.", self.text(self.members_url))
        invite = self.client.post(reverse("member_invite", args=[self.board.pk]), {"email": "x@example.com"})
        self.assertEqual(invite.status_code, 403)

    def test_handing_over_is_confirmed_in_a_dialog(self):
        content = self.text(self.members_url)

        self.assertIn(f'commandfor="make-owner-{self.graces.pk}"', content)
        self.assertIn("Make grace the Owner?</h2>", content)

    def test_only_a_member_of_this_board_can_be_made_owner(self):
        pending = Membership.objects.create(board=self.board, email="pending@example.com")
        elsewhere = Board.objects.create_with_owner(name="Elsewhere", owner=self.grace)

        for pk in [pending.pk, elsewhere.memberships.get().pk, self.board.memberships.get(user=self.ada).pk]:
            with self.subTest(pk=pk):
                self.make_owner(pk)
                self.assertEqual(owners(self.board), ["ada@example.com"])
                self.assertEqual(owners(elsewhere), ["grace@example.com"])
        self.assertIn("They are no longer a Member of this board.", self.text(self.members_url))

    def test_a_member_cannot_hand_over_ownership(self):
        hopper = Membership.objects.create(board=self.board, user=a_user("hopper@example.com"))
        self.client.force_login(self.grace)

        response = self.make_owner(hopper.pk)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(owners(self.board), ["ada@example.com"])

    def test_the_database_refuses_a_second_owner(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.filter(pk=self.graces.pk).update(role=Membership.Role.OWNER)


class LeavingTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        Membership.objects.create(board=self.board, user=self.grace)
        self.to_do = self.board.stages.first()
        self.members_url = reverse("board_members", args=[self.board.pk])
        self.leave_url = reverse("board_leave", args=[self.board.pk])

    def text(self, url):
        return " ".join(self.client.get(url).content.decode().split())

    def test_a_member_leaves_and_loses_access(self):
        self.client.force_login(self.grace)

        response = self.client.post(self.leave_url)

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertIn("You left Housework.", self.text(reverse("home")))
        self.assertEqual(self.client.get(reverse("board_detail", args=[self.board.pk])).status_code, 404)

    def test_leaving_clears_their_assignments_exactly_as_removal_does(self):
        on_board = a_card(self.to_do, "On the board", assignee=self.grace, creator=self.grace)
        archived = a_card(self.to_do, "Archived", assignee=self.grace)
        archived.archive()
        adas = a_card(self.to_do, "Ada's", assignee=self.ada)
        self.client.force_login(self.grace)

        self.client.post(self.leave_url)

        for card, assignee in [(on_board, None), (archived, None), (adas, self.ada)]:
            card.refresh_from_db()
            self.assertEqual(card.assignee, assignee)
        self.assertEqual(on_board.creator, self.grace)
        self.assertIn("2 Cards assigned to you there are now unassigned.", self.text(reverse("home")))

    def test_leaving_is_confirmed_stating_what_becomes_unassigned(self):
        a_card(self.to_do, "One", assignee=self.grace)
        self.client.force_login(self.grace)

        content = self.text(self.members_url)

        self.assertIn('commandfor="leave-board"', content)
        self.assertIn("Leave Housework?</h2>", content)
        self.assertIn("The 1 Card assigned to you will become unassigned", content)

    def test_the_owner_cannot_leave_until_they_hand_over(self):
        self.client.force_login(self.ada)

        response = self.client.post(self.leave_url)

        self.assertRedirects(response, self.members_url, fetch_redirect_response=False)
        self.assertEqual(owners(self.board), ["ada@example.com"])
        content = self.text(self.members_url)
        self.assertIn("The Owner cannot leave. Make someone else Owner first, or delete the board.", content)
        self.assertIn("Make someone else Owner first, with Make Owner above.", content)
        self.assertNotIn('commandfor="leave-board"', content)

    def test_an_owner_alone_on_the_board_is_told_to_delete_it_instead(self):
        Membership.objects.filter(user=self.grace).delete()
        self.client.force_login(self.ada)

        content = self.text(self.members_url)

        self.assertIn("so there is no one to hand it to.", content)
        self.assertIn(f'href="{reverse("board_delete", args=[self.board.pk])}"', content)


class DeletingABoardTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = verified(a_user("grace@example.com"))
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        Membership.objects.create(board=self.board, user=self.grace)
        self.client.force_login(self.ada)
        self.url = reverse("board_delete", args=[self.board.pk])

    def delete(self, name):
        return self.client.post(self.url, {"name": name})

    def test_only_the_owner_is_offered_deletion(self):
        board_url = reverse("board_detail", args=[self.board.pk])
        self.assertIn(f'href="{self.url}"', self.client.get(board_url).content.decode())

        self.client.force_login(self.grace)
        self.assertNotIn(f'href="{self.url}"', self.client.get(board_url).content.decode())

    def test_a_member_cannot_delete_by_submitting_directly_and_a_stranger_sees_nothing(self):
        self.client.force_login(self.grace)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.delete("Housework").status_code, 403)

        self.client.force_login(a_user("stranger@example.com"))
        self.assertEqual(self.delete("Housework").status_code, 404)
        self.assertTrue(Board.objects.filter(pk=self.board.pk).exists())

    def test_the_page_says_what_will_go(self):
        a_card(self.board.stages.first(), "Live")
        a_card(self.board.stages.first(), "Old").archive()
        Membership.objects.create(board=self.board, email="pending@example.com")

        content = " ".join(self.client.get(self.url).content.decode().split())

        self.assertIn("1 Card on the board, and 1 archived", content)
        self.assertIn("3 Stages", content)
        self.assertIn("2 Members, and 1 invitation not yet claimed", content)

    def test_nothing_is_deleted_unless_the_name_is_typed_exactly(self):
        for typed in ["", "housework", "Housework ", " Housework", "House work"]:
            with self.subTest(typed=typed):
                response = self.delete(typed)
                self.assertEqual(response.status_code, 400)
                self.assertTrue(Board.objects.filter(pk=self.board.pk).exists())
        self.assertContains(response, "That does not match the board name. Nothing was deleted.", status_code=400)

    def test_the_board_goes_with_everything_in_it_and_nothing_else(self):
        stage = self.board.stages.first()
        a_card(stage, "Live")
        a_card(stage, "Old").archive()
        Membership.objects.create(board=self.board, email="pending@example.com")
        other = Board.objects.create_with_owner(name="Elsewhere", owner=self.ada)
        kept = a_card(other.stages.first(), "Kept")

        response = self.delete("Housework")

        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertIn("Deleted the board Housework.", self.client.get(reverse("home")).content.decode())
        self.assertFalse(Board.objects.filter(pk=self.board.pk).exists())
        self.assertFalse(Stage.objects.filter(board_id=self.board.pk).exists())
        self.assertFalse(Card.objects.filter(board_id=self.board.pk).exists())
        self.assertFalse(Membership.objects.filter(board_id=self.board.pk).exists())
        self.assertEqual(list(Card.objects.all()), [kept])
        self.assertEqual(other.stages.count(), 3)
        self.assertEqual(owners(other), ["ada@example.com"])

    def test_a_pending_member_of_a_deleted_board_can_claim_nothing_later(self):
        Membership.objects.create(board=self.board, email="hopper@example.com")
        self.delete("Housework")
        hopper = verified(a_user("hopper@example.com"))

        self.assertEqual(Membership.objects.claim_for(hopper), 0)
        self.assertFalse(Membership.objects.filter(user=hopper).exists())


class ConcurrentOwnershipTests(TransactionTestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.hopper = a_user("hopper@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)

    def run_together(self, *actions):
        start = threading.Barrier(len(actions))
        outcomes = [None] * len(actions)

        def run(i, action):
            try:
                start.wait()
                action()
            except Exception as error:
                outcomes[i] = error
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(i, a)) for i, a in enumerate(actions)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return outcomes

    def test_two_hand_overs_at_once_leave_exactly_one_owner(self):
        for _ in range(5):
            graces = Membership.objects.create(board=self.board, user=self.grace)
            hoppers = Membership.objects.create(board=self.board, user=self.hopper)

            outcomes = self.run_together(
                lambda: Board.objects.get(pk=self.board.pk).hand_over(self.ada, graces.pk),
                lambda: Board.objects.get(pk=self.board.pk).hand_over(self.ada, hoppers.pk),
            )

            # One succeeds; the other is refused cleanly, not stopped by the
            # database's one-Owner index with an IntegrityError.
            self.assertEqual(sum(o is None for o in outcomes), 1, outcomes)
            self.assertTrue(all(o is None or isinstance(o, ValidationError) for o in outcomes), outcomes)
            self.assertEqual(len(owners(self.board)), 1)
            # Back to the start for the next round.
            new_owner = self.board.memberships.get(role="owner").user
            self.board.hand_over(new_owner, self.board.memberships.get(user=self.ada).pk)
            Membership.objects.exclude(user=self.ada).delete()

    def test_a_hand_over_racing_the_new_owners_removal_leaves_exactly_one_owner(self):
        for _ in range(5):
            graces = Membership.objects.create(board=self.board, user=self.grace)

            hand_over, remove = self.run_together(
                lambda: Board.objects.get(pk=self.board.pk).hand_over(self.ada, graces.pk),
                lambda: Membership.objects.get(pk=graces.pk).remove(),
            )

            self.assertEqual(len(owners(self.board)), 1)
            self.assertTrue(hand_over is None or isinstance(hand_over, ValidationError), hand_over)
            if hand_over is None:
                # Handed over first: Grace is Owner, so the removal was refused.
                self.assertEqual(owners(self.board), ["grace@example.com"])
                self.assertIn("cannot be removed", str(remove))
                self.board.hand_over(self.grace, self.board.memberships.get(user=self.ada).pk)
            else:
                self.assertEqual(owners(self.board), ["ada@example.com"])
                self.assertIsNone(remove)
            Membership.objects.exclude(user=self.ada).delete()

    def test_a_board_deleted_while_cards_are_added_and_moved_leaves_nothing_behind(self):
        for _ in range(5):
            board = Board.objects.create_with_owner(name="Doomed", owner=self.ada)
            to_do, _, done = board.stages.all()
            mover = a_card(to_do, "Mover")

            outcomes = self.run_together(
                lambda: Board.objects.get(pk=board.pk).destroy(),
                lambda: Card.objects.create_in_first_stage(board=board, title="New", creator=self.ada),
                lambda: Card.objects.get(pk=mover.pk).move_to(done),
            )

            self.assertIsNone(outcomes[0])
            for outcome in outcomes[1:]:
                self.assertTrue(
                    outcome is None
                    or isinstance(outcome, (Stage.DoesNotExist, Card.DoesNotExist, Board.DoesNotExist)),
                    outcome,
                )
            self.assertFalse(Board.objects.filter(pk=board.pk).exists())
            self.assertFalse(Card.objects.filter(board_id=board.pk).exists())
            self.assertFalse(Stage.objects.filter(board_id=board.pk).exists())
