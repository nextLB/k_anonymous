from django.urls import path

from . import views


urlpatterns = [
    path("", views.index, name="home"),
    path("dashboard/", views.index, name="dashboard"),
    path("dashboard/run/<int:traj_id>/start/", views.run, name="run_start"),
    path("dashboard/run/<int:run_id>/", views.run_detail, name="run_detail"),
    path("dashboard/run/<int:run_id>/geojson/", views.run_geojson, name="run_geojson"),
    path("dashboard/run/<int:run_id>/download.geojson", views.download_geojson, name="download_geojson"),
    path("dashboard/run/<int:run_id>/download.csv", views.download_csv, name="download_csv"),
]

