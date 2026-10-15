import re
import runpy
import struct
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from boards.models import Board, Card, Membership


def a_user(email="ada@example.com"):
    return User.objects.create_user(email=email, display_name=email.split("@")[0])


class ChoosingAPetTests(TestCase):
    """Any Member picks the board's pet from its ⋯ menu, and everyone on the
    board sees it on the board's page."""

    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        Membership.objects.create(board=self.board, user=self.grace)
        self.url = reverse("board_pet", args=[self.board.pk])
        self.board_url = reverse("board_detail", args=[self.board.pk])
        # Not the Owner: choosing the pet is open to every Member.
        self.client.force_login(self.grace)

    def pet_menu(self, content=None):
        content = content or self.client.get(self.board_url).content.decode()
        return re.search(r'<form[^>]*aria-label="Pet".*?</form>', content, re.S).group()

    def test_a_board_has_no_pet_until_one_is_chosen(self):
        response = self.client.get(self.board_url)

        self.assertEqual(self.board.pet, "")
        self.assertNotContains(response, "data-pet=")

    def test_the_menu_offers_every_pet_and_none(self):
        menu = self.pet_menu()

        self.assertIn(f'action="{self.url}"', menu)
        for value in ["dog", "pug", "duck", "pig", ""]:
            self.assertIn(f'name="pet" value="{value}"', menu)
        self.assertRegex(menu, r'value=""[^>]*aria-current="true"')

    def test_any_member_can_choose_one_and_everyone_sees_it(self):
        response = self.client.post(self.url, {"pet": "duck"})

        self.assertRedirects(response, self.board_url)
        self.board.refresh_from_db()
        self.assertEqual(self.board.pet, "duck")
        self.client.force_login(self.ada)
        page = self.client.get(self.board_url)
        self.assertContains(page, 'data-pet="duck"')
        self.assertContains(page, 'aria-label="Pet the duck"')
        self.assertRegex(self.pet_menu(page.content.decode()), r'value="duck"[^>]*aria-current="true"')

    def test_the_pug_is_a_pet_of_its_own(self):
        self.client.post(self.url, {"pet": "pug"})

        page = self.client.get(self.board_url)
        self.assertContains(page, 'data-pet="pug"')
        self.assertContains(page, 'aria-label="Pet the pug"')

    def test_none_takes_it_away(self):
        Board.objects.filter(pk=self.board.pk).update(pet="pig")

        self.client.post(self.url, {"pet": ""})

        self.board.refresh_from_db()
        self.assertEqual(self.board.pet, "")
        self.assertNotContains(self.client.get(self.board_url), "data-pet=")

    def test_with_htmx_it_answers_with_the_pet_and_the_menu(self):
        """The pet sits outside #board, so a board refresh never resets it,
        and the menu comes along out of band so its tick moves."""
        response = self.client.post(self.url, {"pet": "dog"}, headers={"HX-Request": "true"})

        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<html", content)
        self.assertRegex(content, r'^\s*<div id="pet"')
        self.assertIn('data-pet="dog"', content)
        self.assertRegex(content, r'<details id="board-menu"[^>]*hx-swap-oob="true"')
        self.assertRegex(self.pet_menu(content), r'value="dog"[^>]*aria-current="true"')

    def test_the_pet_is_outside_the_board(self):
        """A drag or a refresh swaps #board, which would put it back to the
        start and wake it."""
        Board.objects.filter(pk=self.board.pk).update(pet="dog")
        card = Card.objects.create_at_end(stage=self.board.stages.first(), title="Buy milk", creator=self.ada)

        swapped = self.client.post(
            reverse("card_priority", args=[self.board.pk, card.pk]),
            {"priority": "must"},
            headers={"HX-Request": "true"},
        )

        self.assertContains(swapped, 'id="board"')
        self.assertNotContains(swapped, "data-pet=")
        self.assertContains(self.client.get(self.board_url), 'data-pet="dog"')

    def test_without_javascript_it_returns_to_the_board_keeping_the_filter(self):
        response = self.client.post(self.url + "?assignee=me", {"pet": "pig"})

        self.assertRedirects(response, self.board_url + "?assignee=me", fetch_redirect_response=False)

    def test_an_unknown_pet_is_refused(self):
        response = self.client.post(self.url, {"pet": "cat"})

        self.assertEqual(response.status_code, 400)
        self.board.refresh_from_db()
        self.assertEqual(self.board.pet, "")

    def test_someone_off_the_board_gets_a_404(self):
        self.client.force_login(a_user("mallory@example.com"))

        response = self.client.post(self.url, {"pet": "dog"})

        self.assertEqual(response.status_code, 404)
        self.board.refresh_from_db()
        self.assertEqual(self.board.pet, "")

    def test_only_a_post_changes_it(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)


BUILDER = Path(settings.BASE_DIR, "bin", "pets")


class SpriteSheetTests(TestCase):
    """The PNGs are built from text grids by bin/pets and committed. Rebuilding
    must give the same bytes, so a grid and its sheet never drift apart."""

    def test_every_pet_has_a_sheet_built_from_its_grid(self):
        built = runpy.run_path(str(BUILDER))["build"]()

        self.assertEqual(set(built), {"dog", "pug", "duck", "pig"})
        for name, png in built.items():
            with self.subTest(pet=name):
                committed = Path(settings.BASE_DIR, "static", "pets", f"{name}.png").read_bytes()
                self.assertEqual(png, committed, "Run bin/pets and commit the result.")

    def test_every_frame_is_square(self):
        """assets/app.css steps across a sheet one pet-height at a time, so a
        frame has to be as wide as it is tall, whatever its pixel size."""
        frames = runpy.run_path(str(BUILDER))["FRAMES"]
        for path in Path(settings.BASE_DIR, "static", "pets").glob("*.png"):
            with self.subTest(pet=path.stem):
                width, height = struct.unpack(">II", path.read_bytes()[16:24])
                self.assertEqual(width, height * len(frames))

    def test_every_frame_is_shown_from_its_place_in_the_sheet(self):
        """assets/app.css picks a frame by its index in bin/pets' FRAMES, so
        adding or reordering a frame there has to be matched here."""
        frames = runpy.run_path(str(BUILDER))["FRAMES"]
        css = Path(settings.BASE_DIR, "assets", "app.css").read_text()

        shown = dict(re.findall(r'\.pet\[data-frame="(\w+)"\]\s*{\s*--frame:\s*(\d+);', css))

        self.assertEqual(shown, {name: str(index) for index, name in enumerate(frames)})


class RoamingTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.client.force_login(self.ada)

    def test_the_board_page_loads_the_pets_script_even_with_no_pet(self):
        """A pet chosen from the menu arrives without a page load, so the
        script has to be there already."""
        response = self.client.get(reverse("board_detail", args=[self.board.pk]))

        self.assertContains(response, '<script src="/static/js/pet.js" defer></script>')
