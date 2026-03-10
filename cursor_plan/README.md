# 校园步行轨迹 K-匿名原型系统（Django）

本目录实现了开题报告/任务书中要求的原型系统主流程：

**上传轨迹 → 自动清洗/补全 → 选择（或自适应）k 值 → 一键匿名（位置抑制 + 虚假轨迹注入） → 计算隐私/可用性指标 → 地图对比展示 → 下载结果/分享**。

> 你已经说明环境由你自己配置：请先 `conda activate k_anonymous`，再按本文安装依赖并运行。

## 目录结构

- `manage.py`：Django 启动入口
- `k_anonymous_platform/`：项目配置与 URL 路由
- `apps/trajectories/`：轨迹上传、解析（GeoLife/CSV/JSON）、清洗与补全
- `apps/anonymizer/`：k-匿名（自适应 k）、敏感点抑制、虚假轨迹注入、指标计算
- `apps/dashboard/`：Web 页面（Leaflet 地图）与下载导出
- `templates/`、`static/`：页面模板与静态资源

## 安装与运行

在项目根目录（本 `cursor_plan/`）下：

```bash
conda activate k_anonymous
pip install -r requirements.txt

# 第一次启动必须先建表（否则会出现 “no such table ...”）
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```

浏览器访问：

- 登录与个人数据：`/accounts/login/`
- 轨迹上传：`/trajectories/upload/`
- 轨迹列表与一键匿名：`/dashboard/`

## 轨迹数据格式

系统支持以下格式（任选其一上传）：

1. **GPX `.gpx`**（你当前数据集）：解析 `<trkpt lat="" lon=""><time>...</time></trkpt>`（兼容 GPX 1.1 默认命名空间）
2. **GeoLife `.plt`**：微软 GeoLife 的轨迹点文件（包含表头行，字段含纬度/经度/时间）
3. **CSV**：至少包含 `lat,lon,timestamp` 三列（timestamp 支持 ISO8601，如 `2026-03-10T08:00:00`）
4. **JSON**：形如 `[{\"lat\":...,\"lon\":...,\"ts\":...}, ...]`

上传后系统会生成 `Trajectory` 与 `TrajectoryPoint`，并对每条轨迹执行清洗/补全。

## 匿名与指标（对应任务书验收点）

- **轨迹清洗**：漂移点剔除（速度/距离跳变）、短时缺失插值补全、轨迹压缩（Douglas–Peucker）
- **k-匿名算法**：位置抑制 + 虚假轨迹注入混合模型，支持自定义 k 与“可用性阈值（长度误差上限）”
- **隐私度量**：
  - 最大轨迹关联概率（近似 \(1/|A|\)，A 为匿名集）
  - 平均匿名集大小
- **可视化**：Web 地图同步显示原始/匿名轨迹，热点 POI 与敏感停留点，支持匿名前后对比下载
- **用户权限**：
  - 默认使用 Django 登录（原始数据只对本人可见）
  - 预留 CAS（校统一身份认证）接入开关（见 `k_anonymous_platform/settings.py`）

## 性能与约束

任务书指标中“30s 内算完 / 轨迹长度误差 ≤ 10%”属于数据规模相关指标。
本原型默认按“单用户小规模轨迹集”设计；当数据规模更大时，可将匿名任务改为异步队列（Celery/RQ）并启用缓存/索引。

## 备注

- 默认数据库：SQLite（可自行切换到 PostgreSQL）
- 默认静态文件：`whitenoise`（开发可直接用 `runserver`）

