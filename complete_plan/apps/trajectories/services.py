from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
from typing import Iterable, Sequence

import numpy as np
from dateutil import parser as dt_parser


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float
    ts: datetime


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1 = np.deg2rad(lat1)
    phi2 = np.deg2rad(lat2)
    dphi = np.deg2rad(lat2 - lat1)
    dl = np.deg2rad(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * (np.sin(dl / 2) ** 2)
    return float(2 * r * np.arctan2(np.sqrt(a), np.sqrt(1 - a)))


def trajectory_length_m(points: Sequence[Point]) -> float:
    if len(points) < 2:
        return 0.0
    dist = 0.0
    for i in range(1, len(points)):
        dist += _haversine_m(points[i - 1].lat, points[i - 1].lon, points[i].lat, points[i].lon)
    return dist


def parse_uploaded_file(filename: str, content_bytes: bytes) -> list[Point]:
    name = (filename or "").lower()
    text = content_bytes.decode("utf-8", errors="ignore")

    if name.endswith(".gpx"):
        return _parse_gpx(text)
    if name.endswith(".plt"):
        return _parse_geolife_plt(text)
    if name.endswith(".json"):
        return _parse_json_points(text)
    if name.endswith(".csv"):
        return _parse_csv_points(text)

    # 尝试自动探测：GPX -> JSON -> CSV -> GeoLife
    for parser in (_parse_gpx, _parse_json_points, _parse_csv_points, _parse_geolife_plt):
        try:
            pts = parser(text)
            if pts:
                return pts
        except Exception:
            continue
    raise ValueError("无法识别文件格式：请使用 .gpx / .plt / .csv / .json")


def _parse_gpx(text: str) -> list[Point]:
    """
    解析 GPX 1.1：
    - 读取 <trkpt lat="" lon=""><time>...</time></trkpt>
    - 兼容默认命名空间（你提供的数据就是这种）
    """
    text = text.strip()
    if not text.startswith("<"):
        return []

    root = ET.fromstring(text)

    # GPX 常见默认命名空间
    ns = ""
    if root.tag.startswith("{") and "}" in root.tag:
        ns = root.tag.split("}")[0].strip("{")

    def q(tag: str) -> str:
        return f"{{{ns}}}{tag}" if ns else tag

    pts: list[Point] = []

    # 轨迹点（可跨多个 trkseg）
    for trkpt in root.findall(f".//{q('trkpt')}"):
        lat_s = trkpt.attrib.get("lat")
        lon_s = trkpt.attrib.get("lon")
        if lat_s is None or lon_s is None:
            continue
        lat = float(lat_s)
        lon = float(lon_s)
        time_el = trkpt.find(q("time"))
        if time_el is None or not (time_el.text and time_el.text.strip()):
            # 先跳过；后面再用 metadata time 回填
            ts = None
        else:
            ts = dt_parser.parse(time_el.text.strip())
        pts.append(Point(lat=lat, lon=lon, ts=ts))  # type: ignore[arg-type]

    if not pts:
        return []

    # 若存在缺失时间，尝试用 metadata/time 补齐
    if any(p.ts is None for p in pts):  # type: ignore[truthy-bool]
        meta_time_el = root.find(f".//{q('metadata')}/{q('time')}")
        base_ts = dt_parser.parse(meta_time_el.text.strip()) if (meta_time_el is not None and meta_time_el.text) else datetime.utcnow()
        filled: list[Point] = []
        for i, p in enumerate(pts):
            if p.ts is None:  # type: ignore[truthy-bool]
                filled.append(Point(lat=p.lat, lon=p.lon, ts=base_ts + timedelta(seconds=i)))
            else:
                filled.append(p)  # type: ignore[arg-type]
        pts = filled

    return sorted(pts, key=lambda p: p.ts)


def _parse_geolife_plt(text: str) -> list[Point]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 7:
        return []
    # GeoLife 常见前 6 行表头
    data_lines = lines[6:] if "," in lines[6] else lines
    pts: list[Point] = []
    for ln in data_lines:
        parts = [p.strip() for p in ln.split(",")]
        if len(parts) < 6:
            continue
        lat = float(parts[0])
        lon = float(parts[1])
        date_s = parts[-2]
        time_s = parts[-1]
        ts = dt_parser.parse(f"{date_s} {time_s}")
        pts.append(Point(lat=lat, lon=lon, ts=ts))
    return sorted(pts, key=lambda p: p.ts)


def _parse_csv_points(text: str) -> list[Point]:
    f = io.StringIO(text)
    reader = csv.DictReader(f)
    if not reader.fieldnames:
        return []
    fields = {c.lower().strip(): c for c in reader.fieldnames}
    for needed in ("lat", "lon"):
        if needed not in fields:
            return []
    ts_key = fields.get("timestamp") or fields.get("ts") or fields.get("time") or fields.get("datetime")
    if not ts_key:
        return []

    pts: list[Point] = []
    for row in reader:
        lat = float(row[fields["lat"]])
        lon = float(row[fields["lon"]])
        ts = dt_parser.parse(row[ts_key])
        pts.append(Point(lat=lat, lon=lon, ts=ts))
    return sorted(pts, key=lambda p: p.ts)


def _parse_json_points(text: str) -> list[Point]:
    obj = json.loads(text)
    if not isinstance(obj, list):
        return []
    pts: list[Point] = []
    for item in obj:
        if not isinstance(item, dict):
            continue
        lat = float(item.get("lat"))
        lon = float(item.get("lon"))
        ts_raw = item.get("timestamp") or item.get("ts") or item.get("time")
        ts = dt_parser.parse(str(ts_raw))
        pts.append(Point(lat=lat, lon=lon, ts=ts))
    return sorted(pts, key=lambda p: p.ts)


def clean_and_impute(
    points: Sequence[Point],
    *,
    max_speed_mps: float = 3.0,
    max_jump_m: float = 120.0,
    short_gap_s: int = 30,
    interp_step_s: int = 5,
) -> list[Point]:
    """
    针对“个人手机采集 + 校园步行”的轻量级清洗与补全：
    - 漂移点：速度过大或单步跳变过大则剔除
    - 短时缺失：线性插值补点
    """
    if len(points) < 2:
        return list(points)

    pts = sorted(points, key=lambda p: p.ts)

    kept: list[Point] = [pts[0]]
    for i in range(1, len(pts)):
        prev = kept[-1]
        cur = pts[i]
        dt = (cur.ts - prev.ts).total_seconds()
        if dt <= 0:
            continue
        d = _haversine_m(prev.lat, prev.lon, cur.lat, cur.lon)
        speed = d / dt
        if d > max_jump_m or speed > max_speed_mps:
            # 丢弃明显漂移点
            continue
        kept.append(cur)

    if len(kept) < 2:
        return kept

    # 短时缺失插值
    out: list[Point] = [kept[0]]
    for i in range(1, len(kept)):
        a = out[-1]
        b = kept[i]
        gap = (b.ts - a.ts).total_seconds()
        if gap <= 0:
            continue
        if gap <= short_gap_s and gap > interp_step_s:
            steps = int(gap // interp_step_s)
            for s in range(1, steps):
                t = a.ts + timedelta(seconds=s * interp_step_s)
                alpha = (t - a.ts).total_seconds() / gap
                out.append(
                    Point(
                        lat=float(a.lat + alpha * (b.lat - a.lat)),
                        lon=float(a.lon + alpha * (b.lon - a.lon)),
                        ts=t,
                    )
                )
        out.append(b)
    return out


def douglas_peucker(points: Sequence[Point], epsilon_m: float = 8.0) -> list[Point]:
    """
    轨迹压缩：Douglas–Peucker（用经纬度近似投影到米级局部平面）。
    """
    if len(points) <= 2:
        return list(points)

    lats = np.array([p.lat for p in points], dtype=float)
    lons = np.array([p.lon for p in points], dtype=float)
    lat0 = float(np.mean(lats))
    # 简单 equirectangular 近似（校园范围足够）
    x = (lons - lons[0]) * np.cos(np.deg2rad(lat0)) * 111320.0
    y = (lats - lats[0]) * 110540.0
    pts = np.stack([x, y], axis=1)

    keep = np.zeros(len(points), dtype=bool)
    keep[0] = True
    keep[-1] = True

    def dist_point_to_segment(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
        ab = b - a
        denom = float(np.dot(ab, ab))
        if denom <= 1e-12:
            return float(np.linalg.norm(p - a))
        t = float(np.dot(p - a, ab) / denom)
        t = max(0.0, min(1.0, t))
        proj = a + t * ab
        return float(np.linalg.norm(p - proj))

    stack: list[tuple[int, int]] = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        a = pts[i]
        b = pts[j]
        max_d = -1.0
        idx = -1
        for k in range(i + 1, j):
            d = dist_point_to_segment(pts[k], a, b)
            if d > max_d:
                max_d = d
                idx = k
        if max_d >= epsilon_m and idx != -1:
            keep[idx] = True
            stack.append((i, idx))
            stack.append((idx, j))

    out = [p for i, p in enumerate(points) if keep[i]]
    return out


def to_geojson_line(points: Sequence[Point]) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[p.lon, p.lat] for p in points]},
        "properties": {
            "start": points[0].ts.isoformat() if points else None,
            "end": points[-1].ts.isoformat() if points else None,
            "count": len(points),
        },
    }

