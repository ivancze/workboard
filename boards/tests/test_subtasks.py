import re

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from boards.models import Board, Card, Membership, Subtask

from .test_cards import a_card, a_user


def subtasks_of(card):
    return list(card.subtasks.values_list("text", "done"))


class SubtaskTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        Membership.objects.create(board=self.board, user=self.grace)
        self.card = a_card(self.board.stages.first())
        self.card_url = reverse("card_detail", args=[self.board.pk, self.card.pk])
        # Not the Owner: Subtasks are open to every Member, like editing.
        self.client.force_login(self.grace)

    def url(self, name, subtask=None):
        args = [self.board.pk, self.card.pk] + ([subtask.pk] if subtask else [])
        return reverse(name, args=args)

    def add(self, text, **headers):
        return self.client.post(self.url("subtask_add"), {"text": text}, headers=headers)

    def a_subtask(self, text="Milk", done=False, card=None):
        card = card or self.card
        return Subtask.objects.create(
            card=card, text=text, done=done, position=card.subtasks.count()
        )

    def section(self, content=None):
        content = content or self.client.get(self.card_url).content.decode()
        return re.search(r'<section id="subtasks".*?</section>', content, re.S).group()


class OnTheCardPageTests(SubtaskTests):
    def test_a_card_has_none_until_one_is_added(self):
        section = self.section()

        self.assertIn("No Subtasks yet.", section)
        self.assertIn(f'action="{self.url("subtask_add")}"', section)
        self.assertNotIn("<progress", section)

    def test_any_member_adds_one_and_it_goes_to_the_bottom(self):
        self.a_subtask("Milk")
        self.a_subtask("Eggs")

        response = self.add("  Bread  ")

        self.assertRedirects(response, self.card_url)
        self.assertEqual(subtasks_of(self.card), [("Milk", False), ("Eggs", False), ("Bread", False)])
        section = self.section()
        self.assertLess(section.index("Eggs"), section.index("Bread"))

    def test_the_bottom_is_past_any_gap_left_by_deletes(self):
        milk, *middle, jam = [self.a_subtask(t) for t in ["Milk", "Eggs", "Bread", "Jam"]]
        Subtask.objects.filter(pk__in=[s.pk for s in middle]).delete()

        self.add("Tea")

        self.assertEqual([t for t, _ in subtasks_of(self.card)], ["Milk", "Jam", "Tea"])

    def test_an_empty_one_is_refused(self):
        response = self.add("   ")

        self.assertEqual(response.status_code, 400)
        self.assertIn("This field is required.", self.section(response.content.decode()))
        self.assertEqual(subtasks_of(self.card), [])

    def test_one_longer_than_a_title_is_refused(self):
        response = self.add("x" * 201)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(subtasks_of(self.card), [])

    def test_fifty_is_the_most_a_card_holds(self):
        for n in range(50):
            self.a_subtask(f"Step {n}")

        response = self.add("One more")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "A Card holds at most 50 Subtasks.", status_code=400)
        self.assertEqual(self.card.subtasks.count(), 50)

    def test_ticking_one_marks_it_done_and_unticking_undoes_it(self):
        milk = self.a_subtask("Milk")

        self.client.post(self.url("subtask_tick", milk), {"done": "on"})
        self.assertEqual(subtasks_of(self.card), [("Milk", True)])

        response = self.client.post(self.url("subtask_tick", milk), {"done": ""})
        self.assertRedirects(response, self.card_url)
        self.assertEqual(subtasks_of(self.card), [("Milk", False)])

    def test_a_tick_sets_the_state_asked_for_rather_than_flipping_it(self):
        """Two people ticking from the same stale page both mean done. A
        toggle would undo the first."""
        milk = self.a_subtask("Milk")

        self.client.post(self.url("subtask_tick", milk), {"done": "on"})
        self.client.post(self.url("subtask_tick", milk), {"done": "on"})

        self.assertEqual(subtasks_of(self.card), [("Milk", True)])

    def test_each_box_offers_the_opposite_of_its_state(self):
        self.a_subtask("Milk")
        self.a_subtask("Eggs", done=True)

        section = self.section()

        self.assertRegex(section, r'<button[^>]*name="done" value="on"[^>]*role="checkbox" aria-checked="false" aria-label="Milk"')
        self.assertRegex(section, r'<button[^>]*name="done" value=""[^>]*role="checkbox" aria-checked="true" aria-label="Eggs"')

    def test_the_page_shows_how_many_are_done(self):
        self.a_subtask("Milk", done=True)
        self.a_subtask("Eggs")
        self.a_subtask("Bread")

        section = self.section()

        self.assertRegex(section, r'<progress[^>]*value="1" max="3"')
        self.assertIn("1 of 3", section)

    def test_deleting_one_takes_it_off_the_list(self):
        milk = self.a_subtask("Milk")
        self.a_subtask("Eggs")

        response = self.client.post(self.url("subtask_delete", milk))

        self.assertRedirects(response, self.card_url)
        self.assertEqual(subtasks_of(self.card), [("Eggs", False)])

    def test_with_htmx_each_answers_with_the_section(self):
        milk = self.a_subtask("Milk")
        htmx = {"HX-Request": "true"}

        for response in [
            self.add("Eggs", **htmx),
            self.client.post(self.url("subtask_tick", milk), {"done": "on"}, headers=htmx),
            self.client.post(self.url("subtask_delete", milk), headers=htmx),
        ]:
            with self.subTest(response.request["PATH_INFO"]):
                content = response.content.decode()
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("<html", content)
                self.assertRegex(content, r'^\s*<section id="subtasks"')
        self.assertEqual(subtasks_of(self.card), [("Eggs", False)])

    def test_with_htmx_a_refusal_comes_back_in_the_section(self):
        response = self.add("", **{"HX-Request": "true"})

        self.assertEqual(response.status_code, 400)
        self.assertRegex(response.content.decode(), r'^\s*<section id="subtasks"')
        self.assertContains(response, "This field is required.", status_code=400)

    def test_it_returns_to_the_card_keeping_the_filter(self):
        response = self.client.post(self.url("subtask_add") + "?assignee=me", {"text": "Milk"})

        self.assertRedirects(response, self.card_url + "?assignee=me", fetch_redirect_response=False)

    def test_an_archived_card_still_takes_them(self):
        """An archived Card stays fully editable."""
        self.card.archive()

        self.add("Milk")

        self.assertEqual(subtasks_of(self.card), [("Milk", False)])

    def test_deleting_the_card_takes_its_subtasks_with_it(self):
        self.a_subtask("Milk")

        self.client.post(reverse("card_delete", args=[self.board.pk, self.card.pk]))

        self.assertFalse(Card.objects.filter(pk=self.card.pk).exists())
        self.assertFalse(Subtask.objects.exists())

    def test_text_is_shown_as_text(self):
        self.a_subtask("<b>Milk</b>")

        self.assertIn("&lt;b&gt;Milk&lt;/b&gt;", self.section())


