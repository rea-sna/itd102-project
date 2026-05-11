"""
GTFS-RT フィード内の stop_id を調べるデバッグ用スクリプト。

使い方:
  python find_stops.py --keyword "kelvin"   # 停留所名で検索
  python find_stops.py --live               # GTFS-RT に実際に現れる stop_id を一覧

事前に config.py の API_KEY を設定してください。
"""
import argparse
import sys
import time
import requests

try:
    from google.transit import gtfs_realtime_pb2
except ImportError:
    sys.exit("gtfs-realtime-bindings が必要です: pip install gtfs-realtime-bindings")

GTFS_RT_URL = "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/tripupdates"
GTFS_STOPS_URL = "https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip"


def live_stop_ids(limit=200):
    """GTFS-RT フィードから実際に使われている stop_id を収集する"""
    print("GTFS-RT フィードを取得中...")
    resp = requests.get(GTFS_RT_URL, timeout=15,
                        headers={"Accept": "application/x-protobuf"})
    resp.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(resp.content)

    stop_ids = set()
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        for stu in entity.trip_update.stop_time_update:
            stop_ids.add(stu.stop_id)
            if len(stop_ids) >= limit:
                break

    return sorted(stop_ids)


def search_gtfs_stops(keyword: str):
    """静的 GTFS の stops.txt からキーワードに一致する停留所を表示する"""
    import io, zipfile
    print(f"GTFS static データを取得中 (大きいファイルです)...")
    resp = requests.get(GTFS_STOPS_URL, timeout=60, stream=True)
    resp.raise_for_status()

    data = b""
    for chunk in resp.iter_content(chunk_size=65536):
        data += chunk

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        with zf.open("stops.txt") as f:
            lines = f.read().decode("utf-8-sig").splitlines()

    header = lines[0].split(",")
    id_idx   = header.index("stop_id")
    name_idx = header.index("stop_name")

    kw = keyword.lower()
    print(f"\n--- '{keyword}' を含む停留所 ---")
    found = 0
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= max(id_idx, name_idx):
            continue
        if kw in parts[name_idx].lower():
            print(f"  stop_id={parts[id_idx]:<20}  name={parts[name_idx]}")
            found += 1
    print(f"({found} 件)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live",    action="store_true", help="GTFS-RT の stop_id 一覧を表示")
    parser.add_argument("--keyword", type=str,            help="静的 GTFS を停留所名で検索")
    args = parser.parse_args()

    if args.live:
        ids = live_stop_ids()
        print("\n--- GTFS-RT に現れる stop_id (最大200件) ---")
        for sid in ids:
            print(f"  {sid}")
        # place_ 形式があるか確認
        place_ids = [s for s in ids if s.startswith("place_")]
        if place_ids:
            print(f"\n>>> place_* 形式: {place_ids}")
        else:
            print("\n>>> GTFS-RT は place_* を使っていません。数値 ID を config.py に設定してください。")
    elif args.keyword:
        search_gtfs_stops(args.keyword)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
