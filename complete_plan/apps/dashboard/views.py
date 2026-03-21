from __future__ import annotations

import csv
import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.anonymizer.models import AnonymizationRun, AnonymizedPoint, AnonymizedTrajectory
from apps.anonymizer.services import (
    anonymize_trajectory,
    apply_differential_privacy,
    generalize_poi_semantics,
    obfuscate_trajectory_pattern,
)
from apps.trajectories.models import SensitivePOI, Trajectory, TrajectoryPoint
from apps.trajectories.services import Point, clean_and_impute, douglas_peucker, to_geojson_line, trajectory_length_m

from .forms import RunAnonymizationForm


def _owned_traj(user, traj_id: int) -> Trajectory:
    return get_object_or_404(Trajectory, id=traj_id, owner=user)


@login_required
@require_http_methods(["GET"])
def index(request: HttpRequest) -> HttpResponse:
    trajectories = Trajectory.objects.filter(owner=request.user).order_by("-created_at")
    latest_runs: dict[int, AnonymizationRun] = {}
    for r in (
        AnonymizationRun.objects.filter(owner=request.user)
        .order_by("-created_at")
        .select_related("trajectory")[:500]
    ):
        if r.trajectory_id not in latest_runs:
            latest_runs[r.trajectory_id] = r

    rows = [(t, latest_runs.get(t.id)) for t in trajectories]
    return render(
        request,
        "dashboard/index.html",
        {"rows": rows, "form": RunAnonymizationForm()},
    )


@login_required
@require_http_methods(["POST"])
def run(request: HttpRequest, traj_id: int) -> HttpResponse:
    traj = _owned_traj(request.user, traj_id)
    form = RunAnonymizationForm(request.POST)
    if not form.is_valid():
        messages.error(request, "参数不合法")
        return redirect("/dashboard/")

    run_obj = AnonymizationRun.objects.create(
        owner=request.user,
        trajectory=traj,
        k=form.cleaned_data["k"],
        adaptive_k=bool(form.cleaned_data.get("adaptive_k")),
        max_length_error_ratio=form.cleaned_data["max_length_error_ratio"],
        direction_diversity_deg=form.cleaned_data["direction_diversity_deg"],
        synthetic_noise_m=form.cleaned_data["synthetic_noise_m"],
        enable_semantic_generalization=bool(form.cleaned_data.get("enable_semantic_generalization")),
        enable_pattern_obfuscation=bool(form.cleaned_data.get("enable_pattern_obfuscation")),
        enable_differential_privacy=bool(form.cleaned_data.get("enable_differential_privacy")),
        dp_epsilon=form.cleaned_data.get("dp_epsilon", 1.0),
        pattern_obfuscation_strength=form.cleaned_data.get("pattern_obfuscation_strength", 0.3),
    )

    try:
        result = anonymize_trajectory(
            owner_id=request.user.id,
            traj=traj,
            k=run_obj.k,
            adaptive_k=run_obj.adaptive_k,
            max_length_error_ratio=run_obj.max_length_error_ratio,
            direction_diversity_deg=run_obj.direction_diversity_deg,
            synthetic_noise_m=run_obj.synthetic_noise_m,
            enable_semantic_generalization=run_obj.enable_semantic_generalization,
            enable_pattern_obfuscation=run_obj.enable_pattern_obfuscation,
            enable_differential_privacy=run_obj.enable_differential_privacy,
            dp_epsilon=run_obj.dp_epsilon,
            pattern_obfuscation_strength=run_obj.pattern_obfuscation_strength,
        )
        run_obj.anonymized_set_size = len(result.anonymous_set)
        run_obj.max_linkage_prob = float(result.max_linkage_prob)
        run_obj.avg_set_size = float(result.avg_set_size)

        # 计算长度误差（对目标匿名轨迹）
        raw_qs = TrajectoryPoint.objects.filter(trajectory=traj).order_by("idx").values_list("lat", "lon", "ts")
        raw = [Point(lat=lat, lon=lon, ts=ts) for (lat, lon, ts) in raw_qs]
        cleaned = douglas_peucker(clean_and_impute(raw), epsilon_m=8.0)
        run_obj.length_m_original = trajectory_length_m(cleaned)
        run_obj.length_m_anonymized = trajectory_length_m(result.target_anonymized)
        run_obj.length_error_ratio = abs(run_obj.length_m_anonymized - run_obj.length_m_original) / (
            run_obj.length_m_original + 1e-9
        )
        run_obj.save()

        # 保存匿名集到 DB（便于下载/展示）
        for i, pts in enumerate(result.anonymous_set):
            at = AnonymizedTrajectory.objects.create(
                run=run_obj,
                label="target" if i == 0 else f"synthetic_{i}",
                is_synthetic=(i != 0),
                points_count=len(pts),
                length_m=trajectory_length_m(pts),
            )
            AnonymizedPoint.objects.bulk_create(
                [AnonymizedPoint(trajectory=at, idx=j, lat=p.lat, lon=p.lon, ts=p.ts) for j, p in enumerate(pts)],
                batch_size=2000,
            )

        messages.success(request, f"匿名完成：k={result.k_used}，匿名集大小={len(result.anonymous_set)}")
    except Exception as e:
        run_obj.status = "failed"
        run_obj.error_message = str(e)
        run_obj.save(update_fields=["status", "error_message"])
        messages.error(request, f"匿名失败：{e}")

    return redirect(f"/dashboard/run/{run_obj.id}/")