class RenamingAndReorderingTests(SubtaskTests):
    def rename(self, subtask, text, **headers):
        return self.client.post(self.url("subtask_rename", subtask), {"text": text}, headers=headers)

    def shift(self, subtask, direction):
        return self.client.post(self.url("subtask_shift", subtask), {"direction": direction})

    def test_each_one_is_edited_where_it_is(self):
        milk = self.a_subtask("Milk")

        section = self.section()

        self.assertRegex(
            section,
            rf'(?s)<form[^>]*action="{self.url("subtask_rename", milk)}"[^>]*>.*?'
            r'<input[^>]*name="text" value="Milk"',
        )

    def test_renaming_one_keeps_its_tick_and_its_place(self):
        milk = self.a_subtask("Milk", done=True)
        self.a_subtask("Eggs")

        response = self.rename(milk, " Oat milk ")

        self.assertRedirects(response, self.card_url)
        self.assertEqual(subtasks_of(self.card), [("Oat milk", True), ("Eggs", False)])

    def test_an_empty_or_overlong_name_is_refused_and_shown_on_its_row(self):
        milk = self.a_subtask("Milk")

        for text in ["  ", "x" * 201]:
            with self.subTest(text=text[:5]):
                response = self.rename(milk, text, **{"HX-Request": "true"})

                self.assertEqual(response.status_code, 400)
                row = re.search(rf'<li id="subtask-{milk.pk}".*?</li>', response.content.decode(), re.S).group()
                self.assertIn('aria-invalid="true"', row)
        self.assertEqual(subtasks_of(self.card), [("Milk", False)])

    def test_without_htmx_a_refused_name_comes_back_on_the_page(self):
        milk = self.a_subtask("Milk")

        response = self.rename(milk, "")

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "This field is required.", status_code=400)

    def test_up_and_down_swap_it_with_its_neighbour(self):
        milk, eggs, bread = self.a_subtask("Milk"), self.a_subtask("Eggs"), self.a_subtask("Bread")

        response = self.shift(bread, "up")
        self.assertRedirects(response, self.card_url)
        self.assertEqual([t for t, _ in subtasks_of(self.card)], ["Milk", "Bread", "Eggs"])

        self.shift(milk, "down")
        self.assertEqual([t for t, _ in subtasks_of(self.card)], ["Bread", "Milk", "Eggs"])

    def test_at_either_end_it_stays_put(self):
        milk, eggs = self.a_subtask("Milk"), self.a_subtask("Eggs")

        self.shift(milk, "up")
        self.shift(eggs, "down")

        self.assertEqual([t for t, _ in subtasks_of(self.card)], ["Milk", "Eggs"])

    def test_a_gap_left_by_a_delete_doesnt_make_a_shift_skip(self):
        milk, eggs, bread = self.a_subtask("Milk"), self.a_subtask("Eggs"), self.a_subtask("Bread")
        eggs.delete()

        self.shift(bread, "up")

        self.assertEqual([t for t, _ in subtasks_of(self.card)], ["Bread", "Milk"])
        self.assertEqual(list(self.card.subtasks.values_list("position", flat=True)), [0, 1])

    def test_an_unknown_direction_is_refused(self):
        milk = self.a_subtask("Milk")

        self.assertEqual(self.shift(milk, "sideways").status_code, 400)

    def test_the_first_has_no_up_and_the_last_no_down(self):
        milk, eggs = self.a_subtask("Milk"), self.a_subtask("Eggs")

        section = self.section()

        self.assertNotIn('aria-label="Move Milk up"', section)
        self.assertIn('aria-label="Move Milk down"', section)
        self.assertIn('aria-label="Move Eggs up"', section)
        self.assertNotIn('aria-label="Move Eggs down"', section)


