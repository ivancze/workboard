from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from boards.models import Board

from .test_cards import a_card, a_user


class TableCountsTests(TestCase):
    def counts(self):
        output = StringIO()
        call_command("table_counts", stdout=output)
        return dict(line.split() for line in output.getvalue().splitlines())

    def test_counts_every_table_including_djangos_own(self):
        board = Board.objects.create_with_owner(name="Housework", owner=a_user())
        a_card(board.stages.first())

        counts = self.counts()

        self.assertEqual(counts["boards_board"], "1")
        self.assertEqual(counts["boards_stage"], "3")
        self.assertEqual(counts["boards_card"], "1")
        self.assertIn("django_migrations", counts)
        self.assertEqual(list(counts), sorted(counts))
