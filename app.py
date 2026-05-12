from flask import Flask, render_template, jsonify, request
import requests
import time
import io
import csv
import zipfile
import threading
import subprocess
import platform as _platform
import tempfile
import os
from datetime import datetime

from config import (
    PLATFORM_1_STOP_IDS, PLATFORM_2_STOP_IDS,
    PLATFORM_1_LABEL, PLATFORM_2_LABEL,
    MAX_PER_PLATFORM, CACHE_TTL, HOST, PORT, LOCATION_NAME,
    CHIME_VOLUME, ANNOUNCE_VOLUME,
)

try:
    from google.cloud import texttospeech as _tts_lib
    from google.oauth2 import service_account as _sa
    _TTS_OK = True
except ImportError:
    _TTS_OK = False
    print("[WARN] google-cloud-texttospeech not installed. Run: pip install google-cloud-texttospeech")

_CREDENTIALS_FILE = "/home/pi/itd102-496002-2013570bf45b.json"
_SOUND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sound.mp3")

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
    "route_name": {},
    "headsign":   {},
    "loaded":     False,
}

def _load_static_gtfs():
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

threading.Thread(target=_load_static_gtfs, daemon=True).start()


# ── リアルタイムキャッシュ ────────────────────────────────────────────────
_cache = {
    "p1":         [],
    "p2":         [],
    "fetched_at": 0,
    "error":      None,
}


def _parse_feed(content: bytes, stop_ids: set) -> list[dict]:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)

    now_ts = int(time.time())
    results = []

    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue

        tu         = entity.trip_update
        route_name = _static["route_name"].get(tu.trip.route_id, tu.trip.route_id)
        headsign   = _static["headsign"].get(tu.trip.trip_id, "")

        for stu in tu.stop_time_update:
            if stu.stop_id not in stop_ids:
                continue

            if stu.HasField("arrival") and stu.arrival.time > 0:
                arr_ts = stu.arrival.time
            elif stu.HasField("departure") and stu.departure.time > 0:
                arr_ts = stu.departure.time
            else:
                continue

            if arr_ts < now_ts - 60:
                continue

            results.append({
                "route":      route_name,
                "headsign":   headsign,
                "arrival_ts": arr_ts,
                "scheduled":  datetime.fromtimestamp(arr_ts).strftime("%H:%M"),
            })

    results.sort(key=lambda x: x["arrival_ts"])
    return results[:MAX_PER_PLATFORM]


def _fetch_all():
    now = time.time()
    if now - _cache["fetched_at"] < CACHE_TTL:
        return

    if not _PROTO_OK:
        _cache["error"] = "gtfs-realtime-bindings が未インストールです"
        return

    try:
        resp = requests.get(GTFS_RT_URL, timeout=10,
                            headers={"Accept": "application/x-protobuf"})
        resp.raise_for_status()
        content = resp.content

        _cache["p1"]         = _parse_feed(content, PLATFORM_1_STOP_IDS)
        _cache["p2"]         = _parse_feed(content, PLATFORM_2_STOP_IDS)
        _cache["fetched_at"] = now
        _cache["error"]      = None

    except requests.exceptions.HTTPError as e:
        _cache["error"] = f"API エラー: {e.response.status_code}"
    except requests.exceptions.Timeout:
        _cache["error"] = "API タイムアウト"
    except Exception as e:
        _cache["error"] = f"取得エラー: {type(e).__name__}"


# ── TTS / チャイム ────────────────────────────────────────────────────────
_tts_client = None

def _get_tts_client():
    global _tts_client
    if _tts_client is None:
        creds = _sa.Credentials.from_service_account_file(
            _CREDENTIALS_FILE,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        _tts_client = _tts_lib.TextToSpeechClient(credentials=creds)
    return _tts_client


def _play_file(path: str, volume: float):
    gain = str(int(volume * 100))
    try:
        if _platform.system() == "Darwin":
            subprocess.run(["afplay", "-v", str(volume), path], check=False)
        else:
            subprocess.run(["mpg123", "-q", "--gain", gain, path], check=False)
    except Exception as e:
        print(f"[SOUND] {e}")


def _do_announce(route: str, headsign: str):
    if headsign:
        speech_text = f"Bus {route} to {headsign}, arriving in 1 minute."
    else:
        speech_text = f"Bus {route}, arriving in 1 minute."

    # 1. チャイム
    _play_file(_SOUND_FILE, CHIME_VOLUME)

    # 2. TTS アナウンス
    if not _TTS_OK:
        return
    try:
        client = _get_tts_client()
        response = client.synthesize_speech(
            input=_tts_lib.SynthesisInput(text=speech_text),
            voice=_tts_lib.VoiceSelectionParams(
                language_code="en-AU",
                name="en-AU-Neural2-D",
            ),
            audio_config=_tts_lib.AudioConfig(
                audio_encoding=_tts_lib.AudioEncoding.MP3,
                speaking_rate=0.95,
            ),
        )
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(response.audio_content)
            tmp_path = f.name
        try:
            _play_file(tmp_path, ANNOUNCE_VOLUME)
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        print(f"[TTS] {e}")


# ── ルーティング ──────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", location=LOCATION_NAME)


@app.route("/api/departures")
def api_departures():
    _fetch_all()
    all_stops = sorted(PLATFORM_1_STOP_IDS | PLATFORM_2_STOP_IDS)
    return jsonify({
        "p1":        _cache["p1"],
        "p2":        _cache["p2"],
        "p1_label":  PLATFORM_1_LABEL,
        "p2_label":  PLATFORM_2_LABEL,
        "updated":   datetime.now().strftime("%H:%M:%S"),
        "error":     _cache["error"],
        "gtfs_ready": _static["loaded"],
        "stop_ids":  all_stops,
    })


@app.route("/api/announce", methods=["POST"])
def api_announce():
    data     = request.get_json(force=True, silent=True) or {}
    route    = str(data.get("route", "")).strip()
    headsign = str(data.get("headsign", "")).strip()
    if not route:
        return jsonify({"error": "route required"}), 400
    threading.Thread(target=_do_announce, args=(route, headsign), daemon=True).start()
    return jsonify({"ok": True})


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
    print(f"Platform 1 stops: {PLATFORM_1_STOP_IDS}")
    print(f"Platform 2 stops: {PLATFORM_2_STOP_IDS}")
    app.run(host=args.host, port=args.port, debug=False, threaded=False)