class OnTheTileTests(SubtaskTests):
    """The board shows how far along each Card's Subtasks are, as a bar."""

    def setUp(self):
        super().setUp()
        self.board_url = reverse("board_detail", args=[self.board.pk])

    def tile(self, card):
        content = self.client.get(self.board_url).content.decode()
        return re.search(rf'<li data-card-id="{card.pk}".*?</li>', content, re.S).group()

    def test_a_card_with_subtasks_shows_a_bar(self):
        self.a_subtask("Milk", done=True)
        self.a_subtask("Eggs")
        self.a_subtask("Bread", done=True)

        self.assertRegex(
            self.tile(self.card),
            r'<progress value="2" max="3" aria-label="Subtasks: 2 of 3 done" class="subtask-progress',
        )

    def test_a_card_without_any_shows_none(self):
        self.assertNotIn("<progress", self.tile(self.card))

    def test_the_bar_costs_the_board_no_query_per_card(self):
        self.client.get(self.board_url)
        with CaptureQueriesContext(connection) as few:
            self.client.get(self.board_url)

        for n in range(5):
            card = a_card(self.board.stages.first(), f"Card {n}")
            self.a_subtask("Step", card=card)
        with CaptureQueriesContext(connection) as many:
            self.client.get(self.board_url)

        self.assertEqual(len(few), len(many))


def rows(*rows, initial=0):
    """The Subtask rows of a New card or Edit form, as the browser posts them."""
    data = {
        "subtasks-TOTAL_FORMS": str(len(rows)),
        "subtasks-INITIAL_FORMS": str(initial),
        "subtasks-MIN_NUM_FORMS": "0",
        "subtasks-MAX_NUM_FORMS": "50",
    }
    for i, row in enumerate(rows):
        for field, value in row.items():
            data[f"subtasks-{i}-{field}"] = value
    return data


CARD = {"title": "Buy milk", "description": "", "priority": "", "assignee": "",
        "contact_persons": "", "due_date": "", "effort": ""}


