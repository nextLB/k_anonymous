from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import AddSensitivePOIForm, UploadTrajectoryForm
from .models import SensitivePOI, Trajectory, TrajectoryPoint
from .services import Point, clean_and_impute, douglas_peucker, parse_uploaded_file, to_geojson_line, trajectory_length_m


def _get_owned_trajectory(user, traj_id: int) -> Trajectory:
    return get_object_or_404(Trajectory, id=traj_id, owner=user)


@login_required
@require_http_methods(["GET", "POST"])
def upload(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = UploadTrajectoryForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.cleaned_data["file"]
            name = form.cleaned_data.get("name") or ""
            content = f.read()
            try:
                points = parse_uploaded_file(f.name, content)
            except Exception as e:
                messages.error(request, f"解析失败：{e}")
                return render(request, "trajectories/upload.html", {"form": form})

            traj = Trajectory.objects.create(
                owner=request.user,
                name=name,
                source_filename=f.name,
                status=Trajectory.Status.RAW,
                raw_points_count=len(points),
                length_m_raw=trajectory_length_m(points),
            )

            bulk = [
                TrajectoryPoint(trajectory=traj, idx=i, lat=p.lat, lon=p.lon, ts=p.ts)
                for i, p in enumerate(points)
            ]
            TrajectoryPoint.objects.bulk_create(bulk, batch_size=2000)

            # 清洗/补全/压缩
            cleaned = douglas_peucker(clean_and_impute(points), epsilon_m=8.0)
            traj.cleaned_points_count = len(cleaned)
            traj.length_m_cleaned = trajectory_length_m(cleaned)
            traj.status = Trajectory.Status.CLEANED
            traj.save(update_fields=["cleaned_points_count", "length_m_cleaned", "status"])

            messages.success(request, f"上传成功：原始点 {traj.raw_points_count}，清洗后点 {traj.cleaned_points_count}")
            return redirect("/dashboard/")
    else:
        form = UploadTrajectoryForm()

    return render(request, "trajectories/upload.html", {"form": form})


@login_required
@require_http_methods(["GET"])
def trajectory_geojson(request: HttpRequest, traj_id: int) -> JsonResponse:
    traj = _get_owned_trajectory(request.user, traj_id)
    qs = traj.points.order_by("idx").values_list("lat", "lon", "ts")
    raw = [Point(lat=lat, lon=lon, ts=ts) for (lat, lon, ts) in qs]
    cleaned = douglas_peucker(clean_and_impute(raw), epsilon_m=8.0)
    return JsonResponse({"trajectory_id": traj.id, "raw": to_geojson_line(raw), "cleaned": to_geojson_line(cleaned)})


@login_required
@require_http_methods(["GET", "POST"])
def pois(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = AddSensitivePOIForm(request.POST)
        if form.is_valid():
            SensitivePOI.objects.create(owner=request.user, **form.cleaned_data)
            messages.success(request, "已添加敏感区域（POI）")
            return redirect("/trajectories/pois/")
    else:
        form = AddSensitivePOIForm()

    items = SensitivePOI.objects.filter(owner=request.user).order_by("-created_at")
    return render(request, "trajectories/pois.html", {"form": form, "items": items})


@login_required
@require_http_methods(["POST"])
def delete_poi(request: HttpRequest, poi_id: int) -> HttpResponse:
    poi = get_object_or_404(SensitivePOI, id=poi_id, owner=request.user)
    poi.delete()
    messages.success(request, "已删除敏感区域")
    return redirect("/trajectories/pois/")

