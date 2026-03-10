from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from math import atan2, cos, radians, sin
from typing import Iterable, Sequence

import numpy as np

from apps.trajectories.models import SensitivePOI, Trajectory, TrajectoryPoint
from apps.trajectories.services import Point, clean_and_impute, douglas_peucker, trajectory_length_m


def _bearing_deg(a: Point, b: Point) -> float:
    lat1 = radians(a.lat)
    lat2 = radians(b.lat)
    dlon = radians(b.lon - a.lon)
    y = sin(dlon) * cos(lat2)
    x = cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(dlon)
    brng = atan2(y, x)
    deg = (np.degrees(brng) + 360.0) % 360.0
    return float(deg)


def _angle_diff_deg(a: float, b: float) -> float:
    d = abs(a - b) % 360.0
    return float(min(d, 360.0 - d))


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1 = np.deg2rad(lat1)
    phi2 = np.deg2rad(lat2)
    dphi = np.deg2rad(lat2 - lat1)
    dl = np.deg2rad(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * (np.sin(dl / 2) ** 2)
    return float(2 * r * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))


def _poi_suppress(points: Sequence[Point], pois: Sequence[SensitivePOI]) -> list[Point]:
    if not pois:
        return list(points)
    out: list[Point] = []
    for p in points:
        suppressed = False
        for poi in pois:
            d = _haversine_m(p.lat, p.lon, poi.center_lat, poi.center_lon)
            if d <= poi.radius_m:
                suppressed = True
                break
        if not suppressed:
            out.append(p)
    return out


def _add_noise(points: Sequence[Point], *, noise_m: float, rng: np.random.Generator) -> list[Point]:
    if not points:
        return []
    lat0 = float(np.mean([p.lat for p in points]))
    # meters -> degrees (approx)
    lat_scale = 1.0 / 110540.0
    lon_scale = 1.0 / (111320.0 * cos(radians(lat0)) + 1e-12)

    out: list[Point] = []
    for p in points:
        dx = float(rng.normal(0.0, noise_m))
        dy = float(rng.normal(0.0, noise_m))
        out.append(
            Point(
                lat=float(p.lat + dy * lat_scale),
                lon=float(p.lon + dx * lon_scale),
                ts=p.ts,
            )
        )
    return out


def _time_shift(points: Sequence[Point], *, shift_s: int) -> list[Point]:
    if not points:
        return []
    return [Point(lat=p.lat, lon=p.lon, ts=p.ts + timedelta(seconds=shift_s)) for p in points]


def _trajectory_points_from_db(traj: Trajectory) -> list[Point]:
    qs = TrajectoryPoint.objects.filter(trajectory=traj).order_by("idx").values_list("lat", "lon", "ts")
    return [Point(lat=lat, lon=lon, ts=ts) for (lat, lon, ts) in qs]


def _score_similarity(a: Sequence[Point], b: Sequence[Point]) -> float:
    # 越小越相似：用“起点/终点距离 + 长度差”做简单度量
    if not a or not b:
        return 1e18
    d_start = _haversine_m(a[0].lat, a[0].lon, b[0].lat, b[0].lon)
    d_end = _haversine_m(a[-1].lat, a[-1].lon, b[-1].lat, b[-1].lon)
    la = trajectory_length_m(a)
    lb = trajectory_length_m(b)
    return float(d_start + d_end + abs(la - lb) * 0.2)


@dataclass(frozen=True)
class AnonResult:
    target_anonymized: list[Point]
    anonymous_set: list[list[Point]]  # 包含 target 与若干 synthetic/real
    k_used: int
    max_linkage_prob: float
    avg_set_size: float
    length_error_ratio: float


