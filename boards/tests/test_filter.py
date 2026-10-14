import re
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from boards.models import Board, Card, Membership

from .test_cards import a_card, a_user
from .test_moving import card_order


class FilteringByAssigneeTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        Membership.objects.create(board=self.board, user=self.grace)
        Membership.objects.create(board=self.board, email="pending@example.com")
        self.to_do, self.in_progress, self.done = self.board.stages.all()
        a_card(self.to_do, "Ada one", assignee=self.ada, effort=Decimal("2"))
        a_card(self.to_do, "Grace one", assignee=self.grace, effort=Decimal("3"))
        a_card(self.to_do, "Unowned", effort=None)
        a_card(self.to_do, "Ada two", assignee=self.ada)
        a_card(self.done, "Grace done", assignee=self.grace, effort=Decimal("1"))
        self.client.force_login(self.ada)
        self.url = reverse("board_detail", args=[self.board.pk])

    def page(self, query=""):
        return " ".join(self.client.get(self.url + query).content.decode().split())

    def shown(self, content):
        return re.findall(r'<span class="block font-semibold">([^<]+)</span>', content)

    def test_the_filter_lists_everyone_mine_unassigned_and_each_member(self):
        content = self.page()

        form = re.search(r"<form method=\"get\".*?</form>", content).group()
        options = re.findall(r'<option value="([^"]*)"[^>]*>([^<]+)</option>', form)
        self.assertEqual(
            options,
            [
                ("", "Everyone"),
                ("me", "Mine"),
                ("unassigned", "Unassigned"),
                (str(self.ada.pk), "ada"),
                (str(self.grace.pk), "grace"),
            ],
        )
        self.assertIn('name="assignee"', form)
        self.assertIn(f'action="{self.url}"', form)

    def test_choosing_a_member_shows_only_their_cards_in_card_order(self):
        content = self.page(f"?assignee={self.grace.pk}")

        self.assertEqual(self.shown(content), ["Grace one", "Grace done"])
        self.assertRegex(content, rf'<option value="{self.grace.pk}" selected>')

    def test_mine_shows_the_viewers_cards_and_unassigned_shows_cards_with_none(self):
        self.assertEqual(self.shown(self.page("?assignee=me")), ["Ada one", "Ada two"])
        self.assertEqual(self.shown(self.page("?assignee=unassigned")), ["Unowned"])

    def test_someone_not_a_member_falls_back_to_everyone_and_says_so(self):
        removed = a_user("gone@example.com")

        for value in [str(removed.pk), "999999", "nonsense"]:
            with self.subTest(value=value):
                content = self.page(f"?assignee={value}")
                self.assertEqual(len(self.shown(content)), 5)
                self.assertIn("That person is not a Member of this board, so every Card is shown.", content)
                self.assertRegex(content, r'<option value="" selected>Everyone')

    def test_filtering_changes_no_order_and_nobody_elses_view(self):
        before = card_order(self.to_do)
        self.page("?assignee=me")

        self.assertEqual(card_order(self.to_do), before)
        self.client.force_login(self.grace)
        self.assertEqual(len(self.shown(self.page())), 5)

    def test_the_boards_totals_still_cover_every_card_with_the_shown_ones_beside(self):
        content = self.page(f"?assignee={self.grace.pk}")

        lines = re.findall(r'<p class="text-sm text-text-muted">(Shown: )?Effort (.*?)</p>', content)
        figures = [(label, re.sub(r"<[^>]+>", "", value)) for label, value in lines]
        self.assertEqual(
            figures[:5],
            [
                ("", "6 · 2 unestimated"),  # the board, every Card
                ("Shown: ", "4 · 0 unestimated"),  # the board, Grace's
                ("", "5 · 2 unestimated"),  # To Do, every Card
                ("Shown: ", "3 · 0 unestimated"),  # To Do, Grace's
                ("", "0 · 0 unestimated"),  # In Progress
            ],
        )

    def test_without_a_filter_only_the_boards_totals_show(self):
        self.assertNotIn("Shown:", self.page())

    def test_a_stage_whose_cards_are_all_hidden_says_so_and_still_takes_drops(self):
        content = self.page("?assignee=unassigned")

        self.assertIn("1 Card, none matching the filter.", content)  # Done
        self.assertNotIn("No cards yet.", content)  # In Progress, truly empty
        self.assertIn(f'data-stage="{self.done.pk}"', content)

    def test_dragging_keeps_the_filter(self):
        card = Card.objects.get(title="Ada one")
        query = "?assignee=me"

        content = self.page(query)
        self.assertIn(f'data-move-url="{reverse("card_move", args=[self.board.pk, card.pk])}{query}"', content)
        self.assertIn(f'data-board-url="{self.url}{query}"', content)
        fragment = self.client.post(
            reverse("card_move", args=[self.board.pk, card.pk]) + query,
            {"stage": self.done.pk},
            headers={"HX-Request": "true"},
        ).content.decode()

        self.assertEqual(self.shown(fragment), ["Ada two", "Ada one"])

    def test_moving_archiving_and_deleting_from_the_board_keep_the_filter(self):
        card = Card.objects.get(title="Ada one")
        query = "?assignee=me"
        content = self.page(query)

        for name, data in [
            ("card_move", {"stage": self.done.pk}),
            ("card_archive", {}),
            ("card_delete", {}),
        ]:
            with self.subTest(name=name):
                action = reverse(name, args=[self.board.pk, card.pk]) + query
                self.assertIn(f'action="{action}"', content)
                response = self.client.post(action, data)
                self.assertRedirects(response, self.url + query, fetch_redirect_response=False)
                if name == "card_archive":
                    card.restore()

    def test_archiving_a_stage_keeps_the_filter_and_counts_the_hidden_cards_too(self):
        query = "?assignee=me"
        content = self.page(query)

        action = reverse("stage_archive_cards", args=[self.board.pk, self.to_do.pk]) + query
        self.assertIn(f'action="{action}"', content)
        self.assertIn("Archive 4 Cards from To Do?</h2>", content)
        self.assertIn("This includes Cards hidden by the filter.", content)
        response = self.client.post(action, {"expected": 4})
        self.assertRedirects(response, self.url + query, fetch_redirect_response=False)
        self.assertEqual(self.to_do.cards.count(), 0)

    def test_adding_a_card_keeps_the_filter(self):
        query = f"?assignee={self.grace.pk}"
        new = reverse("card_create", args=[self.board.pk]) + query

        self.assertIn(f'href="{new}"', self.page(query))
        self.assertIn(f'href="{self.url}{query}"', self.client.get(new).content.decode())
        response = self.client.post(new, {"title": "Another"})
        self.assertRedirects(response, self.url + query, fetch_redirect_response=False)

    def test_returning_from_a_card_page_keeps_the_filter(self):
        card = Card.objects.get(title="Ada one")
        query = "?assignee=me"
        detail = reverse("card_detail", args=[self.board.pk, card.pk]) + query
        edit = reverse("card_edit", args=[self.board.pk, card.pk]) + query

        self.assertIn(f'href="{detail}"', self.page(query))
        page = self.client.get(detail).content.decode()
        self.assertIn(f'href="{self.url}{query}"', page)
        self.assertIn(f'href="{edit}"', page)
        self.assertIn(f'href="{detail}"', self.client.get(edit).content.decode())
        response = self.client.post(edit, {"title": "Ada one"})
        self.assertRedirects(response, detail, fetch_redirect_response=False)