class OnNewCardTests(SubtaskTests):
    def setUp(self):
        super().setUp()
        self.new_url = reverse("card_create", args=[self.board.pk])

    def test_the_form_offers_one_blank_row(self):
        response = self.client.get(self.new_url)

        self.assertContains(response, 'name="subtasks-TOTAL_FORMS" value="1"')
        self.assertContains(response, 'name="subtasks-0-text"')
        # More rows come from the empty form, added by subtasks.js.
        self.assertContains(response, 'name="subtasks-__prefix__-text"')

    def test_a_new_card_keeps_its_subtasks_in_order_and_skips_blank_rows(self):
        self.client.post(self.new_url, {
            **CARD, "title": "Shopping",
            **rows({"text": "Milk"}, {"text": ""}, {"text": "Eggs"}),
        })

        card = Card.objects.get(title="Shopping")
        self.assertEqual(subtasks_of(card), [("Milk", False), ("Eggs", False)])

    def test_a_removed_row_is_left_out(self):
        self.client.post(self.new_url, {
            **CARD, "title": "Shopping",
            **rows({"text": "Milk"}, {"text": "Eggs", "DELETE": "on"}),
        })

        self.assertEqual(subtasks_of(Card.objects.get(title="Shopping")), [("Milk", False)])

    def test_a_refused_subtask_refuses_the_card(self):
        response = self.client.post(self.new_url, {
            **CARD, "title": "Shopping", **rows({"text": "x" * 201}),
        })

        self.assertContains(response, "Ensure this value has at most 200 characters")
        self.assertFalse(Card.objects.filter(title="Shopping").exists())

    def test_no_more_than_fifty(self):
        response = self.client.post(self.new_url, {
            **CARD, "title": "Shopping", **rows(*({"text": f"Step {n}"} for n in range(51))),
        })

        self.assertContains(response, "A Card holds at most 50 Subtasks.")
        self.assertFalse(Card.objects.filter(title="Shopping").exists())


