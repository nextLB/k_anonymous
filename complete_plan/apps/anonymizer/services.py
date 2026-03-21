from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from math import atan2, cos, radians, sin
from typing import Iterable, Sequence

import numpy as np

from apps.trajectories.models import SemanticCategory, SensitivePOI, Trajectory, TrajectoryPoint
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
    enable_semantic_generalization: bool = False,
    enable_pattern_obfuscation: bool = False,
    enable_differential_privacy: bool = False,
    dp_epsilon: float = 1.0,
    pattern_obfuscation_strength: float = 0.3,
) -> AnonResult:
    """
    面向任务书的"位置抑制 + 虚假轨迹注入"的可运行原型：
    - 先做清洗/补全/压缩（与上传时一致）
    - 抑制：删除落入用户敏感 POI 圆域内的点
    - 语义泛化：将POI泛化为语义类别（如"餐饮区"）
    - 轨迹模式混淆：打乱周期性模式
    - 差分隐私：叠加拉普拉斯噪声
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
        suppressed = base

    if enable_semantic_generalization:
        suppressed, visited_semantics = generalize_poi_semantics(suppressed, pois, enable=True)
    else:
        suppressed = suppressed
        visited_semantics = []

    if enable_pattern_obfuscation and len(suppressed) >= 3:
        suppressed = obfuscate_trajectory_pattern(suppressed, pattern_obfuscation_strength, seed)

    suppressed = douglas_peucker(suppressed, epsilon_m=8.0)

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
        if enable_pattern_obfuscation and len(pts) >= 3:
            pts = obfuscate_trajectory_pattern(pts, pattern_obfuscation_strength, seed + len(anon_set))
        if enable_differential_privacy:
            pts = apply_differential_privacy(pts, dp_epsilon, seed=seed + len(anon_set))
        anon_set.append(pts)

    target_len = trajectory_length_m(suppressed)
    while len(anon_set) < k:
        noise = synthetic_noise_m
        synth = _time_shift(_add_noise(suppressed, noise_m=noise, rng=rng), shift_s=int(rng.integers(60, 600)))

        for _ in range(3):
            l = trajectory_length_m(synth)
            err = abs(l - target_len) / (target_len + 1e-9)
            if err <= max_length_error_ratio:
                break
            noise = max(1.0, noise * 0.6)
            synth = _time_shift(_add_noise(suppressed, noise_m=noise, rng=rng), shift_s=int(rng.integers(60, 600)))

        if enable_semantic_generalization and visited_semantics:
            synth = generate_semantic_consistent_synthetic(synth, visited_semantics, noise, rng)

        if enable_pattern_obfuscation and len(synth) >= 3:
            synth = obfuscate_trajectory_pattern(synth, pattern_obfuscation_strength, seed + len(anon_set))

        if enable_differential_privacy:
            synth = apply_differential_privacy(synth, dp_epsilon, seed=seed + len(anon_set))

        anon_set.append(synth)

    target_anonymized = anon_set[0]
    if enable_differential_privacy and not enable_pattern_obfuscation:
        target_anonymized = apply_differential_privacy(target_anonymized, dp_epsilon, seed=seed)

    max_linkage_prob = 1.0 / max(1, len(anon_set))
    avg_set_size = float(np.mean([len(x) for x in anon_set])) if anon_set else 0.0
    l_anon = trajectory_length_m(target_anonymized)
    length_error_ratio = abs(l_anon - target_len) / (target_len + 1e-9) if target_len > 0 else 0.0

    return AnonResult(
        target_anonymized=target_anonymized,
        anonymous_set=anon_set,
        k_used=k,
        max_linkage_prob=max_linkage_prob,
        avg_set_size=avg_set_size,
        length_error_ratio=float(length_error_ratio),
    )


def _detect_trajectory_pattern(points: Sequence[Point]) -> dict:
    """
    检测轨迹的时间模式特征
    返回：平均间隔、标准差、是否存在周期性模式
    """
    if len(points) < 3:
        return {"has_periodicity": False, "avg_interval_s": 0, "std_interval_s": 0}

    intervals = []
    for i in range(1, len(points)):
        interval = (points[i].ts - points[i-1].ts).total_seconds()
        intervals.append(interval)

    if not intervals:
        return {"has_periodicity": False, "avg_interval_s": 0, "std_interval_s": 0}

    avg_interval = np.mean(intervals)
    std_interval = np.std(intervals)

    cv = std_interval / (avg_interval + 1e-9)
    has_periodicity = cv < 0.2 and avg_interval > 10

    return {
        "has_periodicity": has_periodicity,
        "avg_interval_s": float(avg_interval),
        "std_interval_s": float(std_interval),
        "cv": float(cv)
    }


def _time_shift_pattern(points: Sequence[Point], strength: float, rng: np.random.Generator) -> list[Point]:
    """
    轨迹模式混淆：对时间轴进行随机偏移，打破周期性模式
    strength: 混淆强度 (0-1)，影响时间偏移幅度
    """
    if len(points) < 2:
        return list(points)

    pattern_info = _detect_trajectory_pattern(points)
    if not pattern_info["has_periodicity"]:
        return list(points)

    avg_interval = pattern_info["avg_interval_s"]
    max_shift = avg_interval * strength * 0.5

    out: list[Point] = [points[0]]
    for i in range(1, len(points)):
        shift_s = float(rng.uniform(-max_shift, max_shift))
        new_ts = points[i].ts + timedelta(seconds=shift_s)
        out.append(Point(lat=points[i].lat, lon=points[i].lon, ts=new_ts))

    return out


def _path_jitter(points: Sequence[Point], strength: float, rng: np.random.Generator) -> list[Point]:
    """
    路径微调：对轨迹点进行微小随机偏移
    strength: 混淆强度 (0-1)
    """
    if len(points) < 2 or strength <= 0:
        return list(points)

    lat0 = float(np.mean([p.lat for p in points]))
    lon0 = float(np.mean([p.lon for p in points]))
    lat_scale = 1.0 / 110540.0
    lon_scale = 1.0 / (111320.0 * cos(radians(lat0)) + 1e-12)

    jitter_m = 3.0 * strength

    out: list[Point] = []
    for p in points:
        dx = float(rng.normal(0.0, jitter_m))
        dy = float(rng.normal(0.0, jitter_m))
        out.append(Point(
            lat=float(p.lat + dy * lat_scale),
            lon=float(p.lon + dx * lon_scale),
            ts=p.ts
        ))
    return out


def obfuscate_trajectory_pattern(
    points: Sequence[Point],
    strength: float = 0.3,
    seed: int = 20260310
) -> list[Point]:
    """
    轨迹模式混淆主函数
    - 检测周期性模式
    - 应用时间偏移
    - 应用路径微调
    """
    if len(points) < 3 or strength <= 0:
        return list(points)

    rng = np.random.default_rng(seed)
    result = _time_shift_pattern(points, strength, rng)
    result = _path_jitter(result, strength * 0.5, rng)
    return result


def _laplace_noise(value: float, sensitivity: float, epsilon: float) -> float:
    """
    拉普拉斯噪声添加
    sensitivity: 敏感度参数
    epsilon: 隐私预算
    """
    scale = sensitivity / epsilon
    noise = np.random.laplace(0, scale)
    return value + noise


def apply_differential_privacy(
    points: Sequence[Point],
    epsilon: float = 1.0,
    sensitivity_m: float = 50.0,
    seed: int = 20260310
) -> list[Point]:
    """
    差分隐私噪声注入
    - 对每个轨迹点坐标添加拉普拉斯噪声
    - epsilon 越小，隐私保护越强，噪声越大
    - sensitivity_m: 轨迹点的最大移动距离敏感度（米）
    """
    if len(points) < 1 or epsilon <= 0:
        return list(points)

    rng = np.random.default_rng(seed)
    lat0 = float(np.mean([p.lat for p in points]))
    lat_scale = sensitivity_m / 110540.0
    lon_scale = sensitivity_m / (111320.0 * cos(radians(lat0)) + 1e-12)

    out: list[Point] = []
    for p in points:
        noise_lat = rng.laplace(0, lat_scale / epsilon)
        noise_lon = rng.laplace(0, lon_scale / epsilon)
        out.append(Point(
            lat=float(p.lat + noise_lat),
            lon=float(p.lon + noise_lon),
            ts=p.ts
        ))
    return out


def get_semantic_category_name(poi: SensitivePOI) -> str:
    """
    获取POI的语义类别名称
    如果未设置语义类别，则使用原始category或泛化类别
    """
    if poi.semantic_category:
        return poi.semantic_category.name

    category_map = {
        "食堂": "餐饮区",
        "餐厅": "餐饮区",
        "教学楼": "教学区",
        "学院": "教学区",
        "图书馆": "教学区",
        "宿舍": "宿舍区",
        "公寓": "宿舍区",
        "操场": "运动区",
        "体育场": "运动区",
        "体育馆": "运动区",
        "医院": "医疗区",
        "校医院": "医疗区",
        "超市": "商业区",
        "商店": "商业区",
    }

    for keyword, sem_category in category_map.items():
        if keyword in poi.name:
            return sem_category

    return poi.category or "其他区域"


def generalize_poi_semantics(
    points: Sequence[Point],
    pois: Sequence[SensitivePOI],
    enable: bool = True
) -> tuple[list[Point], list[str]]:
    """
    POI语义泛化
    - 返回泛化后的轨迹点和经过的语义类别序列
    - 语义类别用于在生成虚假轨迹时保持行为模式一致性
    """
    if not enable or not pois:
        return list(points), []

    visited_semantics: list[str] = []
    out: list[Point] = []

    for p in points:
        matched_semantic = None
        for poi in pois:
            d = _haversine_m(p.lat, p.lon, poi.center_lat, poi.center_lon)
            if d <= poi.radius_m:
                matched_semantic = get_semantic_category_name(poi)
                break

        if matched_semantic:
            if matched_semantic not in visited_semantics:
                visited_semantics.append(matched_semantic)
        else:
            out.append(p)

    return out, visited_semantics


def generate_semantic_consistent_synthetic(
    base_trajectory: Sequence[Point],
    target_semantics: list[str],
    noise_m: float,
    rng: np.random.Generator
) -> list[Point]:
    """
    生成语义一致的虚假轨迹
    - base_trajectory: 基础轨迹
    - target_semantics: 目标语义类别序列
    - 确保生成的虚假轨迹与真实用户行为模式统计一致
    """
    if not target_semantics:
        return _add_noise(base_trajectory, noise_m=noise_m, rng=rng)

    semantic_spawns = {
        "餐饮区": [(39.9, 116.3), (39.91, 116.31)],
        "教学区": [(39.905, 116.305), (39.91, 116.31)],
        "宿舍区": [(39.895, 116.29), (39.898, 116.295)],
        "运动区": [(39.89, 116.28), (39.892, 116.282)],
        "商业区": [(39.908, 116.315), (39.91, 116.318)],
        "医疗区": [(39.895, 116.32), (39.897, 116.322)],
    }

    num_points = len(base_trajectory)
    if num_points == 0:
        return []

    points_per_semantic = num_points // max(1, len(target_semantics))

    result: list[Point] = []
    current_lat = base_trajectory[0].lat
    current_lon = base_trajectory[0].lon

    for i, sem in enumerate(target_semantics):
        spawn_points = semantic_spawns.get(sem, [(current_lat, current_lon)])
        target_lat, target_lon = spawn_points[i % len(spawn_points)]

        for j in range(points_per_semantic):
            alpha = j / max(1, points_per_semantic)
            lat = current_lat + alpha * (target_lat - current_lat)
            lon = current_lon + alpha * (target_lon - current_lon)

            noise_scale = 1.0 / 110540.0
            lat += rng.normal(0, noise_m * noise_scale)
            lon += rng.normal(0, noise_m * noise_scale)

            ts = base_trajectory[0].ts + timedelta(seconds=j * 30)
            result.append(Point(lat=lat, lon=lon, ts=ts))

        current_lat, current_lon = target_lat, target_lon

    for p in base_trajectory[len(target_semantics) * points_per_semantic:]:
        result.append(p)

    return result

