from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from boards.models import Board, Card, Membership


def a_user(email="ada@example.com"):
    return User.objects.create_user(email=email, display_name=email.split("@")[0])


def a_card(stage, title="Buy milk", creator=None, **fields):
    return Card.objects.create_at_end(
        stage=stage, title=title, creator=creator or stage.board.owner, **fields
    )


class AddingACardTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.to_do, self.in_progress, _ = self.board.stages.all()
        self.client.force_login(self.ada)

    def add(self, stage, title):
        return self.client.post(
            reverse("card_create", args=[self.board.pk, stage.pk]), {"title": title}
        )

    def test_a_card_added_to_a_stage_appears_in_that_stage(self):
        self.add(self.in_progress, "Buy milk")

        card = Card.objects.get()
        self.assertEqual(card.stage, self.in_progress)
        response = self.client.get(reverse("board_detail", args=[self.board.pk]))
        content = response.content.decode()
        self.assertLess(content.index("In Progress"), content.index("Buy milk"))
        self.assertLess(content.index("Buy milk"), content.index("Done"))
        self.assertContains(response, "No cards yet.", count=2)

    def test_the_adder_is_recorded_as_creator(self):
        self.add(self.to_do, "Buy milk")

        self.assertEqual(Card.objects.get().creator, self.ada)

    def test_a_card_needs_a_title(self):
        self.add(self.to_do, "")

        self.assertFalse(Card.objects.exists())

    def test_a_new_card_goes_to_the_end_of_its_stage(self):
        for title in ["First", "Second", "Third"]:
            self.add(self.to_do, title)

        self.assertEqual(
            [c.title for c in self.to_do.cards.all()], ["First", "Second", "Third"]
        )
        self.assertEqual([c.position for c in self.to_do.cards.all()], [0, 1, 2])

    def test_card_order_is_counted_per_stage(self):
        self.add(self.to_do, "First")
        self.add(self.in_progress, "Elsewhere")

        self.assertEqual(Card.objects.get(title="Elsewhere").position, 0)

    def test_the_board_shows_cards_in_card_order_not_creation_order(self):
        older = a_card(self.to_do, "Older")
        newer = a_card(self.to_do, "Newer")
        Card.objects.filter(pk=older.pk).update(position=5)
        Card.objects.filter(pk=newer.pk).update(position=1)

        response = self.client.get(reverse("board_detail", args=[self.board.pk]))

        content = response.content.decode()
        self.assertLess(content.index("Newer"), content.index("Older"))


class EditingACardTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.stage = self.board.stages.first()
        self.card = a_card(self.stage, "Buy milk", description="Semi-skimmed")
        self.url = reverse("card_detail", args=[self.board.pk, self.card.pk])
        self.client.force_login(self.ada)

    def test_opening_a_card_shows_its_detail(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Buy milk")
        self.assertContains(response, "Semi-skimmed")

    def test_the_board_links_to_each_card(self):
        response = self.client.get(reverse("board_detail", args=[self.board.pk]))

        self.assertContains(response, f'href="{self.url}"')

    def test_title_and_description_can_be_changed(self):
        self.client.post(self.url, {"title": "Buy oat milk", "description": "Barista"})

        self.card.refresh_from_db()
        self.assertEqual(self.card.title, "Buy oat milk")
        self.assertEqual(self.card.description, "Barista")

    def test_the_description_may_be_cleared(self):
        self.client.post(self.url, {"title": "Buy milk", "description": ""})

        self.card.refresh_from_db()
        self.assertEqual(self.card.description, "")

    def test_the_title_cannot_be_cleared(self):
        response = self.client.post(self.url, {"title": "", "description": "x"})

        self.assertEqual(response.status_code, 200)
        self.card.refresh_from_db()
        self.assertEqual(self.card.title, "Buy milk")

    def test_editing_leaves_stage_order_and_creator_alone(self):
        grace = a_user("grace@example.com")
        Membership.objects.create(board=self.board, user=grace)
        self.client.force_login(grace)

        self.client.post(self.url, {"title": "Buy oat milk", "description": ""})

        self.card.refresh_from_db()
        self.assertEqual(self.card.creator, self.ada)
        self.assertEqual(self.card.stage, self.stage)
        self.assertEqual(self.card.position, 0)

    def test_a_rejected_edit_does_not_show_its_description_as_saved(self):
        response = self.client.post(self.url, {"title": "", "description": "Unsaved"})

        self.assertContains(response, "<p>Semi-skimmed</p>", html=True)
        self.assertNotContains(response, "<p>Unsaved</p>", html=True)

    def test_the_last_change_is_recorded(self):
        Card.objects.filter(pk=self.card.pk).update(
            updated_at=timezone.now() - timedelta(days=1)
        )
        self.card.refresh_from_db()
        before = self.card.updated_at

        self.client.post(self.url, {"title": "Buy oat milk", "description": ""})

        self.card.refresh_from_db()
        self.assertGreater(self.card.updated_at, before)


class CreatorTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.card = a_card(self.board.stages.first())
        self.client.force_login(self.ada)

    def test_the_card_displays_its_creator_and_when_it_was_created(self):
        created = timezone.localtime(timezone.now()).replace(
            year=2026, month=3, day=14, hour=9, minute=26
        )
        Card.objects.filter(pk=self.card.pk).update(created_at=created)

        response = self.client.get(
            reverse("card_detail", args=[self.board.pk, self.card.pk])
        )

        self.assertContains(response, "Created by ada")
        self.assertContains(response, "14 March 2026")

    def test_a_creator_who_left_the_board_is_still_named(self):
        grace = a_user("grace@example.com")
        Membership.objects.create(board=self.board, user=grace)
        card = a_card(self.board.stages.first(), creator=grace)
        Membership.objects.filter(user=grace).delete()

        response = self.client.get(reverse("card_detail", args=[self.board.pk, card.pk]))

        self.assertContains(response, "Created by grace")


class MarkdownDescriptionTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.stage = self.board.stages.first()
        self.client.force_login(self.ada)

    def view(self, description):
        card = a_card(self.stage, description=description)
        return self.client.get(reverse("card_detail", args=[self.board.pk, card.pk]))

    def test_markdown_is_rendered(self):
        response = self.view("Some **bold** and a [link](https://example.com)")

        self.assertContains(response, "<strong>bold</strong>", html=True)
        self.assertContains(response, '<a href="https://example.com">link</a>', html=True)

    def test_an_embedded_script_does_not_execute(self):
        """The browser only runs a script that reaches it as a <script> element.
        Asserting the tag is absent from the page and present only escaped is
        the proof: the escaped text is what the browser shows, not runs."""
        response = self.view("Hello <script>alert('pwned')</script>")

        content = response.content.decode()
        self.assertNotIn("<script>alert", content)
        self.assertIn("&lt;script&gt;alert(&#x27;pwned&#x27;)&lt;/script&gt;", content)

    def test_raw_html_is_shown_as_text_not_markup(self):
        response = self.view('<img src=x onerror="alert(1)"> <b>bold</b>')

        content = response.content.decode()
        self.assertNotIn("<img", content)
        self.assertNotIn("<b>", content)
        self.assertIn("&lt;b&gt;", content)

    def test_a_javascript_link_is_not_made_clickable(self):
        response = self.view("[click me](javascript:alert(1))")

        self.assertContains(response, "click me")
        self.assertNotContains(response, 'href="javascript:')


class CardAccessTests(TestCase):
    """Cards are reached only through a board scoped to the current user."""

    def setUp(self):
        self.ada = a_user("ada@example.com")
        self.grace = a_user("grace@example.com")
        self.adas_board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.graces_board = Board.objects.create_with_owner(
            name="Secret Plans", owner=self.grace
        )
        self.graces_stage = self.graces_board.stages.first()
        self.graces_card = a_card(self.graces_stage, "Hidden card")
        self.client.force_login(self.ada)

    def test_a_non_member_cannot_view_a_card_by_guessing_ids(self):
        response = self.client.get(
            reverse("card_detail", args=[self.graces_board.pk, self.graces_card.pk])
        )

        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, "Hidden card", status_code=404)

    def test_nor_through_a_board_they_do_belong_to(self):
        response = self.client.get(
            reverse("card_detail", args=[self.adas_board.pk, self.graces_card.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_a_non_member_cannot_edit_a_card(self):
        for board in [self.graces_board, self.adas_board]:
            response = self.client.post(
                reverse("card_detail", args=[board.pk, self.graces_card.pk]),
                {"title": "Defaced", "description": ""},
            )
            self.assertEqual(response.status_code, 404)

        self.graces_card.refresh_from_db()
        self.assertEqual(self.graces_card.title, "Hidden card")

    def test_a_non_member_cannot_add_a_card_to_a_stage(self):
        for board in [self.graces_board, self.adas_board]:
            response = self.client.post(
                reverse("card_create", args=[board.pk, self.graces_stage.pk]),
                {"title": "Planted"},
            )
            self.assertEqual(response.status_code, 404)

        self.assertFalse(Card.objects.filter(title="Planted").exists())

    def test_an_anonymous_visitor_is_sent_to_sign_in(self):
        self.client.logout()

        response = self.client.get(
            reverse("card_detail", args=[self.graces_board.pk, self.graces_card.pk])
        )

        self.assertEqual(response.status_code, 302)
