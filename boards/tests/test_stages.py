import threading

from django.db import connection
from django.db.models import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from boards.models import Board, Card, Stage

from .test_cards import a_card, a_user


def names(board):
    return [s.name for s in board.stages.all()]


class EditStagesTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.to_do, self.in_progress, self.done = self.board.stages.all()
        self.url = reverse("stage_list", args=[self.board.pk])
        self.client.force_login(self.ada)

    def add(self, name):
        return self.client.post(
            reverse("stage_create", args=[self.board.pk]), {"new-name": name}
        )

    def rename(self, stage, name):
        return self.client.post(
            reverse("stage_rename", args=[self.board.pk, stage.pk]),
            {f"stage{stage.pk}-name": name},
        )

    def delete(self, stage):
        return self.client.post(reverse("stage_delete", args=[self.board.pk, stage.pk]))

    def test_the_board_links_to_edit_stages(self):
        response = self.client.get(reverse("board_detail", args=[self.board.pk]))

        self.assertContains(response, f'href="{self.url}"')

    def test_the_page_lists_stages_in_board_order_with_their_card_counts(self):
        a_card(self.in_progress)
        a_card(self.in_progress)
        # Board order differs from creation order, so a query that lost its
        # ordering would show itself here.
        self.to_do.shift(1)
        self.assertEqual(names(self.board), ["In Progress", "To Do", "Done"])

        content = self.client.get(self.url).content.decode()

        self.assertLess(content.index('value="In Progress"'), content.index('value="To Do"'))
        self.assertLess(content.index('value="To Do"'), content.index('value="Done"'))
        self.assertIn("2 Cards", content)
        self.assertIn("0 Cards", content)

    def test_a_member_adds_a_stage_and_it_appears_at_the_end(self):
        response = self.add("Review")

        self.assertRedirects(response, self.url)
        self.assertEqual(names(self.board), ["To Do", "In Progress", "Done", "Review"])
        board = self.client.get(reverse("board_detail", args=[self.board.pk]))
        self.assertContains(board, "Review</h2>")

    def test_any_member_may_edit_stages(self):
        grace = a_user("grace@example.com")
        self.board.memberships.create(user=grace)
        self.client.force_login(grace)

        self.add("Review")
        self.rename(self.to_do, "Backlog")

        self.assertEqual(names(self.board), ["Backlog", "In Progress", "Done", "Review"])

    def test_a_stage_can_be_renamed(self):
        response = self.rename(self.in_progress, "Doing")

        self.assertRedirects(response, self.url)
        self.assertEqual(names(self.board), ["To Do", "Doing", "Done"])

    def test_a_rename_may_change_only_the_case(self):
        self.rename(self.done, "DONE")

        self.assertEqual(names(self.board), ["To Do", "In Progress", "DONE"])

    def test_names_must_be_unique_on_the_board_ignoring_case(self):
        response = self.add("done")
        self.assertContains(response, "already has a Stage called Done", status_code=400)

        response = self.rename(self.to_do, "in progress")
        self.assertContains(response, "already has a Stage called In Progress", status_code=400)

        self.assertEqual(names(self.board), ["To Do", "In Progress", "Done"])

    def test_another_board_may_use_the_same_name(self):
        Board.objects.create_with_owner(name="Elsewhere", owner=self.ada).add_stage("Review")

        self.add("Review")

        self.assertIn("Review", names(self.board))

    def test_a_name_cannot_be_empty(self):
        self.assertEqual(self.add("   ").status_code, 400)
        self.assertEqual(self.rename(self.to_do, "").status_code, 400)

        self.assertEqual(names(self.board), ["To Do", "In Progress", "Done"])

    def test_an_empty_stage_can_be_deleted(self):
        response = self.delete(self.in_progress)

        self.assertRedirects(response, self.url)
        self.assertEqual(names(self.board), ["To Do", "Done"])

    def test_deleting_a_stage_that_holds_cards_is_refused_with_the_reason(self):
        a_card(self.done, "Keep me")
        a_card(self.done, "And me")

        response = self.delete(self.done)

        self.assertContains(response, "Still holds 2 Cards. Move them out first.", status_code=400)
        self.assertEqual(names(self.board), ["To Do", "In Progress", "Done"])
        self.assertEqual(self.done.cards.count(), 2)

    def test_the_refusal_says_card_for_one(self):
        a_card(self.done)

        response = self.delete(self.done)

        self.assertContains(response, "Still holds 1 Card. Move it out first.", status_code=400)

    def test_the_last_stage_cannot_be_deleted(self):
        self.delete(self.to_do)
        self.delete(self.in_progress)

        response = self.delete(self.done)

        self.assertContains(response, "A board needs at least one Stage.", status_code=400)
        self.assertEqual(names(self.board), ["Done"])

    def shift(self, stage, direction):
        return self.client.post(
            reverse("stage_shift", args=[self.board.pk, stage.pk]), {"direction": direction}
        )

    def test_a_stage_moves_up_and_down_one_place_at_a_time(self):
        response = self.shift(self.done, "up")
        self.assertRedirects(response, self.url)
        self.assertEqual(names(self.board), ["To Do", "Done", "In Progress"])

        self.shift(self.to_do, "down")
        self.assertEqual(names(self.board), ["Done", "To Do", "In Progress"])

    def test_the_ends_offer_no_arrow_beyond_them(self):
        content = self.client.get(self.url).content.decode()

        self.assertNotIn('aria-label="Move To Do up"', content)
        self.assertIn('aria-label="Move To Do down"', content)
        self.assertIn('aria-label="Move In Progress up"', content)
        self.assertIn('aria-label="Move In Progress down"', content)
        self.assertIn('aria-label="Move Done up"', content)
        self.assertNotIn('aria-label="Move Done down"', content)

    def test_pressing_past_either_end_changes_nothing(self):
        self.shift(self.to_do, "up")
        self.shift(self.done, "down")

        self.assertEqual(names(self.board), ["To Do", "In Progress", "Done"])

    def test_a_stages_cards_move_with_it_in_their_order(self):
        for title in ["First", "Second", "Third"]:
            a_card(self.to_do, title)

        self.shift(self.to_do, "down")

        self.assertEqual(
            [(c.title, c.position) for c in self.to_do.cards.all()],
            [("First", 0), ("Second", 1), ("Third", 2)],
        )
        content = self.client.get(reverse("board_detail", args=[self.board.pk])).content.decode()
        self.assertLess(content.index("In Progress</h2>"), content.index("To Do</h2>"))
        self.assertLess(content.index("To Do</h2>"), content.index("First"))
        self.assertLess(content.index("First"), content.index("Done</h2>"))

    def test_gaps_left_by_deleted_stages_close_up(self):
        self.delete(self.in_progress)
        self.add("Review")

        self.shift(self.to_do, "down")

        self.assertEqual(names(self.board), ["Done", "To Do", "Review"])
        self.assertEqual([s.position for s in self.board.stages.all()], [0, 1, 2])

    def test_a_direction_other_than_up_or_down_is_refused(self):
        for direction in ["", "left", "UP"]:
            with self.subTest(direction=direction):
                self.assertEqual(self.shift(self.in_progress, direction).status_code, 400)

        self.assertEqual(names(self.board), ["To Do", "In Progress", "Done"])

    def test_renaming_and_adding_leave_stage_order_alone(self):
        self.rename(self.to_do, "Zebra")
        self.add("Aardvark")

        self.assertEqual(names(self.board), ["Zebra", "In Progress", "Done", "Aardvark"])

    def test_the_database_will_not_delete_a_stage_with_its_cards(self):
        a_card(self.done)

        with self.assertRaises(ProtectedError):
            self.done.delete()


class StageAccessTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.adas_board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.graces_board = Board.objects.create_with_owner(
            name="Secret Plans", owner=self.grace
        )
        self.client.force_login(self.ada)

    def test_a_non_member_cannot_see_or_change_stages(self):
        theirs = self.graces_board.stages.first()
        stage_urls = [
            reverse("stage_rename", args=[board.pk, theirs.pk])
            for board in [self.graces_board, self.adas_board]
        ] + [
            reverse("stage_delete", args=[board.pk, theirs.pk])
            for board in [self.graces_board, self.adas_board]
        ]

        self.assertEqual(
            self.client.get(reverse("stage_list", args=[self.graces_board.pk])).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                reverse("stage_create", args=[self.graces_board.pk]), {"new-name": "Planted"}
            ).status_code,
            404,
        )
        for url in stage_urls:
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.post(url, {f"stage{theirs.pk}-name": "Defaced"}).status_code,
                    404,
                )

        response = self.client.post(
            reverse("stage_shift", args=[self.graces_board.pk, theirs.pk]), {"direction": "down"}
        )
        self.assertEqual(response.status_code, 404)

        self.assertEqual(names(self.graces_board), ["To Do", "In Progress", "Done"])

    def test_changes_need_a_post(self):
        stage = self.adas_board.stages.first()
        for url in [
            reverse("stage_create", args=[self.adas_board.pk]),
            reverse("stage_rename", args=[self.adas_board.pk, stage.pk]),
            reverse("stage_delete", args=[self.adas_board.pk, stage.pk]),
            reverse("stage_shift", args=[self.adas_board.pk, stage.pk]),
        ]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 405)

    def test_moving_into_a_deleted_stage_is_a_404(self):
        to_do, in_progress, _ = self.adas_board.stages.all()
        card = a_card(to_do)
        in_progress_pk = in_progress.pk
        in_progress.delete_if_empty()

        move = self.client.post(
            reverse("card_move", args=[self.adas_board.pk, card.pk]), {"stage": in_progress_pk}
        )

        self.assertEqual(move.status_code, 404)


