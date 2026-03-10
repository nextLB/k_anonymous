from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.trajectories.models import Trajectory


class AnonymizationRun(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    trajectory = models.ForeignKey(Trajectory, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    k = models.IntegerField(default=5)
    adaptive_k = models.BooleanField(default=False)
    max_length_error_ratio = models.FloatField(default=0.10)
    direction_diversity_deg = models.FloatField(default=30.0)
    synthetic_noise_m = models.FloatField(default=8.0)

    anonymized_set_size = models.IntegerField(default=0)
    max_linkage_prob = models.FloatField(default=1.0)
    avg_set_size = models.FloatField(default=0.0)
    length_m_original = models.FloatField(default=0.0)
    length_m_anonymized = models.FloatField(default=0.0)
    length_error_ratio = models.FloatField(default=0.0)

    status = models.CharField(max_length=20, default="ok")
    error_message = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"AnonRun({self.id}) k={self.k} traj={self.trajectory_id}"


class AnonymizedTrajectory(models.Model):
    run = models.ForeignKey(AnonymizationRun, on_delete=models.CASCADE, related_name="anonymized_trajectories")
    label = models.CharField(max_length=100, default="anonymized")
    is_synthetic = models.BooleanField(default=False)

    points_count = models.IntegerField(default=0)
    length_m = models.FloatField(default=0.0)

    def __str__(self) -> str:
        return f"AnonTraj({self.id}) run={self.run_id} synthetic={self.is_synthetic}"


class AnonymizedPoint(models.Model):
    trajectory = models.ForeignKey(AnonymizedTrajectory, on_delete=models.CASCADE, related_name="points")
    idx = models.IntegerField()
    lat = models.FloatField()
    lon = models.FloatField()
    ts = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["trajectory", "idx"]),
        ]
        unique_together = [("trajectory", "idx")]

