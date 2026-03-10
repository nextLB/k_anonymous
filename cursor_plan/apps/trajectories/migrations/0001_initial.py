from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Trajectory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(blank=True, max_length=200)),
                ("source_filename", models.CharField(blank=True, max_length=300)),
                (
                    "status",
                    models.CharField(
                        choices=[("raw", "Raw"), ("cleaned", "Cleaned"), ("failed", "Failed")],
                        default="raw",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("raw_points_count", models.IntegerField(default=0)),
                ("cleaned_points_count", models.IntegerField(default=0)),
                ("length_m_raw", models.FloatField(default=0.0)),
                ("length_m_cleaned", models.FloatField(default=0.0)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="SensitivePOI",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("category", models.CharField(blank=True, max_length=50)),
                ("center_lat", models.FloatField()),
                ("center_lon", models.FloatField()),
                ("radius_m", models.FloatField(default=60.0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="TrajectoryPoint",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("idx", models.IntegerField()),
                ("lat", models.FloatField()),
                ("lon", models.FloatField()),
                ("ts", models.DateTimeField()),
                ("is_suppressed", models.BooleanField(default=False)),
                (
                    "trajectory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="points",
                        to="trajectories.trajectory",
                    ),
                ),
            ],
            options={
                "unique_together": {("trajectory", "idx")},
                "indexes": [
                    models.Index(fields=["trajectory", "idx"], name="trajectorie_traject_6f72e7_idx"),
                    models.Index(fields=["trajectory", "ts"], name="trajectorie_traject_92a0a4_idx"),
                ],
            },
        ),
    ]

