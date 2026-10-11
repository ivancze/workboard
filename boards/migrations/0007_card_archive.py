import django.db.models.deletion
from django.db import migrations, models


def fill_boards(apps, schema_editor):
    """Every existing Card is on the board, so its board is its Stage's."""
    Card = apps.get_model("boards", "Card")
    Stage = apps.get_model("boards", "Stage")
    Card.objects.update(
        board=models.Subquery(
            Stage.objects.filter(pk=models.OuterRef("stage_id")).values("board_id")
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ("boards", "0006_card_stage_protect"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="board",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cards",
                to="boards.board",
            ),
        ),
        migrations.RunPython(fill_boards, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="card",
            name="board",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cards",
                to="boards.board",
            ),
        ),
        migrations.AlterField(
            model_name="card",
            name="stage",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cards",
                to="boards.stage",
            ),
        ),
        migrations.AlterField(
            model_name="card",
            name="position",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="card",
            name="archived_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="card",
            name="archived_from",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="boards.stage",
            ),
        ),
        migrations.AddConstraint(
            model_name="card",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("archived_at__isnull", True),
                        ("archived_from__isnull", True),
                        ("position__isnull", False),
                        ("stage__isnull", False),
                    ),
                    models.Q(
                        ("archived_at__isnull", False),
                        ("position__isnull", True),
                        ("stage__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="on_the_board_or_archived",
            ),
        ),
    ]
