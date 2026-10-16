import re
import threading
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from boards import models
from boards.models import Board, Card, Stage

from .test_cards import a_card, a_user
from .test_moving import card_order


class ArchivingACardTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.to_do, self.in_progress, self.done = self.board.stages.all()
        self.client.force_login(self.ada)
        self.board_url = reverse("board_detail", args=[self.board.pk])
        self.archive_url = reverse("board_archive", args=[self.board.pk])

    def archive(self, card, **data):
        return self.client.post(
            reverse("card_archive", args=[self.board.pk, card.pk]), data
        )

    def restore(self, card, **data):
        return self.client.post(
            reverse("card_restore", args=[self.board.pk, card.pk]), data
        )

    def test_each_card_menu_offers_archive(self):
        card = a_card(self.to_do, "Buy milk")

        content = self.client.get(self.board_url).content.decode()

        action = reverse("card_archive", args=[self.board.pk, card.pk])
        self.assertRegex(
            content,
            rf'(?s)<form method="post" action="{action}"[^>]*>.*?aria-label="Archive Buy milk"[^>]*>Archive</button>',
        )

    def test_archiving_takes_the_card_off_the_board_into_its_archive(self):
        card = a_card(self.to_do, "Buy milk")

        response = self.archive(card)

        self.assertRedirects(response, self.board_url)
        self.assertNotContains(self.client.get(self.board_url), "Buy milk")
        self.assertContains(self.client.get(self.archive_url), "Buy milk")

    def test_the_cards_below_an_archived_card_close_the_gap(self):
        a_card(self.to_do, "First")
        middle = a_card(self.to_do, "Middle")
        a_card(self.to_do, "Last")

        self.archive(middle)

        self.assertEqual(card_order(self.to_do), [("First", 0), ("Last", 1)])

    def test_the_archive_lists_only_this_boards_archived_cards(self):
        archived = a_card(self.to_do, "Archived here")
        a_card(self.to_do, "Still on the board")
        other = Board.objects.create_with_owner(name="Elsewhere", owner=self.ada)
        elsewhere = a_card(other.stages.first(), "Archived elsewhere")
        archived.archive()
        elsewhere.archive()

        content = self.client.get(self.archive_url).content.decode()

        self.assertIn("Archived here", content)
        self.assertNotIn("Still on the board", content)
        self.assertNotIn("Archived elsewhere", content)

    def test_the_archive_says_where_each_card_came_from(self):
        kept = a_card(self.in_progress, "Kept Stage")
        orphan = a_card(self.done, "Lost Stage")
        kept.archive()
        orphan.archive()
        self.done.delete_if_empty()

        content = " ".join(self.client.get(self.archive_url).content.decode().split())

        self.assertIn("from In Progress", content)
        self.assertIn("from a deleted Stage, so restores to To Do", content)

    def test_an_empty_archive_says_so(self):
        self.assertContains(self.client.get(self.archive_url), "Nothing archived yet.")

    def test_an_archived_card_can_still_be_opened_and_edited(self):
        card = a_card(self.to_do, "Buy milk")
        card.archive()

        detail = reverse("card_detail", args=[self.board.pk, card.pk])
        self.assertContains(self.client.get(detail), "Archived on")
        response = self.client.post(
            reverse("card_edit", args=[self.board.pk, card.pk]),
            {"title": "Buy oat milk", "description": "", "effort": "2"},
        )

        self.assertRedirects(response, detail)
        card.refresh_from_db()
        self.assertEqual((card.title, card.effort), ("Buy oat milk", Decimal("2")))
        self.assertIsNotNone(card.archived_at, "editing must not restore it")

    def test_restoring_returns_a_card_to_the_bottom_of_its_stage(self):
        card = a_card(self.in_progress, "Buy milk")
        card.archive()
        a_card(self.in_progress, "Added since")

        response = self.restore(card)

        self.assertRedirects(response, self.board_url)
        self.assertEqual(card_order(self.in_progress), [("Added since", 0), ("Buy milk", 1)])
        self.assertNotContains(self.client.get(self.archive_url), "Buy milk")

    def test_restoring_a_card_whose_stage_was_deleted_puts_it_in_the_first_stage(self):
        card = a_card(self.done, "Buy milk")
        card.archive()
        self.done.delete_if_empty()
        self.board.stages.get(pk=self.in_progress.pk).shift(-1)  # now first

        self.restore(card)

        card.refresh_from_db()
        self.assertEqual(card.stage, self.in_progress)

    def test_a_stage_holding_only_archived_cards_can_be_deleted(self):
        card = a_card(self.done, "Buy milk")
        card.archive()

        response = self.client.post(
            reverse("stage_delete", args=[self.board.pk, self.done.pk])
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Stage.objects.filter(pk=self.done.pk).exists())
        card.refresh_from_db()
        self.assertIsNone(card.archived_from)
        self.assertIsNotNone(card.archived_at)

    def test_archived_cards_count_towards_no_total(self):
        a_card(self.to_do, "Kept", effort=Decimal("1"))
        a_card(self.to_do, "Gone", effort=Decimal("5")).archive()
        a_card(self.to_do, "Gone too").archive()

        content = self.client.get(self.board_url).content.decode()

        lines = [
            re.sub(r"<[^>]+>|\s+", " ", line).split()
            for line in re.findall(r'<p class="text-sm text-text-muted">Effort (.*?)</p>', content, re.S)
        ]
        self.assertEqual(lines[0], ["1", "·", "0", "unestimated"])  # board
        self.assertEqual(lines[1], ["1", "·", "0", "unestimated"])  # To Do

    def test_an_archived_card_is_never_overdue(self):
        card = a_card(self.to_do, "Buy milk", due_date=timezone.localdate() - timedelta(days=3))
        self.assertTrue(card.is_overdue)

        card.archive()

        self.assertFalse(card.is_overdue)
        detail = self.client.get(reverse("card_detail", args=[self.board.pk, card.pk]))
        self.assertNotContains(detail, "Overdue")

    def test_from_its_page_a_card_is_archived_and_restored_back_to_that_page(self):
        card = a_card(self.to_do, "Buy milk")
        detail = reverse("card_detail", args=[self.board.pk, card.pk])

        self.assertRedirects(self.archive(card, next=detail), detail)
        self.assertContains(self.client.get(detail), "Restore")
        self.assertRedirects(self.restore(card, next=detail), detail)
        card.refresh_from_db()
        self.assertEqual(card.stage, self.to_do)

    def test_a_next_page_off_this_site_is_ignored(self):
        card = a_card(self.to_do, "Buy milk")

        response = self.archive(card, next="https://evil.example.com/")

        self.assertRedirects(response, self.board_url)

    def test_archiving_or_restoring_twice_changes_nothing_more(self):
        a_card(self.to_do, "Other")
        card = a_card(self.to_do, "Buy milk")

        self.archive(card)
        self.archive(card)
        self.assertEqual(card_order(self.to_do), [("Other", 0)])
        self.restore(card)
        self.restore(card)
        self.assertEqual(card_order(self.to_do), [("Other", 0), ("Buy milk", 1)])

    def test_an_archived_card_cannot_be_moved(self):
        card = a_card(self.to_do, "Buy milk")
        card.archive()

        response = self.client.post(
            reverse("card_move", args=[self.board.pk, card.pk]), {"stage": self.done.pk}
        )

        self.assertEqual(response.status_code, 404)
        card.refresh_from_db()
        self.assertIsNone(card.stage)
        with self.assertRaises(Card.DoesNotExist):
            card.move_to(self.done)

    def test_archiving_and_restoring_need_a_post(self):
        card = a_card(self.to_do, "Buy milk")

        for name in ("card_archive", "card_restore"):
            response = self.client.get(reverse(name, args=[self.board.pk, card.pk]))
            self.assertEqual(response.status_code, 405)

    def test_the_database_refuses_a_card_half_archived(self):
        card = a_card(self.to_do, "Buy milk")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Card.objects.filter(pk=card.pk).update(archived_at=timezone.now())


class ArchivingAStageTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.to_do, self.in_progress, self.done = self.board.stages.all()
        self.client.force_login(self.ada)
        self.board_url = reverse("board_detail", args=[self.board.pk])

    def archive_stage(self, stage, expected):
        return self.client.post(
            reverse("stage_archive_cards", args=[self.board.pk, stage.pk]),
            {"expected": expected},
        )

    def page(self):
        return " ".join(self.client.get(self.board_url).content.decode().split())

    def test_a_stage_with_cards_offers_archive_all_confirmed_with_the_count(self):
        for title in ["One", "Two", "Three"]:
            a_card(self.done, title)
        a_card(self.to_do, "Single")

        content = self.page()

        self.assertIn(f'commandfor="archive-stage-{self.done.pk}"', content)
        self.assertIn("Archive 3 Cards from Done?</h2>", content)
        self.assertIn("Archive 1 Card from To Do?</h2>", content)
        action = reverse("stage_archive_cards", args=[self.board.pk, self.done.pk])
        self.assertRegex(
            content, rf'<form method="post" action="{action}"[^>]*>.*?name="expected" value="3"'
        )

    def test_a_stage_with_no_cards_does_not_offer_it(self):
        content = self.page()

        self.assertNotIn(f'commandfor="archive-stage-{self.done.pk}"', content)
        self.assertNotIn("stages/{self.done.pk}/archive/", content)
        self.assertIn('disabled class="block w-full cursor-not-allowed rounded-md px-2 py-1.5 text-left text-sm text-text-muted opacity-60">Archive all Cards</button>', content)

    def test_archiving_a_stage_archives_every_card_it_holds_and_nothing_else(self):
        cards = [a_card(self.done, title) for title in ["One", "Two", "Three"]]
        a_card(self.to_do, "Elsewhere")

        response = self.archive_stage(self.done, 3)

        self.assertRedirects(response, self.board_url, fetch_redirect_response=False)
        self.assertEqual(self.done.cards.count(), 0)
        self.assertEqual(card_order(self.to_do), [("Elsewhere", 0)])
        for card in cards:
            card.refresh_from_db()
            self.assertEqual((card.archived_from, card.stage, card.position), (self.done, None, None))
        self.assertIn("Archived 3 Cards from Done.", self.page())

    def test_the_emptied_stage_can_be_deleted_at_once(self):
        a_card(self.done, "One")
        self.archive_stage(self.done, 1)

        self.done.delete_if_empty()

        self.assertFalse(Stage.objects.filter(pk=self.done.pk).exists())

    def test_each_card_appears_in_the_archive_and_restores_to_the_stage(self):
        first, second = a_card(self.done, "One"), a_card(self.done, "Two")
        self.archive_stage(self.done, 2)

        archive = self.client.get(reverse("board_archive", args=[self.board.pk]))
        self.assertContains(archive, "One")
        self.assertContains(archive, "Two")
        second.restore()
        first.restore()

        self.assertEqual(card_order(self.done), [("Two", 0), ("One", 1)])

    def test_a_count_that_changed_since_it_was_confirmed_archives_nothing(self):
        for title in ["One", "Two", "Three"]:
            a_card(self.done, title)

        response = self.archive_stage(self.done, 2)

        self.assertRedirects(response, self.board_url, fetch_redirect_response=False)
        self.assertEqual(self.done.cards.count(), 3)
        self.assertIn("Done now holds 3 Cards, not 2. Nothing was archived.", self.page())

    def test_a_missing_or_meaningless_count_is_refused(self):
        a_card(self.done, "One")

        for expected in ["", "zero", "0", "-1"]:
            with self.subTest(expected=expected):
                self.assertEqual(self.archive_stage(self.done, expected).status_code, 400)
        self.assertEqual(self.done.cards.count(), 1)

    def test_it_needs_a_post_and_a_stage_on_this_board(self):
        other = Board.objects.create_with_owner(name="Elsewhere", owner=self.ada)
        a_card(other.stages.first(), "Not here")

        get = self.client.get(reverse("stage_archive_cards", args=[self.board.pk, self.done.pk]))
        wrong_board = self.client.post(
            reverse("stage_archive_cards", args=[self.board.pk, other.stages.first().pk]),
            {"expected": 1},
        )

        self.assertEqual((get.status_code, wrong_board.status_code), (405, 404))
        self.assertEqual(other.stages.first().cards.count(), 1)

    def test_a_card_added_just_before_the_lock_refuses_the_whole_action(self):
        a_card(self.done, "One")
        real = models.lock_stages
        pending = [lambda: a_card(self.done, "Added meanwhile")]

        def lock_stages(*ids):
            if pending:
                pending.pop()()
            return real(*ids)

        with mock.patch.object(models, "lock_stages", lock_stages):
            response = self.archive_stage(self.done, 1)

        # The staged addition shares the refused transaction, so it is rolled
        # back with it: what matters is that "One" was not archived.
        self.assertRedirects(response, self.board_url, fetch_redirect_response=False)
        self.assertIn("Done now holds 2 Cards, not 1. Nothing was archived.", self.page())
        self.assertEqual(card_order(self.done), [("One", 0)])


class ArchiveAccessTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.card = a_card(self.board.stages.first(), "Buy milk")
        self.client.force_login(self.grace)

    def test_a_non_member_can_neither_archive_nor_restore_nor_see_the_archive(self):
        archive = self.client.post(
            reverse("card_archive", args=[self.board.pk, self.card.pk])
        )
        self.card.archive()
        restore = self.client.post(
            reverse("card_restore", args=[self.board.pk, self.card.pk])
        )
        page = self.client.get(reverse("board_archive", args=[self.board.pk]))
        detail = self.client.get(reverse("card_detail", args=[self.board.pk, self.card.pk]))

        self.assertEqual(
            [r.status_code for r in (archive, restore, page, detail)], [404] * 4
        )
        self.card.refresh_from_db()
        self.assertIsNotNone(self.card.archived_at)

    def test_a_non_member_cannot_archive_a_stage(self):
        stage = self.board.stages.first()

        response = self.client.post(
            reverse("stage_archive_cards", args=[self.board.pk, stage.pk]), {"expected": 1}
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(stage.cards.count(), 1)

    def test_a_card_is_not_reachable_through_another_board(self):
        """Even one the person is a Member of."""
        own = Board.objects.create_with_owner(name="Own", owner=self.grace)
        self.card.archive()

        response = self.client.get(reverse("card_detail", args=[own.pk, self.card.pk]))

        self.assertEqual(response.status_code, 404)


class StagedArchiveRaceTests(TestCase):
    """Races whose window is too narrow to hit with threads, staged by making
    the other request's change just before the Stage lock is taken."""

    def setUp(self):
        self.board = Board.objects.create_with_owner(name="Housework", owner=a_user())
        self.to_do, self.in_progress, self.done = self.board.stages.all()

    def meanwhile(self, change):
        """Patch lock_stages so `change` happens once, just before it."""
        real = models.lock_stages
        pending = [change]

        def lock_stages(*ids):
            if pending:
                pending.pop()()
            return real(*ids)

        return mock.patch.object(models, "lock_stages", lock_stages)

    def test_a_card_moved_just_before_it_is_archived_is_archived_from_its_new_stage(self):
        card = a_card(self.to_do)

        with self.meanwhile(lambda: Card.objects.get(pk=card.pk).move_to(self.done)):
            card.archive()

        self.assertEqual(card.archived_from, self.done)

    def test_a_stage_deleted_just_before_its_card_is_restored_sends_it_to_the_first(self):
        card = a_card(self.done)
        card.archive()

        with self.meanwhile(lambda: Stage.objects.get(pk=self.done.pk).delete_if_empty()):
            card.restore()

        self.assertEqual(card.stage, self.to_do)


    def test_a_card_archived_again_elsewhere_just_before_it_is_restored_goes_there(self):
        card = a_card(self.done)
        card.archive()

        def restored_moved_and_archived_again():
            other = Card.objects.get(pk=card.pk)
            other.restore()
            other.move_to(self.in_progress)
            other.archive()

        with self.meanwhile(restored_moved_and_archived_again):
            card.restore()

        self.assertEqual(card.stage, self.in_progress)

class ConcurrentArchiveTests(TransactionTestCase):
    """Archive and Restore racing other writes, each on its own connection."""

    def setUp(self):
        self.board = Board.objects.create_with_owner(name="Housework", owner=a_user())
        self.to_do, self.in_progress, self.done = self.board.stages.all()

    def run_together(self, *actions):
        """Run the actions at once and return what each raised, or None."""
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

    def assertContiguous(self, stage):
        positions = [c.position for c in stage.cards.all()]
        self.assertEqual(positions, list(range(len(positions))))

    def test_archiving_while_others_move_keeps_card_order_contiguous(self):
        cards = [a_card(self.to_do, f"Card {i}") for i in range(6)]

        outcomes = self.run_together(
            *[lambda card=card: Card.objects.get(pk=card.pk).archive() for card in cards[::2]],
            *[lambda card=card: Card.objects.get(pk=card.pk).move_to(self.done, 0) for card in cards[1::2]],
        )

        self.assertEqual(outcomes, [None] * 6)
        self.assertEqual(self.to_do.cards.count(), 0)
        self.assertContiguous(self.done)

    def test_restoring_while_others_are_added_keeps_card_order_contiguous(self):
        cards = [a_card(self.to_do, f"Card {i}") for i in range(3)]
        for card in cards:
            card.archive()

        outcomes = self.run_together(
            *[lambda card=card: Card.objects.get(pk=card.pk).restore() for card in cards],
            *[lambda i=i: a_card(self.to_do, f"New {i}") for i in range(3)],
        )

        self.assertEqual(outcomes, [None] * 6)
        self.assertEqual(self.to_do.cards.count(), 6)
        self.assertContiguous(self.to_do)

    def test_one_card_archived_and_moved_at_once_ends_up_archived(self):
        for _ in range(5):
            card = a_card(self.to_do, "Contested")
            a_card(self.to_do, "After")

            archive, move = self.run_together(
                lambda: Card.objects.get(pk=card.pk).archive(),
                lambda: Card.objects.get(pk=card.pk).move_to(self.done),
            )

            # Whichever goes first, the archive wins: after a move it starts
            # over from the new Stage, and a move after it finds no Card.
            card.refresh_from_db()
            self.assertIsNotNone(card.archived_at)
            self.assertIsNone(archive)
            self.assertTrue(move is None or isinstance(move, Card.DoesNotExist), move)
            self.assertEqual(card_order(self.to_do), [("After", 0)])
            self.assertEqual(self.done.cards.count(), 0)
            Card.objects.all().delete()

    def test_two_restores_at_once_restore_the_card_once(self):
        for _ in range(5):
            a_card(self.in_progress, "Staying")
            card = a_card(self.in_progress, "Contested")
            card.archive()

            outcomes = self.run_together(
                lambda: Card.objects.get(pk=card.pk).restore(),
                lambda: Card.objects.get(pk=card.pk).restore(),
            )

            self.assertEqual(outcomes, [None, None])
            self.assertEqual(card_order(self.in_progress), [("Staying", 0), ("Contested", 1)])
            Card.objects.all().delete()

    def test_a_stage_deleted_while_its_card_is_restored_never_loses_the_card(self):
        for _ in range(5):
            Stage.objects.filter(board=self.board, name="Target").delete()
            target = self.board.add_stage("Target")
            card = a_card(target)
            card.archive()

            delete, restore = self.run_together(
                lambda: Stage.objects.get(pk=target.pk).delete_if_empty(),
                lambda: Card.objects.get(pk=card.pk).restore(),
            )

            self.assertIsNone(restore)
            card.refresh_from_db()
            self.assertIsNone(card.archived_at)
            if Stage.objects.filter(pk=target.pk).exists():
                # The restore won: the delete was refused because of the Card.
                self.assertEqual(card.stage_id, target.pk)
                self.assertIn("Still holds 1 Card", str(delete))
            else:
                # The delete won: the Card went to the first Stage instead.
                self.assertIsNone(delete)
                self.assertEqual(card.stage, self.to_do)
            Card.objects.all().delete()


    def test_a_stage_archived_while_cards_arrive_archives_all_or_nothing(self):
        for _ in range(5):
            for i in range(3):
                a_card(self.done, f"Card {i}")
            mover = a_card(self.to_do, "Mover")

            archive, add, move = self.run_together(
                lambda: Stage.objects.get(pk=self.done.pk).archive_cards(3),
                lambda: a_card(self.done, "New"),
                lambda: Card.objects.get(pk=mover.pk).move_to(self.done),
            )

            self.assertEqual((add, move), (None, None))
            on_board = self.done.cards.count()
            if archive is None:
                # Archived first: the two arrivals are all that's left.
                self.assertEqual(on_board, 2)
                self.assertEqual(Card.objects.filter(archived_from=self.done).count(), 3)
            else:
                # An arrival got in first: the count no longer matched.
                self.assertIn("Nothing was archived", str(archive))
                self.assertGreaterEqual(on_board, 4)
                self.assertFalse(Card.objects.filter(archived_at__isnull=False).exists())
            self.assertContiguous(self.done)
            Card.objects.all().delete()
