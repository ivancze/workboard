import re
import threading
from unittest import mock

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from boards.forms import CardForm
from boards.models import Board, Card

from .test_cards import a_card, a_user


def card_order(stage):
    return [(c.title, c.position) for c in stage.cards.all()]


class MovingACardTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.to_do, self.in_progress, self.done = self.board.stages.all()
        self.client.force_login(self.ada)

    def move(self, card, stage_pk):
        return self.client.post(
            reverse("card_move", args=[self.board.pk, card.pk]), {"stage": stage_pk}
        )

    def test_each_card_offers_the_boards_other_stages(self):
        card = a_card(self.to_do, "Buy milk")

        content = self.client.get(
            reverse("board_detail", args=[self.board.pk])
        ).content.decode()

        action = reverse("card_move", args=[self.board.pk, card.pk])
        form = re.search(rf'<form method="post" action="{action}".*?</form>', content, re.S)
        # One submit button per other Stage, so a click moves the Card with no
        # JavaScript and no dropdown to open first.
        buttons = re.findall(
            r'<button type="submit" name="stage" value="(\d+)"[^>]*>([^<]+)</button>',
            form.group(),
        )
        self.assertEqual(
            buttons,
            [(str(self.in_progress.pk), "In Progress"), (str(self.done.pk), "Done")],
        )

    def test_choosing_a_stage_moves_the_card_and_survives_a_reload(self):
        card = a_card(self.to_do, "Buy milk")

        response = self.move(card, self.done.pk)

        self.assertRedirects(response, reverse("board_detail", args=[self.board.pk]))
        card.refresh_from_db()
        self.assertEqual(card.stage, self.done)
        content = self.client.get(response.url).content.decode()
        self.assertLess(content.index('<h2 class="font-condensed text-2xl tracking-wide">Done'), content.index("Buy milk"))

    def test_a_moved_card_lands_at_the_end_of_its_new_stage(self):
        a_card(self.done, "Already done")
        a_card(self.done, "Also done")
        card = a_card(self.to_do, "Buy milk")

        self.move(card, self.done.pk)

        self.assertEqual(
            card_order(self.done),
            [("Already done", 0), ("Also done", 1), ("Buy milk", 2)],
        )

    def test_both_stages_stay_contiguous(self):
        for title in ["First", "Second", "Third"]:
            a_card(self.to_do, title)
        a_card(self.done, "Done one")

        self.move(Card.objects.get(title="Second"), self.done.pk)

        self.assertEqual(card_order(self.to_do), [("First", 0), ("Third", 1)])
        self.assertEqual(card_order(self.done), [("Done one", 0), ("Second", 1)])

    def test_moving_to_its_own_stage_changes_nothing(self):
        a_card(self.to_do, "First")
        card = a_card(self.to_do, "Second")

        self.move(card, self.to_do.pk)

        self.assertEqual(card_order(self.to_do), [("First", 0), ("Second", 1)])

    def test_an_edit_saved_after_a_move_does_not_undo_it(self):
        card = a_card(self.to_do, "Buy milk")
        edit = reverse("card_edit", args=[self.board.pk, card.pk])
        is_valid = CardForm.is_valid

        def moved_meanwhile(form):
            # The edit request has already loaded the Card; someone moves it.
            Card.objects.get(pk=card.pk).move_to(self.done)
            return is_valid(form)

        with mock.patch.object(CardForm, "is_valid", moved_meanwhile):
            self.client.post(edit, {"title": "Buy oat milk"})

        card.refresh_from_db()
        self.assertEqual((card.title, card.stage, card.position), ("Buy oat milk", self.done, 0))

    def test_moving_needs_a_post(self):
        card = a_card(self.to_do)

        response = self.client.get(reverse("card_move", args=[self.board.pk, card.pk]))

        self.assertEqual(response.status_code, 405)


