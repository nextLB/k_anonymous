from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("trajectories", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AnonymizationRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("k", models.IntegerField(default=5)),
                ("adaptive_k", models.BooleanField(default=False)),
                ("max_length_error_ratio", models.FloatField(default=0.1)),
                ("direction_diversity_deg", models.FloatField(default=30.0)),
                ("synthetic_noise_m", models.FloatField(default=8.0)),
                ("anonymized_set_size", models.IntegerField(default=0)),
                ("max_linkage_prob", models.FloatField(default=1.0)),
                ("avg_set_size", models.FloatField(default=0.0)),
                ("length_m_original", models.FloatField(default=0.0)),
                ("length_m_anonymized", models.FloatField(default=0.0)),
                ("length_error_ratio", models.FloatField(default=0.0)),
                ("status", models.CharField(default="ok", max_length=20)),
                ("error_message", models.TextField(blank=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                (
                    "trajectory",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="trajectories.trajectory"),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AnonymizedTrajectory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(default="anonymized", max_length=100)),
                ("is_synthetic", models.BooleanField(default=False)),
                ("points_count", models.IntegerField(default=0)),
                ("length_m", models.FloatField(default=0.0)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="anonymized_trajectories",
                        to="anonymizer.anonymizationrun",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AnonymizedPoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idx", models.IntegerField()),
                ("lat", models.FloatField()),
                ("lon", models.FloatField()),
                ("ts", models.DateTimeField()),
                (
                    "trajectory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="points",
                        to="anonymizer.anonymizedtrajectory",
                    ),
                ),
            ],
            options={
                "unique_together": {("trajectory", "idx")},
                "indexes": [
                    models.Index(fields=["trajectory", "idx"], name="anonymizer_traject_5c2b2e_idx"),
                ],
            },
        ),
    ]

