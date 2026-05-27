"""
Debug script for inspecting stop_id values in the GTFS-RT feed.

Usage:
  python find_stops.py --keyword "kelvin"   # search stops by name
  python find_stops.py --live               # list stop_ids seen in the live GTFS-RT feed
"""
import argparse
import sys
import time
import requests

try:
    from google.transit import gtfs_realtime_pb2
except ImportError:
    sys.exit("gtfs-realtime-bindings is required: pip install gtfs-realtime-bindings")

GTFS_RT_URL = "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/tripupdates"
GTFS_STOPS_URL = "https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip"


def live_stop_ids(limit=200):
    """Collect stop_ids currently present in the GTFS-RT feed."""
    print("Fetching GTFS-RT feed...")
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
    """Search stops.txt in the static GTFS for stops matching the given keyword."""
    import io, zipfile
    print(f"Fetching static GTFS data (large file)...")
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
    print(f"\n--- Stops containing '{keyword}' ---")
    found = 0
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) <= max(id_idx, name_idx):
            continue
        if kw in parts[name_idx].lower():
            print(f"  stop_id={parts[id_idx]:<20}  name={parts[name_idx]}")
            found += 1
    print(f"({found} result(s))")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live",    action="store_true", help="List stop_ids from the live GTFS-RT feed")
    parser.add_argument("--keyword", type=str,            help="Search static GTFS stops by name")
    args = parser.parse_args()

    if args.live:
        ids = live_stop_ids()
        print("\n--- stop_ids in GTFS-RT (up to 200) ---")
        for sid in ids:
            print(f"  {sid}")
        # Check whether place_* format is used
        place_ids = [s for s in ids if s.startswith("place_")]
        if place_ids:
            print(f"\n>>> place_* format detected: {place_ids}")
        else:
            print("\n>>> GTFS-RT does not use place_* IDs. Set numeric IDs in config.py.")
    elif args.keyword:
        search_gtfs_stops(args.keyword)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
