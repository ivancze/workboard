import re
import threading
from decimal import Decimal
from unittest import mock

from django.db import connection
from django.db.models.query import QuerySet
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from boards.forms import CardForm
from boards.models import Board, Card

from .test_cards import a_card, a_user
from .test_moving import card_order


class DeletingACardTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.to_do, self.in_progress, self.done = self.board.stages.all()
        self.client.force_login(self.ada)
        self.board_url = reverse("board_detail", args=[self.board.pk])
        self.archive_url = reverse("board_archive", args=[self.board.pk])

    def delete(self, card, **data):
        return self.client.post(reverse("card_delete", args=[self.board.pk, card.pk]), data)

    def text(self, url):
        return " ".join(self.client.get(url).content.decode().split())

    def test_deletion_is_confirmed_by_a_dialog_naming_the_card(self):
        card = a_card(self.to_do, "Buy milk")

        for url in (self.board_url, reverse("card_detail", args=[self.board.pk, card.pk])):
            with self.subTest(url=url):
                content = self.text(url)
                # The only way to Delete is the button that opens the dialog.
                self.assertIn(f'commandfor="delete-card-{card.pk}" command="show-modal"', content)
                dialog = re.search(rf'<dialog id="delete-card-{card.pk}".*?</dialog>', content).group()
                self.assertIn("Delete Buy milk?</h2>", dialog)
                self.assertIn("can't be undone", dialog)
                action = reverse("card_delete", args=[self.board.pk, card.pk])
                self.assertIn(f'<form method="post" action="{action}"', dialog)

    def test_a_card_deleted_from_the_board_is_gone_and_the_gap_closes(self):
        a_card(self.to_do, "First", effort=Decimal("1"))
        card = a_card(self.to_do, "Buy milk", effort=Decimal("5"))
        a_card(self.to_do, "Last", effort=Decimal("1"))

        response = self.delete(card)

        self.assertRedirects(response, self.board_url, fetch_redirect_response=False)
        self.assertFalse(Card.objects.filter(pk=card.pk).exists())
        self.assertEqual(card_order(self.to_do), [("First", 0), ("Last", 1)])
        content = self.text(self.board_url)
        self.assertIn("Deleted Buy milk.", content)
        self.assertIn('Effort <span class="font-semibold text-text">2</span>', content)

    def test_a_card_deleted_from_the_archive_is_gone_from_it(self):
        card = a_card(self.to_do, "Buy milk")
        card.archive()

        response = self.delete(card, next=self.archive_url)

        self.assertRedirects(response, self.archive_url, fetch_redirect_response=False)
        content = self.text(self.archive_url)
        self.assertIn("Deleted Buy milk.", content)
        self.assertIn("Nothing archived yet.", content)

    def test_the_archive_offers_delete_for_each_card(self):
        card = a_card(self.to_do, "Buy milk")
        card.archive()

        content = self.text(self.archive_url)

        self.assertIn(f'commandfor="delete-card-{card.pk}"', content)
        self.assertRegex(content, rf'<dialog id="delete-card-{card.pk}".*?name="next" value="{self.archive_url}"')

    def test_from_its_page_a_deleted_card_returns_to_where_it_lived(self):
        live, archived = a_card(self.to_do, "Live"), a_card(self.to_do, "Archived")
        archived.archive()

        for card, home in [(live, self.board_url), (archived, self.archive_url)]:
            with self.subTest(card=card.title):
                page = self.text(reverse("card_detail", args=[self.board.pk, card.pk]))
                dialog = re.search(rf'<dialog id="delete-card-{card.pk}".*?</dialog>', page).group()
                next_page = re.search(r'name="next" value="([^"]+)"', dialog)
                self.assertEqual(next_page.group(1) if next_page else self.board_url, home)

    def test_nothing_offers_to_undo_or_recover_a_deletion(self):
        card = a_card(self.to_do, "Buy milk")
        self.delete(card)

        content = self.text(self.board_url)

        self.assertNotIn("Undo", content)
        self.assertNotIn(f"/cards/{card.pk}/", content)
        for name in ("card_detail", "card_restore"):
            method = self.client.get if name == "card_detail" else self.client.post
            self.assertEqual(method(reverse(name, args=[self.board.pk, card.pk])).status_code, 404)

    def test_archive_stays_the_prominent_action_and_delete_the_quieter_one(self):
        card = a_card(self.to_do, "Buy milk")

        board = self.text(self.board_url)
        menu = re.search(r"<details data-menu class=\"absolute.*?</details>", board).group()
        # In the Card menu, Delete comes after Archive, smaller and muted.
        self.assertLess(menu.index(">Archive</button>"), menu.index(">Delete…</button>"))
        self.assertRegex(menu, r'class="[^"]*text-xs text-text-muted[^"]*">Delete…</button>')
        # On the Card page, Archive is a button by the title; Delete is a ghost
        # button below everything else.
        page = self.text(reverse("card_detail", args=[self.board.pk, card.pk]))
        self.assertLess(page.index(">Archive</button>"), page.index("No description."))
        self.assertLess(page.index("No description."), page.index(">Delete Card…</button>"))
        self.assertRegex(page, r'class="[^"]*text-text-muted hover:bg-sunken[^"]*">Delete Card…</button>')

    def test_deleting_needs_a_post_and_a_member(self):
        card = a_card(self.to_do, "Buy milk")
        get = self.client.get(reverse("card_delete", args=[self.board.pk, card.pk]))
        self.client.force_login(a_user("grace@example.com"))

        stranger = self.delete(card)

        self.assertEqual((get.status_code, stranger.status_code), (405, 404))
        self.assertTrue(Card.objects.filter(pk=card.pk).exists())

    def test_an_edit_saved_after_the_card_was_deleted_is_a_404(self):
        card = a_card(self.to_do, "Buy milk")
        is_valid = CardForm.is_valid

        def deleted_meanwhile(form):
            # The edit request has already loaded the Card; someone deletes it.
            Card.objects.get(pk=card.pk).delete()
            return is_valid(form)

        with mock.patch.object(CardForm, "is_valid", deleted_meanwhile):
            response = self.client.post(
                reverse("card_edit", args=[self.board.pk, card.pk]), {"title": "Buy oat milk"}
            )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Card.objects.filter(pk=card.pk).exists())

    def test_archiving_or_restoring_a_card_deleted_meanwhile_is_a_404(self):
        card = a_card(self.to_do, "Buy milk")

        for name in ("archive", "restore"):
            with self.subTest(name=name):
                with mock.patch.object(Card, name, side_effect=Card.DoesNotExist):
                    response = self.client.post(
                        reverse(f"card_{name}", args=[self.board.pk, card.pk])
                    )
                self.assertEqual(response.status_code, 404)

    def test_an_archived_card_restored_just_before_its_delete_still_leaves_no_gap(self):
        card = a_card(self.to_do, "Buy milk")
        card.archive()
        real = QuerySet.delete
        pending = [lambda: (Card.objects.get(pk=card.pk).restore(), a_card(self.to_do, "Below"))]

        def delete(queryset):
            if pending:
                pending.pop()()
            return real(queryset)

        with mock.patch.object(QuerySet, "delete", delete):
            Card.objects.get(pk=card.pk).delete()

        self.assertEqual(card_order(self.to_do), [("Below", 0)])


