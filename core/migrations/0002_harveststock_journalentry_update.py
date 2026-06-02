import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        # Tambah model HarvestStock
        migrations.CreateModel(
            name="HarvestStock",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("qty", models.PositiveIntegerField()),
                ("note", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "seed",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="harvest_stocks",
                        to="core.seed",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        # Tambah field account_name ke JournalEntry (isi default dulu)
        migrations.AddField(
            model_name="journalentry",
            name="account_name",
            field=models.CharField(max_length=120, default="Manual"),
            preserve_default=False,
        ),
        # Ubah choices direction: IN/OUT -> DB/KR
        migrations.AlterField(
            model_name="journalentry",
            name="direction",
            field=models.CharField(
                max_length=3,
                choices=[("DB", "Debit"), ("KR", "Kredit")],
            ),
        ),
        # Ganti created_at dari auto_now_add ke bisa diisi manual
        migrations.AlterField(
            model_name="journalentry",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]