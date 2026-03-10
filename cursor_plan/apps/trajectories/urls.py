from django.urls import path

from . import views


urlpatterns = [
    path("upload/", views.upload, name="upload"),
    path("<int:traj_id>/geojson/", views.trajectory_geojson, name="trajectory_geojson"),
    path("pois/", views.pois, name="pois"),
    path("pois/<int:poi_id>/delete/", views.delete_poi, name="delete_poi"),
]

