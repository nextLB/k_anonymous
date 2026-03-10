from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("trajectories/", include("apps.trajectories.urls")),
    path("", include("apps.dashboard.urls")),
]

