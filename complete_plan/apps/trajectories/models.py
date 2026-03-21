from __future__ import annotations

from django.conf import settings
from django.db import models


class Trajectory(models.Model):
    class Status(models.TextChoices):
        RAW = "raw", "Raw"
        CLEANED = "cleaned", "Cleaned"
        FAILED = "failed", "Failed"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=200, blank=True)
    source_filename = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RAW)
    created_at = models.DateTimeField(auto_now_add=True)

    raw_points_count = models.IntegerField(default=0)
    cleaned_points_count = models.IntegerField(default=0)
    length_m_raw = models.FloatField(default=0.0)
    length_m_cleaned = models.FloatField(default=0.0)

    def __str__(self) -> str:
        return f"Trajectory({self.id}) {self.name or self.source_filename or ''}".strip()


class TrajectoryPoint(models.Model):
    trajectory = models.ForeignKey(Trajectory, on_delete=models.CASCADE, related_name="points")
    idx = models.IntegerField()
    lat = models.FloatField()
    lon = models.FloatField()
    ts = models.DateTimeField()
    is_suppressed = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["trajectory", "idx"]),
            models.Index(fields=["trajectory", "ts"]),
        ]
        unique_together = [("trajectory", "idx")]

    def __str__(self) -> str:
        return f"Point(t={self.ts}, lat={self.lat}, lon={self.lon})"


class SemanticCategory(models.Model):
    """
    POI语义泛化类别定义
    如"餐饮区"、"教学区"、"宿舍区"等
    """
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.name


class SensitivePOI(models.Model):
    """
    用户自定义敏感区域（用于抑制策略）。

    为了便于原型系统跑通，这里采用"圆形区域"表示：中心点 + 半径（米）。
    """

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    category = models.CharField(max_length=50, blank=True)
    semantic_category = models.ForeignKey(
        SemanticCategory, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="pois"
    )
    center_lat = models.FloatField()
    center_lon = models.FloatField()
    radius_m = models.FloatField(default=60.0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"POI({self.name}, r={self.radius_m}m)"

