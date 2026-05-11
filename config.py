# QUT Kelvin Grove のバス停 ID (プラットフォーム別)
PLATFORM_1_STOP_IDS = {"884"}   # Platform 1 — outbound
PLATFORM_2_STOP_IDS = {"889"}   # Platform 2 — inbound

PLATFORM_1_LABEL = "Platform 1 - RBWH, Carseldine, Chermside, Bracken Ridge"
PLATFORM_2_LABEL = "Platform 2 - Roma Street, City, Woolloongabba, UQ Lakes"

# app.py 後方互換
STOP_IDS = PLATFORM_1_STOP_IDS | PLATFORM_2_STOP_IDS

# プラットフォームごとの最大表示件数 (native.py)
MAX_PER_PLATFORM = 12
# app.py 用
MAX_DEPARTURES = 12

# キャッシュ有効期間 (秒) - RPi 3 の負荷を考慮
CACHE_TTL = 30

# Flask サーバー設定
HOST = "0.0.0.0"
PORT = 5000

# 表示名
LOCATION_NAME = "QUT Kelvin Grove"