@login_required
@require_http_methods(["GET"])
def run_detail(request: HttpRequest, run_id: int) -> HttpResponse:
    run_obj = get_object_or_404(AnonymizationRun, id=run_id, owner=request.user)
    return render(
        request,
        "dashboard/run_detail.html",
        {
            "run": run_obj,
            "anon_trajs": run_obj.anonymized_trajectories.order_by("id"),
        },
    )


@login_required
@require_http_methods(["GET"])
def run_geojson(request: HttpRequest, run_id: int) -> JsonResponse:
    run_obj = get_object_or_404(AnonymizationRun, id=run_id, owner=request.user)
    traj = run_obj.trajectory
    raw_qs = TrajectoryPoint.objects.filter(trajectory=traj).order_by("idx").values_list("lat", "lon", "ts")
    raw = [Point(lat=lat, lon=lon, ts=ts) for (lat, lon, ts) in raw_qs]
    cleaned = douglas_peucker(clean_and_impute(raw), epsilon_m=8.0)

    anon_lines = []
    for at in run_obj.anonymized_trajectories.order_by("id"):
        qs = at.points.order_by("idx").values_list("lat", "lon", "ts")
        pts = [Point(lat=lat, lon=lon, ts=ts) for (lat, lon, ts) in qs]
        feat = to_geojson_line(pts)
        feat["properties"]["label"] = at.label
        feat["properties"]["synthetic"] = at.is_synthetic
        anon_lines.append(feat)

    return JsonResponse({"run_id": run_obj.id, "raw": to_geojson_line(raw), "cleaned": to_geojson_line(cleaned), "anon_set": anon_lines})


@login_required
@require_http_methods(["GET"])
def download_geojson(request: HttpRequest, run_id: int) -> HttpResponse:
    run_obj = get_object_or_404(AnonymizationRun, id=run_id, owner=request.user)
    features = []
    for at in run_obj.anonymized_trajectories.order_by("id"):
        qs = at.points.order_by("idx").values_list("lat", "lon", "ts")
        pts = [Point(lat=lat, lon=lon, ts=ts) for (lat, lon, ts) in qs]
        feat = to_geojson_line(pts)
        feat["properties"]["label"] = at.label
        feat["properties"]["synthetic"] = at.is_synthetic
        features.append(feat)
    fc = {"type": "FeatureCollection", "features": features}

    resp = JsonResponse(fc, json_dumps_params={"ensure_ascii": False})
    resp["Content-Disposition"] = f'attachment; filename="anon_run_{run_obj.id}.geojson"'
    return resp


@login_required
@require_http_methods(["GET"])
def download_csv(request: HttpRequest, run_id: int) -> HttpResponse:
    run_obj = get_object_or_404(AnonymizationRun, id=run_id, owner=request.user)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["run_id", "traj_label", "idx", "lat", "lon", "timestamp"])
    for at in run_obj.anonymized_trajectories.order_by("id"):
        for lat, lon, ts, idx in at.points.order_by("idx").values_list("lat", "lon", "ts", "idx"):
            w.writerow([run_obj.id, at.label, idx, lat, lon, ts.isoformat()])

    resp = HttpResponse(buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="anon_run_{run_obj.id}.csv"'
    return resp

