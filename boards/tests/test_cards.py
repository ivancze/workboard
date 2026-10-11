import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
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
        self.edit_url = reverse("card_edit", args=[self.board.pk, self.card.pk])
        self.client.force_login(self.ada)

    def test_opening_a_card_shows_its_detail(self):
        response = self.client.get(self.url)

        self.assertContains(response, "Buy milk")
        self.assertContains(response, "Semi-skimmed")

    def test_the_board_links_to_each_card(self):
        response = self.client.get(reverse("board_detail", args=[self.board.pk]))

        self.assertContains(response, f'href="{self.url}"')

    def test_title_and_description_can_be_changed(self):
        self.client.post(self.edit_url, {"title": "Buy oat milk", "description": "Barista"})

        self.card.refresh_from_db()
        self.assertEqual(self.card.title, "Buy oat milk")
        self.assertEqual(self.card.description, "Barista")

    def test_the_description_may_be_cleared(self):
        self.client.post(self.edit_url, {"title": "Buy milk", "description": ""})

        self.card.refresh_from_db()
        self.assertEqual(self.card.description, "")

    def test_the_title_cannot_be_cleared(self):
        response = self.client.post(self.edit_url, {"title": "", "description": "x"})

        self.assertEqual(response.status_code, 200)
        self.card.refresh_from_db()
        self.assertEqual(self.card.title, "Buy milk")

    def test_editing_leaves_stage_order_and_creator_alone(self):
        grace = a_user("grace@example.com")
        Membership.objects.create(board=self.board, user=grace)
        self.client.force_login(grace)

        self.client.post(self.edit_url, {"title": "Buy oat milk", "description": ""})

        self.card.refresh_from_db()
        self.assertEqual(self.card.creator, self.ada)
        self.assertEqual(self.card.stage, self.stage)
        self.assertEqual(self.card.position, 0)

    def test_a_rejected_edit_stays_on_the_edit_page_with_what_was_typed(self):
        response = self.client.post(self.edit_url, {"title": "", "description": "Unsaved"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertContains(response, "Unsaved</textarea>")

    def test_a_rejected_edit_names_the_card_by_its_saved_title(self):
        # A valid title is written onto the form's instance even when another
        # field fails, so this is the case that would leak into the heading.
        response = self.client.post(self.edit_url, {"title": "Buy oat milk", "effort": "-1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "← Buy milk")
        self.assertNotContains(response, "← Buy oat milk")

    def test_a_rejected_edit_leaves_the_card_page_as_saved(self):
        self.client.post(self.edit_url, {"title": "", "description": "Unsaved"})

        response = self.client.get(self.url)
        self.assertContains(response, "<p>Semi-skimmed</p>", html=True)
        self.assertNotContains(response, "Unsaved")

    def test_the_card_page_is_read_only_with_an_edit_button(self):
        response = self.client.get(self.url)

        self.assertNotContains(response, 'name="title"')
        self.assertContains(response, f'href="{self.edit_url}"')

    def test_saving_returns_to_the_card_page(self):
        response = self.client.post(self.edit_url, {"title": "Buy oat milk"})

        self.assertRedirects(response, self.url)

    def test_cancel_returns_to_the_card_page(self):
        response = self.client.get(self.edit_url)

        self.assertContains(response, f'<a href="{self.url}"', count=2)  # back link and Cancel
        self.assertContains(response, ">Cancel</a>")

    def test_posting_to_the_card_page_is_refused(self):
        response = self.client.post(self.url, {"title": "Ignored", "description": ""})

        self.assertEqual(response.status_code, 405)
        self.card.refresh_from_db()
        self.assertEqual(self.card.title, "Buy milk")

    def test_the_last_change_is_recorded(self):
        Card.objects.filter(pk=self.card.pk).update(
            updated_at=timezone.now() - timedelta(days=1)
        )
        self.card.refresh_from_db()
        before = self.card.updated_at

        self.client.post(self.edit_url, {"title": "Buy oat milk", "description": ""})

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
        self.assertIn("<p>Hello &lt;script&gt;alert('pwned')&lt;/script&gt;</p>", content)

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
            url = reverse("card_edit", args=[board.pk, self.graces_card.pk])
            self.assertEqual(self.client.get(url).status_code, 404)
            response = self.client.post(url, {"title": "Defaced", "description": ""})
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


class AssigneeTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        Membership.objects.create(board=self.board, user=self.grace)
        self.card = a_card(self.board.stages.first())
        self.url = reverse("card_detail", args=[self.board.pk, self.card.pk])
        self.edit_url = reverse("card_edit", args=[self.board.pk, self.card.pk])
        self.board_url = reverse("board_detail", args=[self.board.pk])
        self.client.force_login(self.ada)

    def edit(self, **fields):
        return self.client.post(self.edit_url, {"title": "Buy milk", **fields})

    def test_a_member_can_be_assigned_and_is_shown(self):
        self.edit(assignee=self.grace.pk)

        self.card.refresh_from_db()
        self.assertEqual(self.card.assignee, self.grace)
        self.assertContains(self.client.get(self.board_url), "grace")
        self.assertContains(self.client.get(self.url), "grace")

    def test_a_card_starts_unassigned_and_says_so(self):
        self.assertIsNone(self.card.assignee)
        self.assertContains(self.client.get(self.board_url), "Unassigned")
        self.assertContains(self.client.get(self.url), "Unassigned")

    def test_the_assignee_can_be_removed(self):
        Card.objects.filter(pk=self.card.pk).update(assignee=self.grace)

        self.edit(assignee="")

        self.card.refresh_from_db()
        self.assertIsNone(self.card.assignee)

    def test_only_members_are_offered(self):
        a_user("mallory@example.com")

        response = self.client.get(self.edit_url)

        self.assertContains(response, f'<option value="{self.grace.pk}">grace</option>', html=True)
        self.assertNotContains(response, "mallory")

    def test_a_non_member_is_refused(self):
        mallory = a_user("mallory@example.com")

        response = self.edit(assignee=mallory.pk)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice")
        self.card.refresh_from_db()
        self.assertIsNone(self.card.assignee)


class ContactPersonTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.card = a_card(self.board.stages.first())
        self.url = reverse("card_detail", args=[self.board.pk, self.card.pk])
        self.edit_url = reverse("card_edit", args=[self.board.pk, self.card.pk])
        self.client.force_login(self.ada)

    def test_contact_persons_are_recorded_as_typed_and_shown(self):
        self.client.post(
            self.edit_url, {"title": "Buy milk", "contact_persons": "Dave, Priya from Acme"}
        )

        self.card.refresh_from_db()
        self.assertEqual(self.card.contact_persons, "Dave, Priya from Acme")
        self.assertContains(self.client.get(self.url), "Dave, Priya from Acme")

    def test_naming_a_user_does_not_link_or_admit_them(self):
        grace = a_user("grace@example.com")

        self.client.post(self.edit_url, {"title": "Buy milk", "contact_persons": "grace"})

        self.card.refresh_from_db()
        self.assertIsNone(self.card.assignee)
        self.assertFalse(Board.objects.for_user(grace).exists())


class DueDateTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.stage = self.board.stages.first()
        self.card = a_card(self.stage)
        self.url = reverse("card_detail", args=[self.board.pk, self.card.pk])
        self.edit_url = reverse("card_edit", args=[self.board.pk, self.card.pk])
        self.board_url = reverse("board_detail", args=[self.board.pk])
        self.client.force_login(self.ada)

    def test_a_due_date_is_saved_as_a_plain_date(self):
        self.client.post(self.edit_url, {"title": "Buy milk", "due_date": "2026-10-14"})

        self.card.refresh_from_db()
        self.assertEqual(self.card.due_date, date(2026, 10, 14))
        self.assertContains(self.client.get(self.edit_url), 'value="2026-10-14"')

    def test_the_date_shown_is_the_date_entered_in_any_timezone(self):
        Card.objects.filter(pk=self.card.pk).update(due_date=date(2026, 10, 14))

        # Twenty-six hours apart: a date that shifted with the timezone would
        # show as the 13th or the 15th in one of them.
        for tz in ["Pacific/Pago_Pago", "Pacific/Kiritimati"]:
            with self.subTest(tz=tz), override_settings(TIME_ZONE=tz):
                self.assertContains(self.client.get(self.url), "14 October 2026")
                self.assertContains(self.client.get(self.board_url), "Due 14 Oct 2026")

    def test_a_card_past_its_due_date_is_emphasised(self):
        a_card(self.stage, "Late one", due_date=timezone.localdate() - timedelta(days=1))

        response = self.client.get(self.board_url)

        self.assertContains(response, "Overdue", count=1)
        self.assertContains(response, "border-danger", count=1)

    def test_a_card_due_today_is_not_yet_overdue(self):
        a_card(self.stage, "Today", due_date=timezone.localdate())

        self.assertNotContains(self.client.get(self.board_url), "Overdue")

    def test_a_card_without_a_due_date_is_never_overdue(self):
        self.assertIsNone(self.card.due_date)
        self.assertNotContains(self.client.get(self.board_url), "Overdue")
        self.assertNotContains(self.client.get(self.url), "Overdue")

    @override_settings(TIME_ZONE="Asia/Kuala_Lumpur")
    def test_overdue_is_judged_by_the_teams_date_not_utc(self):
        # 01:00 on the 14th in Kuala Lumpur is still the 13th in UTC.
        just_after_midnight = datetime(2026, 10, 13, 17, 0, tzinfo=timezone.UTC)
        Card.objects.filter(pk=self.card.pk).update(due_date=date(2026, 10, 13))

        with mock.patch("django.utils.timezone.now", return_value=just_after_midnight):
            self.assertContains(self.client.get(self.board_url), "Overdue")


class DueDateIsAdvisoryTests(TestCase):
    """Nothing sorts, filters, blocks or notifies on a Due date."""

    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.stage = self.board.stages.first()
        self.client.force_login(self.ada)

    def test_card_order_ignores_due_dates(self):
        today = timezone.localdate()
        a_card(self.stage, "Due later", due_date=today + timedelta(days=9))
        a_card(self.stage, "Long overdue", due_date=today - timedelta(days=9))
        a_card(self.stage, "Due soon", due_date=today + timedelta(days=1))

        content = self.client.get(
            reverse("board_detail", args=[self.board.pk])
        ).content.decode()

        self.assertLess(content.index("Due later"), content.index("Long overdue"))
        self.assertLess(content.index("Long overdue"), content.index("Due soon"))

    def test_a_past_due_date_is_accepted_and_sends_nothing(self):
        card = a_card(self.stage)

        response = self.client.post(
            reverse("card_edit", args=[self.board.pk, card.pk]),
            {"title": "Buy milk", "due_date": "2020-01-01"},
        )

        self.assertEqual(response.status_code, 302)
        card.refresh_from_db()
        self.assertEqual(card.due_date, date(2020, 1, 1))
        self.assertEqual(mail.outbox, [])


class EffortTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.card = a_card(self.board.stages.first())
        self.url = reverse("card_detail", args=[self.board.pk, self.card.pk])
        self.edit_url = reverse("card_edit", args=[self.board.pk, self.card.pk])
        self.client.force_login(self.ada)

    def edit(self, effort):
        return self.client.post(self.edit_url, {"title": "Buy milk", "effort": effort})

    def test_effort_is_saved_in_steps_of_a_half_with_no_small_ceiling(self):
        for typed, saved in [("2.5", Decimal("2.5")), ("0", Decimal("0")), ("100000", Decimal("100000"))]:
            with self.subTest(typed=typed):
                self.edit(typed)
                self.card.refresh_from_db()
                self.assertEqual(self.card.effort, saved)

    def test_the_field_has_stepper_arrows(self):
        response = self.client.get(self.edit_url)

        self.assertContains(response, 'type="number" name="effort"')
        self.assertContains(response, 'step="0.5"')

    def test_values_off_the_half_step_are_rejected(self):
        for typed in ["0.3", "1.25"]:
            with self.subTest(typed=typed):
                response = self.edit(typed)
                self.assertEqual(response.status_code, 200)
                self.card.refresh_from_db()
                self.assertIsNone(self.card.effort)

    def test_negative_effort_is_rejected(self):
        response = self.edit("-1")

        self.assertContains(response, "greater than or equal to 0")
        self.card.refresh_from_db()
        self.assertIsNone(self.card.effort)

    def test_unestimated_and_zero_are_saved_and_shown_differently(self):
        self.edit("")
        self.card.refresh_from_db()
        self.assertIsNone(self.card.effort)
        shown = '<span class="font-normal text-text-muted">Unestimated</span>'
        self.assertContains(self.client.get(self.url), shown, html=True)
        tile = self.client.get(reverse("board_detail", args=[self.board.pk]))
        self.assertNotContains(tile, '<span class="sr-only">Effort</span>')

        self.edit("0")
        self.card.refresh_from_db()
        self.assertEqual(self.card.effort, Decimal("0"))
        self.assertNotContains(self.client.get(self.url), shown, html=True)
        tile = self.client.get(reverse("board_detail", args=[self.board.pk]))
        self.assertContains(tile, '⚡</span> <span class="sr-only">Effort</span>0</span>')


class EffortTotalTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.to_do, self.in_progress, self.done = self.board.stages.all()
        self.url = reverse("board_detail", args=[self.board.pk])
        self.client.force_login(self.ada)

    def totals(self, response):
        """Each "Effort N · M unestimated" line on the page, board first."""
        content = response.content.decode()
        return [
            " ".join(line.split())
            for line in re.findall(r'<p class="text-sm text-text-muted">Effort (.*?)</p>', content, re.S)
        ]

    def test_each_stage_and_the_board_show_their_total_and_unestimated_count(self):
        a_card(self.to_do, "A", effort=Decimal("2.5"))
        a_card(self.to_do, "B", effort=Decimal("1"))
        a_card(self.to_do, "C")
        a_card(self.in_progress, "D", effort=Decimal("0"))
        a_card(self.in_progress, "E")

        lines = self.totals(self.client.get(self.url))

        self.assertEqual(
            [re.sub(r"<[^>]+>", "", line) for line in lines],
            [
                "3.5 · 2 unestimated",  # board
                "3.5 · 1 unestimated",  # To Do
                "0 · 1 unestimated",  # In Progress
                "0 · 0 unestimated",  # Done, empty
            ],
        )

    def test_a_total_of_only_unestimated_cards_still_reports_them(self):
        a_card(self.done, "Mystery")

        lines = self.totals(self.client.get(self.url))

        self.assertEqual(re.sub(r"<[^>]+>", "", lines[3]), "0 · 1 unestimated")

    def test_totals_are_summed_by_the_database(self):
        for i in range(10):
            a_card(self.to_do, f"Card {i}", effort=Decimal("1"))

        with CaptureQueriesContext(connection) as captured:
            self.client.get(self.url)

        sums = [q["sql"] for q in captured if "SUM(" in q["sql"]]
        self.assertEqual(len(sums), 2, "one query for the Stages, one for the board")

    def test_the_board_costs_the_same_queries_however_many_cards_it_has(self):
        a_card(self.to_do, "Only")
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.url)

        for i in range(20):
            a_card(self.in_progress, f"Card {i}", effort=Decimal("1"))
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.url)

        self.assertEqual(len(few), len(many))

    def test_totals_only_count_this_boards_cards(self):
        other = Board.objects.create_with_owner(name="Elsewhere", owner=self.ada)
        a_card(other.stages.first(), "Not here", effort=Decimal("9"))
        a_card(other.stages.first(), "Nor here")

        lines = self.totals(self.client.get(self.url))

        self.assertEqual(re.sub(r"<[^>]+>", "", lines[0]), "0 · 0 unestimated")
