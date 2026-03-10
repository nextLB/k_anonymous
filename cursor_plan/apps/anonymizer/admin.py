from django.contrib import admin

from .models import AnonymizationRun, AnonymizedPoint, AnonymizedTrajectory


@admin.register(AnonymizationRun)
class AnonymizationRunAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "trajectory", "created_at", "k", "adaptive_k", "anonymized_set_size", "max_linkage_prob", "status")
    list_filter = ("status", "adaptive_k", "created_at")


@admin.register(AnonymizedTrajectory)
class AnonymizedTrajectoryAdmin(admin.ModelAdmin):
    list_display = ("id", "run", "label", "is_synthetic", "points_count", "length_m")
    list_filter = ("is_synthetic",)


@admin.register(AnonymizedPoint)
class AnonymizedPointAdmin(admin.ModelAdmin):
    list_display = ("id", "trajectory", "idx", "lat", "lon", "ts")
    list_filter = ("trajectory",)