class DragAndDropTests(TestCase):
    """A drop sends the Card's new Stage and its position there, from 0."""

    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.to_do, self.in_progress, self.done = self.board.stages.all()
        for title in ["A", "B", "C", "D"]:
            a_card(self.to_do, title)
        for title in ["X", "Y"]:
            a_card(self.done, title)
        self.client.force_login(self.ada)

    def drop(self, title, stage, position, **headers):
        card = Card.objects.get(title=title)
        return self.client.post(
            reverse("card_move", args=[self.board.pk, card.pk]),
            {"stage": stage.pk, "position": position},
            headers=headers,
        )

    def titles(self, stage):
        order = card_order(stage)
        self.assertEqual([p for _, p in order], list(range(len(order))))
        return [t for t, _ in order]

    def test_dragging_down_within_a_stage(self):
        self.drop("A", self.to_do, 2)

        self.assertEqual(self.titles(self.to_do), ["B", "C", "A", "D"])

    def test_dragging_up_within_a_stage(self):
        self.drop("D", self.to_do, 1)

        self.assertEqual(self.titles(self.to_do), ["A", "D", "B", "C"])

    def test_dragging_to_the_top_and_bottom_of_its_stage(self):
        self.drop("C", self.to_do, 0)
        self.assertEqual(self.titles(self.to_do), ["C", "A", "B", "D"])

        self.drop("A", self.to_do, 3)
        self.assertEqual(self.titles(self.to_do), ["C", "B", "D", "A"])

    def test_dropping_where_it_already_is_changes_nothing(self):
        self.drop("B", self.to_do, 1)

        self.assertEqual(self.titles(self.to_do), ["A", "B", "C", "D"])

    def test_a_card_dropped_into_another_stage_lands_where_it_was_dropped(self):
        self.drop("B", self.done, 1)

        self.assertEqual(self.titles(self.done), ["X", "B", "Y"])
        self.assertEqual(self.titles(self.to_do), ["A", "C", "D"])

    def test_a_card_dropped_at_the_top_of_another_stage(self):
        self.drop("D", self.done, 0)

        self.assertEqual(self.titles(self.done), ["D", "X", "Y"])

    def test_a_card_dropped_into_an_empty_stage(self):
        self.drop("A", self.in_progress, 0)

        self.assertEqual(self.titles(self.in_progress), ["A"])
        self.assertEqual(self.titles(self.to_do), ["B", "C", "D"])

    def test_a_position_past_the_end_means_the_end(self):
        self.drop("A", self.to_do, 99)
        self.drop("B", self.done, 99)

        self.assertEqual(self.titles(self.to_do), ["C", "D", "A"])
        self.assertEqual(self.titles(self.done), ["X", "Y", "B"])

    def test_a_negative_or_malformed_position_is_refused(self):
        for position in ["-1", "first", "1.5"]:
            with self.subTest(position=position):
                self.assertEqual(self.drop("A", self.done, position).status_code, 400)

        self.assertEqual(self.titles(self.to_do), ["A", "B", "C", "D"])

    def test_a_drag_gets_the_fresh_board_back_instead_of_a_redirect(self):
        response = self.drop("A", self.done, 0, HX_Request="true")

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertTrue(content.lstrip().startswith('<div id="board"'))
        self.assertNotIn("<html", content)
        # Totals come back too: Done had two Unestimated Cards and gained one.
        self.assertRegex(content, r"Done</h2>\s*<p[^>]*>Effort <span[^>]*>0</span> · 3 unestimated")
        self.assertLess(content.index(">A<"), content.index(">X<"))

    def test_the_board_page_loads_drag_and_drop_and_sends_csrf_with_htmx(self):
        content = self.client.get(
            reverse("board_detail", args=[self.board.pk])
        ).content.decode()

        for script in ["vendor/htmx.min.js", "vendor/Sortable.min.js", "js/board.js"]:
            self.assertIn(f'src="/static/{script}"', content)
        self.assertIn("hx-headers='{\"X-CSRFToken\": ", content)
        self.assertEqual(content.count("data-card-list"), 3)  # empty Stages too


class MoveAccessTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.adas_board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.graces_board = Board.objects.create_with_owner(
            name="Secret Plans", owner=self.grace
        )
        self.adas_card = a_card(self.adas_board.stages.first(), "Mine")
        self.graces_card = a_card(self.graces_board.stages.first(), "Hidden card")
        self.client.force_login(self.ada)

    def test_a_card_cannot_be_moved_into_another_boards_stage(self):
        their_stage = self.graces_board.stages.last()

        response = self.client.post(
            reverse("card_move", args=[self.adas_board.pk, self.adas_card.pk]),
            {"stage": their_stage.pk},
        )

        self.assertEqual(response.status_code, 404)
        self.adas_card.refresh_from_db()
        self.assertEqual(self.adas_card.stage, self.adas_board.stages.first())
        self.assertFalse(their_stage.cards.exists())

    def test_a_non_member_cannot_move_a_card_by_its_identifier(self):
        for board in [self.graces_board, self.adas_board]:
            for stage in [*self.graces_board.stages.all(), *self.adas_board.stages.all()]:
                response = self.client.post(
                    reverse("card_move", args=[board.pk, self.graces_card.pk]),
                    {"stage": stage.pk},
                )
                self.assertEqual(response.status_code, 404)

        self.graces_card.refresh_from_db()
        self.assertEqual(self.graces_card.stage, self.graces_board.stages.first())

    def test_a_missing_or_malformed_stage_is_refused(self):
        url = reverse("card_move", args=[self.adas_board.pk, self.adas_card.pk])
        for data in [{}, {"stage": ""}, {"stage": "abc"}]:
            with self.subTest(data=data):
                self.assertEqual(self.client.post(url, data).status_code, 404)

    def test_an_anonymous_visitor_is_sent_to_sign_in(self):
        self.client.logout()

        response = self.client.post(
            reverse("card_move", args=[self.adas_board.pk, self.adas_card.pk]),
            {"stage": self.adas_board.stages.last().pk},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response.url)
        self.assertEqual(self.adas_card.stage, self.adas_board.stages.first())


class ConcurrentCardOrderTests(TransactionTestCase):
    """Requests that rewrite Card order at the same moment, each on its own
    database connection, as they would arrive from different people."""

    def setUp(self):
        self.board = Board.objects.create_with_owner(name="Housework", owner=a_user())
        self.to_do, self.in_progress, self.done = self.board.stages.all()

    def run_together(self, *actions):
        start = threading.Barrier(len(actions))
        errors = []

        def run(action):
            try:
                start.wait()
                action()
            except Exception as error:  # surfaced below, with the others
                errors.append(error)
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(action,)) for action in actions]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])

    def assertContiguous(self, stage, count):
        self.assertEqual([c.position for c in stage.cards.all()], list(range(count)))

    def test_cards_moved_at_the_same_moment_keep_card_order_contiguous(self):
        cards = [a_card(self.to_do, f"Card {i}") for i in range(6)]

        self.run_together(
            *[lambda card=card, i=i: card.move_to([self.in_progress, self.done][i % 2]) for i, card in enumerate(cards)]
        )

        self.assertContiguous(self.to_do, 0)
        self.assertContiguous(self.in_progress, 3)
        self.assertContiguous(self.done, 3)

    def test_one_card_moved_two_ways_at_once_ends_up_in_one_place(self):
        a_card(self.to_do, "Before")
        card = a_card(self.to_do, "Contested")
        a_card(self.to_do, "After")

        self.run_together(
            lambda: Card.objects.get(pk=card.pk).move_to(self.in_progress),
            lambda: Card.objects.get(pk=card.pk).move_to(self.done),
        )

        self.assertContiguous(self.to_do, 2)
        self.assertEqual(self.in_progress.cards.count() + self.done.cards.count(), 1)

    def test_cards_added_at_the_same_moment_get_distinct_positions(self):
        self.run_together(
            *[lambda i=i: a_card(self.to_do, f"Card {i}") for i in range(6)]
        )

        self.assertContiguous(self.to_do, 6)

    def test_adding_and_moving_into_a_stage_at_once_keeps_it_contiguous(self):
        movers = [a_card(self.to_do, f"Mover {i}") for i in range(3)]

        self.run_together(
            *[lambda card=card: card.move_to(self.done) for card in movers],
            *[lambda i=i: a_card(self.done, f"New {i}") for i in range(3)],
        )

        self.assertContiguous(self.done, 6)
        self.assertContiguous(self.to_do, 0)

    def test_cards_reordered_at_the_same_moment_stay_contiguous(self):
        cards = [a_card(self.to_do, f"Card {i}") for i in range(6)]

        self.run_together(
            *[lambda card=card, i=i: card.move_to(self.to_do, 5 - i) for i, card in enumerate(cards)],
            *[lambda card=card: card.move_to(self.done, 0) for card in cards[:2]],
        )

        self.assertEqual(
            len(self.to_do.cards.all()) + len(self.done.cards.all()), 6
        )
        self.assertContiguous(self.to_do, self.to_do.cards.count())
        self.assertContiguous(self.done, self.done.cards.count())

    def test_the_database_refuses_two_cards_in_one_position(self):
        """The backstop if code ever gets Card order wrong: checked at commit."""
        card = a_card(self.to_do, "First")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Card.objects.create(
                    stage=self.to_do, position=card.position, title="Clash", creator=card.creator
                )