def adaptive_k_from_density(*, pois_count: int, base_k: int) -> int:
    """
    原型版“自适应 k”：
    - POI 越多，视为更敏感区域/高密度语义点，k 略增
    - 约束：k 至少 2
    """
    k = int(base_k + min(5, max(0, pois_count // 3)))
    return max(2, k)


def anonymize_trajectory(
    *,
    owner_id: int,
    traj: Trajectory,
    k: int,
    adaptive_k: bool,
    max_length_error_ratio: float,
    direction_diversity_deg: float,
    synthetic_noise_m: float,
    seed: int = 20260310,
) -> AnonResult:
    """
    面向任务书的“位置抑制 + 虚假轨迹注入”的可运行原型：
    - 先做清洗/补全/压缩（与上传时一致）
    - 抑制：删除落入用户敏感 POI 圆域内的点
    - 匿名集：优先选取数据库中其他轨迹满足方向差异约束；不足则生成 synthetic 轨迹补齐
    - 可用性约束：尽量控制长度误差 <= max_length_error_ratio（不足时降低噪声强度）
    """
    rng = np.random.default_rng(seed)

    raw = _trajectory_points_from_db(traj)
    base = douglas_peucker(clean_and_impute(raw), epsilon_m=8.0)

    pois = list(SensitivePOI.objects.filter(owner_id=owner_id))
    if adaptive_k:
        k = adaptive_k_from_density(pois_count=len(pois), base_k=k)

    suppressed = _poi_suppress(base, pois)
    suppressed = douglas_peucker(suppressed, epsilon_m=8.0)

    if len(suppressed) < 2:
        # 兜底：抑制后没点了，退化为不抑制（保证系统可跑通）
        suppressed = base

    # 选择真实轨迹补充匿名集
    candidates: list[tuple[float, Trajectory]] = []
    base_bearing = _bearing_deg(suppressed[0], suppressed[-1])
    for other in Trajectory.objects.exclude(id=traj.id).filter(status=Trajectory.Status.CLEANED):
        other_pts = douglas_peucker(clean_and_impute(_trajectory_points_from_db(other)), epsilon_m=8.0)
        if len(other_pts) < 2:
            continue
        other_bearing = _bearing_deg(other_pts[0], other_pts[-1])
        if _angle_diff_deg(base_bearing, other_bearing) < direction_diversity_deg:
            continue
        candidates.append((_score_similarity(suppressed, other_pts), other))
    candidates.sort(key=lambda x: x[0])

    anon_set: list[list[Point]] = [suppressed]
    for _, other in candidates[: max(0, k - 1)]:
        pts = douglas_peucker(clean_and_impute(_trajectory_points_from_db(other)), epsilon_m=8.0)
        anon_set.append(pts)

    # 不足则生成 synthetic
    target_len = trajectory_length_m(suppressed)
    while len(anon_set) < k:
        # 合成策略：抑制后的轨迹 + 小噪声 + 时间漂移（抵御连续查询关联）
        noise = synthetic_noise_m
        synth = _time_shift(_add_noise(suppressed, noise_m=noise, rng=rng), shift_s=int(rng.integers(60, 600)))

        # 控制长度误差
        for _ in range(3):
            l = trajectory_length_m(synth)
            err = abs(l - target_len) / (target_len + 1e-9)
            if err <= max_length_error_ratio:
                break
            noise = max(1.0, noise * 0.6)
            synth = _time_shift(_add_noise(suppressed, noise_m=noise, rng=rng), shift_s=int(rng.integers(60, 600)))

        anon_set.append(synth)

    max_linkage_prob = 1.0 / max(1, len(anon_set))
    avg_set_size = float(np.mean([len(x) for x in anon_set])) if anon_set else 0.0
    l_anon = trajectory_length_m(suppressed)
    length_error_ratio = abs(l_anon - target_len) / (target_len + 1e-9) if target_len > 0 else 0.0

    return AnonResult(
        target_anonymized=suppressed,
        anonymous_set=anon_set,
        k_used=k,
        max_linkage_prob=max_linkage_prob,
        avg_set_size=avg_set_size,
        length_error_ratio=float(length_error_ratio),
    )