class OnEditTests(SubtaskTests):
    def setUp(self):
        super().setUp()
        self.edit_url = reverse("card_edit", args=[self.board.pk, self.card.pk])

    def edit(self, *subtask_rows, initial, **card):
        return self.client.post(self.edit_url, {**CARD, **card, **rows(*subtask_rows, initial=initial)})

    def test_each_subtask_is_a_row_with_a_blank_one_after(self):
        milk = self.a_subtask("Milk", done=True)

        response = self.client.get(self.edit_url)

        self.assertContains(response, 'name="subtasks-INITIAL_FORMS" value="1"')
        self.assertContains(response, f'name="subtasks-0-id" value="{milk.pk}"')
        self.assertRegex(response.content.decode(), r'name="subtasks-0-text" value="Milk"')
        self.assertContains(response, 'name="subtasks-1-text"')

    def test_renaming_removing_and_adding_rows(self):
        milk, eggs = self.a_subtask("Milk", done=True), self.a_subtask("Eggs")

        response = self.edit(
            {"id": milk.pk, "text": "Oat milk"},
            {"id": eggs.pk, "text": "Eggs", "DELETE": "on"},
            {"text": "Bread"},
            initial=2,
        )

        self.assertRedirects(response, self.card_url)
        self.assertEqual(subtasks_of(self.card), [("Oat milk", True), ("Bread", False)])

    def test_a_subtask_added_meanwhile_is_kept(self):
        """The form names only the rows it showed. Saving it touches those."""
        milk = self.a_subtask("Milk")
        self.a_subtask("Eggs")  # added on the Card's page after Edit opened

        self.edit({"id": milk.pk, "text": "Milk"}, initial=1, title="Shopping")

        self.assertEqual(subtasks_of(self.card), [("Milk", False), ("Eggs", False)])

    def test_a_tick_made_since_edit_opened_is_kept_even_on_a_renamed_row(self):
        milk = self.a_subtask("Milk")
        eggs = self.a_subtask("Eggs")
        Subtask.objects.update(done=True)  # ticked on the Card's page after Edit opened

        self.edit({"id": milk.pk, "text": "Milk"}, {"id": eggs.pk, "text": "Free-range eggs"}, initial=2)

        self.assertEqual(subtasks_of(self.card), [("Milk", True), ("Free-range eggs", True)])

    def test_new_rows_go_to_the_bottom_past_any_gap(self):
        """Deletes leave gaps in the positions, so the bottom is past the
        highest one, not at the count."""
        milk, *middle, jam = [self.a_subtask(t) for t in ["Milk", "Eggs", "Bread", "Jam"]]
        Subtask.objects.filter(pk__in=[s.pk for s in middle]).delete()

        self.edit({"id": milk.pk, "text": "Milk"}, {"id": jam.pk, "text": "Jam"}, {"text": "Tea"}, initial=2)

        self.assertEqual([t for t, _ in subtasks_of(self.card)], ["Milk", "Jam", "Tea"])

    def test_a_row_deleted_meanwhile_says_so(self):
        gone = self.a_subtask("Milk").pk
        Subtask.objects.filter(pk=gone).delete()  # on the Card's page after Edit opened

        response = self.edit({"id": gone, "text": "Milk"}, initial=1, title="Shopping")

        self.assertContains(response, "Someone deleted this Subtask while you were editing.")
        self.card.refresh_from_db()
        self.assertEqual(self.card.title, "Buy milk")

    def test_a_row_deleted_meanwhile_and_removed_here_too_is_fine(self):
        gone = self.a_subtask("Milk").pk
        Subtask.objects.filter(pk=gone).delete()

        response = self.edit({"id": gone, "text": "Milk", "DELETE": "on"}, initial=1, title="Shopping")

        self.assertRedirects(response, self.card_url)
        self.card.refresh_from_db()
        self.assertEqual(self.card.title, "Shopping")

    def test_an_edit_page_from_before_subtasks_leaves_them_alone(self):
        """Opened before this was deployed, it posts no rows at all."""
        self.a_subtask("Milk", done=True)

        response = self.client.post(self.edit_url, {**CARD, "title": "Shopping"})

        self.assertRedirects(response, self.card_url)
        self.assertEqual(subtasks_of(self.card), [("Milk", True)])

    def test_fifty_counts_those_added_meanwhile(self):
        for n in range(49):
            self.a_subtask(f"Step {n}")

        response = self.edit({"text": "One"}, {"text": "Two"}, initial=0, title="Shopping")

        self.assertContains(response, "A Card holds at most 50 Subtasks.")
        self.assertEqual(self.card.subtasks.count(), 49)
        self.card.refresh_from_db()
        self.assertEqual(self.card.title, "Buy milk")

    def test_removing_makes_room(self):
        subtasks = [self.a_subtask(f"Step {n}") for n in range(50)]

        response = self.edit(
            *({"id": s.pk, "text": s.text, **({"DELETE": "on"} if s is subtasks[0] else {})} for s in subtasks),
            {"text": "One more"},
            initial=50,
        )

        self.assertRedirects(response, self.card_url)
        self.assertEqual(self.card.subtasks.count(), 50)


class AccessTests(SubtaskTests):
    def test_someone_off_the_board_gets_a_404_and_changes_nothing(self):
        milk = self.a_subtask("Milk")
        self.client.force_login(a_user("mallory@example.com"))

        for url, data in [
            (self.url("subtask_add"), {"text": "Eggs"}),
            (self.url("subtask_tick", milk), {"done": "on"}),
            (self.url("subtask_delete", milk), {}),
            (self.url("subtask_rename", milk), {"text": "Eggs"}),
            (self.url("subtask_shift", milk), {"direction": "down"}),
        ]:
            with self.subTest(url):
                self.assertEqual(self.client.post(url, data).status_code, 404)
        self.assertEqual(subtasks_of(self.card), [("Milk", False)])

    def test_a_subtask_is_reached_only_through_its_own_card(self):
        other = a_card(self.board.stages.first(), "Wash up")
        theirs = self.a_subtask("Plates", card=other)

        response = self.client.post(self.url("subtask_tick", theirs), {"done": "on"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(subtasks_of(other), [("Plates", False)])

    def test_only_a_post_changes_them(self):
        milk = self.a_subtask("Milk")

        self.assertEqual(self.client.get(self.url("subtask_add")).status_code, 405)
        for name in ["subtask_tick", "subtask_delete", "subtask_rename", "subtask_shift"]:
            url = self.url(name, milk)
            with self.subTest(url):
                self.assertEqual(self.client.get(url).status_code, 405)