class ConcurrentDeleteTests(TransactionTestCase):
    """Deletes racing other writes to Card order, each on its own connection."""

    def setUp(self):
        self.board = Board.objects.create_with_owner(name="Housework", owner=a_user())
        self.to_do, self.in_progress, self.done = self.board.stages.all()

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

    def assertContiguous(self, stage):
        positions = [c.position for c in stage.cards.all()]
        self.assertEqual(positions, list(range(len(positions))))

    def test_deleting_while_others_move_keeps_card_order_contiguous(self):
        cards = [a_card(self.to_do, f"Card {i}") for i in range(6)]

        outcomes = self.run_together(
            *[lambda card=card: Card.objects.get(pk=card.pk).delete() for card in cards[::2]],
            *[lambda card=card: Card.objects.get(pk=card.pk).move_to(self.done, 0) for card in cards[1::2]],
        )

        self.assertEqual(outcomes, [None] * 6)
        self.assertEqual(Card.objects.count(), 3)
        self.assertContiguous(self.to_do)
        self.assertContiguous(self.done)

    def test_one_card_deleted_and_moved_at_once_is_deleted(self):
        for _ in range(5):
            card = a_card(self.to_do, "Contested")
            a_card(self.to_do, "After")
            a_card(self.done, "Waiting")

            delete, move = self.run_together(
                lambda: Card.objects.get(pk=card.pk).delete(),
                lambda: Card.objects.get(pk=card.pk).move_to(self.done, 0),
            )

            self.assertIsNone(delete)
            self.assertTrue(move is None or isinstance(move, Card.DoesNotExist), move)
            self.assertFalse(Card.objects.filter(pk=card.pk).exists())
            self.assertEqual(card_order(self.to_do), [("After", 0)])
            self.assertEqual(card_order(self.done), [("Waiting", 0)])
            Card.objects.all().delete()
