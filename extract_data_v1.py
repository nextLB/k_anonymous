#!/usr/bin/env python3
"""
GPX 轨迹解析与可视化工具
用法：python gpx_plot.py <轨迹文件.gpx>
"""

import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import sys
import os

def parse_gpx(file_path):
    """
    解析 GPX 文件，提取所有轨迹点的经纬度。
    返回 (lats, lons) 两个列表。
    """
    # 注册命名空间（GPX 文件通常包含命名空间）
    namespaces = {'': 'http://www.topografix.com/GPX/1/1'}  # 默认命名空间
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"错误：无法解析 GPX 文件（XML 格式错误）: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"错误：文件 '{file_path}' 未找到。")
        sys.exit(1)

    # 查找所有 trkpt 元素（需要考虑命名空间）
    # 简单方法：使用带命名空间的标签名
    # 因为默认命名空间，标签实际为 {命名空间}trkpt
    ns = root.tag.split('}')[0] + '}' if '}' in root.tag else ''
    trkpts = root.findall(f'.//{ns}trkpt')
    if not trkpts:
        print("错误：未找到任何轨迹点 (trkpt)。")
        sys.exit(1)

    lats = []
    lons = []
    for pt in trkpts:
        lat = pt.get('lat')
        lon = pt.get('lon')
        if lat is None or lon is None:
            continue  # 忽略缺少坐标的点
        try:
            lats.append(float(lat))
            lons.append(float(lon))
        except ValueError:
            print(f"警告：无效的坐标值 (lat={lat}, lon={lon})，已跳过。")
            continue
    return lats, lons

def print_details(file_path, lats, lons):
    """在终端输出详细的坐标信息"""
    print("=" * 60)
    print(f"文件：{os.path.basename(file_path)}")
    print(f"总点数：{len(lats)}")
    if len(lats) == 0:
        print("没有有效的坐标点。")
        return

    # 统计信息
    print(f"纬度范围：{min(lats):.6f} ～ {max(lats):.6f}")
    print(f"经度范围：{min(lons):.6f} ～ {max(lons):.6f}")

    # 显示前5个点和后5个点（如果总数较少则全部显示）
    n_show = min(5, len(lats))
    print("\n前 {} 个点：".format(n_show))
    for i in range(n_show):
        print(f"  {i+1}: 纬度 {lats[i]:.6f}, 经度 {lons[i]:.6f}")

    if len(lats) > 10:
        print("  ...")
        print("后 {} 个点：".format(n_show))
        for i in range(-n_show, 0):
            print(f"  {len(lats)+i+1}: 纬度 {lats[i]:.6f}, 经度 {lons[i]:.6f}")
    elif len(lats) > n_show:
        # 点数在6-10之间，显示全部
        print("\n所有点：")
        for i in range(len(lats)):
            print(f"  {i+1}: 纬度 {lats[i]:.6f}, 经度 {lons[i]:.6f}")
    print("=" * 60)

def plot_track(lats, lons):
    """使用 matplotlib 绘制轨迹"""
    plt.figure(figsize=(10, 6))
    plt.plot(lons, lats, 'b-', linewidth=1, marker='.', markersize=2, label='Track')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.title('GPS Track Visualization')
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.axis('equal')  # 使比例大致相等（经度一度距离在不同纬度不同，但视觉上合理）
    plt.legend()
    plt.tight_layout()
    plt.show()

def main():
    if len(sys.argv) != 2:
        print("用法: python gpx_plot.py <轨迹文件.gpx>")
        sys.exit(1)

    gpx_file = sys.argv[1]
    lats, lons = parse_gpx(gpx_file)

    if lats:
        print_details(gpx_file, lats, lons)
        plot_track(lats, lons)
    else:
        print("未提取到任何有效坐标，无法绘图。")

if __name__ == "__main__":
    main()