class DeletedStageTests(TestCase):
    """The request that loses a race to a delete holds a Stage that no longer
    exists. The race itself can't be ordered on demand, so it is staged here."""

    def setUp(self):
        self.board = Board.objects.create_with_owner(name="Housework", owner=a_user())
        self.to_do, self.in_progress, _ = self.board.stages.all()
        self.card = a_card(self.to_do)
        Stage.objects.filter(pk=self.in_progress.pk).delete()

    def test_a_move_into_a_stage_deleted_after_it_was_chosen_fails_cleanly(self):
        with self.assertRaises(Stage.DoesNotExist):
            self.card.move_to(self.in_progress)

        self.card.refresh_from_db()
        self.assertEqual((self.card.stage, self.card.position), (self.to_do, 0))

    def test_adding_to_a_stage_deleted_after_it_was_chosen_fails_cleanly(self):
        with self.assertRaises(Stage.DoesNotExist):
            a_card(self.in_progress, "Lost")

        self.assertFalse(Card.objects.filter(title="Lost").exists())


class ConcurrentStageTests(TransactionTestCase):
    """Stage changes racing Card moves, each on its own connection."""

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

    def test_a_stage_deleted_while_a_card_moves_into_it_never_takes_the_card(self):
        for _ in range(5):
            Stage.objects.filter(board=self.board, name="Target").delete()
            target = self.board.add_stage("Target")
            card = a_card(self.to_do)

            delete, move = self.run_together(
                lambda: Stage.objects.get(pk=target.pk).delete_if_empty(),
                lambda: Card.objects.get(pk=card.pk).move_to(target),
            )

            card.refresh_from_db()  # the Card always survives
            if Stage.objects.filter(pk=target.pk).exists():
                # The move won: the delete was refused because of the Card.
                self.assertEqual(card.stage_id, target.pk)
                self.assertIn("Still holds 1 Card", str(delete))
                self.assertIsNone(move)
                card.move_to(self.to_do)
            else:
                # The delete won: the move found no Stage, and the Card stayed.
                self.assertEqual(card.stage, self.to_do)
                self.assertIsNone(delete)
                self.assertIsInstance(move, Stage.DoesNotExist)

    def test_two_deletes_at_once_cannot_remove_the_last_stage(self):
        self.done.delete_if_empty()

        outcomes = self.run_together(
            lambda: Stage.objects.get(pk=self.to_do.pk).delete_if_empty(),
            lambda: Stage.objects.get(pk=self.in_progress.pk).delete_if_empty(),
        )

        self.assertEqual(self.board.stages.count(), 1)
        self.assertEqual(sum(o is None for o in outcomes), 1)
        self.assertIn("at least one Stage", " ".join(str(o) for o in outcomes))

    def test_stages_shifted_at_once_keep_a_contiguous_order(self):
        for name in ["Review", "Ship", "Celebrate"]:
            self.board.add_stage(name)
        stages = list(self.board.stages.all())

        # Repeated, because one round of presses rarely overlaps closely
        # enough to show a missing lock.
        for _ in range(10):
            outcomes = self.run_together(
                *[lambda stage=stage, i=i: stage.shift(-1 if i % 2 else 1) for i, stage in enumerate(stages)]
            )

            self.assertEqual(outcomes, [None] * len(stages))
            self.assertEqual(
                sorted(s.position for s in self.board.stages.all()), list(range(len(stages)))
            )

    def test_two_stages_added_at_once_with_one_name_make_one_stage(self):
        outcomes = self.run_together(
            lambda: Board.objects.get(pk=self.board.pk).add_stage("Review"),
            lambda: Board.objects.get(pk=self.board.pk).add_stage("review"),
        )

        self.assertEqual(self.board.stages.filter(name__iexact="review").count(), 1)
        self.assertEqual(sum(o is None for o in outcomes), 1)
