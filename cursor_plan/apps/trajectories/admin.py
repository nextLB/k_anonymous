from django.contrib import admin

from .models import SensitivePOI, Trajectory, TrajectoryPoint


@admin.register(Trajectory)
class TrajectoryAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "name", "source_filename", "status", "created_at", "raw_points_count", "cleaned_points_count")
    list_filter = ("status", "created_at")
    search_fields = ("name", "source_filename", "owner__username")


@admin.register(TrajectoryPoint)
class TrajectoryPointAdmin(admin.ModelAdmin):
    list_display = ("id", "trajectory", "idx", "lat", "lon", "ts")
    list_filter = ("trajectory",)


@admin.register(SensitivePOI)
class SensitivePOIAdmin(admin.ModelAdmin):
    list_display = ("id", "owner", "name", "category", "center_lat", "center_lon", "radius_m", "created_at")
    search_fields = ("name", "category", "owner__username")

