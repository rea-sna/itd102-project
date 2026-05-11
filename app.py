from flask import Flask, render_template, jsonify
import requests
import time
import io
import csv
import zipfile
import threading
from datetime import datetime

from config import STOP_IDS, MAX_DEPARTURES, CACHE_TTL, HOST, PORT, LOCATION_NAME

try:
    from google.transit import gtfs_realtime_pb2
    _PROTO_OK = True
except ImportError:
    _PROTO_OK = False
    print("[WARN] gtfs-realtime-bindings not installed. Run: pip install gtfs-realtime-bindings")

app = Flask(__name__)

GTFS_RT_URL     = "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/tripupdates"
GTFS_STATIC_URL = "https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip"

# ── 静的 GTFS ルックアップ ──────────────────────────────────────────────────
_static = {
    "route_name": {},    # route_id  -> route_short_name ("333" など)
    "headsign":   {},    # trip_id   -> trip_headsign ("City" など)
    "loaded":     False,
}

def _load_static_gtfs():
    """routes.txt と trips.txt だけを取り出してメモリに保持する"""
    try:
        print("[GTFS] Downloading static feed…")
        resp = requests.get(GTFS_STATIC_URL, timeout=60)
        resp.raise_for_status()

        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open("routes.txt") as f:
                for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                    _static["route_name"][row["route_id"]] = row.get("route_short_name") or row["route_id"]

            with zf.open("trips.txt") as f:
                for row in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                    _static["headsign"][row["trip_id"]] = row.get("trip_headsign", "")

        _static["loaded"] = True
        print(f"[GTFS] Loaded {len(_static['route_name'])} routes, {len(_static['headsign'])} trips")

    except Exception as e:
        print(f"[GTFS] Static load failed: {e}")

# 起動時にバックグラウンドで読み込む
threading.Thread(target=_load_static_gtfs, daemon=True).start()


# ── リアルタイムキャッシュ ────────────────────────────────────────────────
_cache = {
    "departures": [],
    "fetched_at": 0,
    "error": None,
}


def _parse_feed(content: bytes) -> list[dict]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)

    now_ts = int(time.time())
    results = []

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue

        tu       = entity.trip_update
        route_id = tu.trip.route_id
        trip_id  = tu.trip.trip_id

        # 表示用ルート番号: 静的データがあれば short_name、なければ route_id そのまま
        route_name = _static["route_name"].get(route_id, route_id)
        headsign   = _static["headsign"].get(trip_id, "")

        for stu in tu.stop_time_update:
            if stu.stop_id not in STOP_IDS:
                continue

            if stu.HasField("arrival") and stu.arrival.time > 0:
                arr_ts = stu.arrival.time
            elif stu.HasField("departure") and stu.departure.time > 0:
                arr_ts = stu.departure.time
            else:
                continue

            if arr_ts < now_ts - 60:
                continue

            minutes = max(0, (arr_ts - now_ts) // 60)
            results.append({
                "route":      route_name,
                "headsign":   headsign,
                "arrival_ts": arr_ts,
                "minutes":    int(minutes),
                "scheduled":  datetime.fromtimestamp(arr_ts).strftime("%H:%M"),
            })

    results.sort(key=lambda x: x["arrival_ts"])
    return results[:MAX_DEPARTURES]


def fetch_departures() -> list[dict]:
    now = time.time()
    if now - _cache["fetched_at"] < CACHE_TTL:
        return _cache["departures"]

    if not _PROTO_OK:
        _cache["error"] = "gtfs-realtime-bindings が未インストールです"
        return _cache["departures"]

    try:
        resp = requests.get(GTFS_RT_URL, timeout=10,
                            headers={"Accept": "application/x-protobuf"})
        resp.raise_for_status()

        departures = _parse_feed(resp.content)
        _cache["departures"] = departures
        _cache["fetched_at"] = now
        _cache["error"] = None

    except requests.exceptions.HTTPError as e:
        _cache["error"] = f"API エラー: {e.response.status_code}"
    except requests.exceptions.Timeout:
        _cache["error"] = "API タイムアウト"
    except Exception as e:
        _cache["error"] = f"取得エラー: {type(e).__name__}"

    return _cache["departures"]


# ── ルーティング ──────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", location=LOCATION_NAME)


@app.route("/api/departures")
def api_departures():
    departures = fetch_departures()
    return jsonify({
        "departures": departures,
        "updated":    datetime.now().strftime("%H:%M:%S"),
        "error":      _cache["error"],
        "gtfs_ready": _static["loaded"],
    })


@app.route("/api/debug/stops")
def debug_stops():
    if not _PROTO_OK:
        return jsonify({"error": "gtfs-realtime-bindings 未インストール"}), 500
    try:
        resp = requests.get(GTFS_RT_URL, timeout=15,
                            headers={"Accept": "application/x-protobuf"})
        resp.raise_for_status()
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(resp.content)

        stop_ids: set[str] = set()
        for entity in feed.entity:
            if not entity.HasField("trip_update"):
                continue
            for stu in entity.trip_update.stop_time_update:
                stop_ids.add(stu.stop_id)

        return jsonify({
            "total_unique_stops": len(stop_ids),
            "sample": sorted(stop_ids)[:200],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok", "proto": _PROTO_OK, "gtfs_ready": _static["loaded"]})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--host", default=HOST)
    args = parser.parse_args()

    print(f"Starting TransLink Signage at http://{args.host}:{args.port}")
    print(f"Monitoring stops: {STOP_IDS}")
    app.run(host=args.host, port=args.port, debug=False, threaded=False)
