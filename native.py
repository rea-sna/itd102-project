#!/usr/bin/env python3
"""
TransLink Departure Signage — native Tkinter app.
Split two-platform view: Platform 1 (left) | Platform 2 (right).
Exact 50/50 split via columnconfigure uniform group.
"""

import tkinter as tk
import threading
import time
import math
import io
import csv
import zipfile
import subprocess
import platform
import os
import requests
from datetime import datetime

from config import (
    PLATFORM_1_STOP_IDS, PLATFORM_2_STOP_IDS,
    PLATFORM_1_LABEL, PLATFORM_2_LABEL,
    MAX_PER_PLATFORM, CACHE_TTL, LOCATION_NAME,
)

try:
    from google.transit import gtfs_realtime_pb2
    _PROTO_OK = True
except ImportError:
    _PROTO_OK = False
    print("[WARN] gtfs-realtime-bindings not installed. Run: pip install gtfs-realtime-bindings")

# ── Colour palette ────────────────────────────────────────────────────────────
BG         = "#080c10"
HEADER_BG  = "#0d2244"
ACCENT     = "#1a56a8"
GREEN      = "#22c55e"
AMBER      = "#f59e0b"
RED        = "#ef4444"
TEXT       = "#e8edf2"
MUTED      = "#6b7280"
BORDER     = "#1a2030"
TABLE_HEAD = "#0d1520"
STATUS_BG  = "#05090e"

GTFS_RT_URL     = "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/tripupdates"
GTFS_STATIC_URL = "https://gtfsrt.api.translink.com.au/GTFS/SEQ_GTFS.zip"

_SOUND_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sound.mp3")

def _play_sound():
    def _play():
        try:
            if platform.system() == "Darwin":
                subprocess.run(["afplay", _SOUND_FILE], check=False)
            else:
                subprocess.run(["mpg123", "-q", _SOUND_FILE], check=False)
        except Exception as e:
            print(f"[SOUND] {e}")
    threading.Thread(target=_play, daemon=True).start()

# ── Static GTFS ───────────────────────────────────────────────────────────────
_static = {"route_name": {}, "headsign": {}, "loaded": False}

def _load_static():
    try:
        print("[GTFS] Downloading static feed…")
        resp = requests.get(GTFS_STATIC_URL, timeout=60)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            with zf.open("routes.txt") as f:
                for row in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
                    _static["route_name"][row["route_id"]] = (
                        row.get("route_short_name") or row["route_id"]
                    )
            with zf.open("trips.txt") as f:
                for row in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
                    _static["headsign"][row["trip_id"]] = row.get("trip_headsign", "")
        _static["loaded"] = True
        print(f"[GTFS] {len(_static['route_name'])} routes, {len(_static['headsign'])} trips loaded")
        if _cache["raw"]:
            try:
                _cache["p1"] = _parse_feed(_cache["raw"], PLATFORM_1_STOP_IDS)
                _cache["p2"] = _parse_feed(_cache["raw"], PLATFORM_2_STOP_IDS)
                _cache["dirty"] = True
            except Exception:
                pass
    except Exception as e:
        print(f"[GTFS] Static load failed: {e}")

threading.Thread(target=_load_static, daemon=True).start()

# ── Realtime cache ────────────────────────────────────────────────────────────
_cache = {
    "p1": [], "p2": [],
    "fetched_at": 0.0, "error": None,
    "raw": b"", "dirty": False,
}

def _parse_feed(content: bytes, stop_ids: set) -> list:
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(content)
    now_ts = int(time.time())
    results = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        tu = entity.trip_update
        rname = _static["route_name"].get(tu.trip.route_id, tu.trip.route_id)
        hsign = _static["headsign"].get(tu.trip.trip_id, "")
        for stu in tu.stop_time_update:
            if stu.stop_id not in stop_ids:
                continue
            if   stu.HasField("arrival")   and stu.arrival.time   > 0:
                ts = stu.arrival.time
            elif stu.HasField("departure") and stu.departure.time > 0:
                ts = stu.departure.time
            else:
                continue
            if ts < now_ts - 60:
                continue
            results.append({
                "route":      rname,
                "headsign":   hsign,
                "arrival_ts": ts,
                "scheduled":  datetime.fromtimestamp(ts).strftime("%H:%M"),
            })
    results.sort(key=lambda x: x["arrival_ts"])
    return results[:MAX_PER_PLATFORM]


def _fmt_arrival(arr_ts: int, now_ts: int) -> tuple:
    """Returns (text, color, should_blink)."""
    diff = arr_ts - now_ts
    if diff <= 0:
        return "NOW",                         RED,   True
    if diff < 120:
        return f"{math.ceil(diff / 60)} min", RED,   False
    if diff < 300:
        return f"{math.ceil(diff / 60)} min", AMBER, False
    return     f"{diff // 60} min",           GREEN, False


# ── Main Application ──────────────────────────────────────────────────────────
class SignageApp(tk.Tk):
    FETCH_MS = 30_000
    TICK_MS  = 1_000

    def __init__(self):
        super().__init__()
        self.title(f"{LOCATION_NAME} — Departures")
        self.configure(bg=BG)
        self.attributes("-fullscreen", True)
        self.bind("<Escape>", lambda _: self.attributes("-fullscreen", False))
        self.bind("<F11>",    lambda _: self.attributes("-fullscreen", True))
        self.bind("q",        lambda _: self.destroy())

        self._blink_on = True
        self._alerted  = set()   # arrival_ts values that already triggered sound
        self._p1_refs      = []   # [(dep_dict, arriving_label, row_widgets)]
        self._p2_refs      = []
        self._p1_row_cache = []   # [(cell, badge_lbl, dest_lbl, sched_lbl, arr_lbl, sep)]
        self._p2_row_cache = []

        self._build_ui()
        self._tick()
        self._do_fetch()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_panels()
        self._build_status_bar()

    def _build_header(self):
        hdr = tk.Frame(self, bg=HEADER_BG)
        hdr.pack(fill="x", side="top")
        tk.Frame(hdr, bg=ACCENT, height=3).pack(fill="x", side="bottom")

        left = tk.Frame(hdr, bg=HEADER_BG)
        left.pack(side="left", padx=28, pady=14)
        tk.Label(left, text=LOCATION_NAME,
                 bg=HEADER_BG, fg=TEXT, font=("Helvetica", 38, "bold"),
                 anchor="w").pack(anchor="w")

        self.clock_lbl = tk.Label(hdr, text="--:--:--",
                                  bg=HEADER_BG, fg=TEXT, font=("Courier", 54, "bold"))
        self.clock_lbl.pack(side="right", padx=28)

    def _build_panels(self):
        """
        Two panels that each occupy exactly 50 % of the screen width.
        columnconfigure uniform="half" ensures both columns are identical size
        regardless of content, so the split is pixel-perfect.
        The 3 px ACCENT border between panels lives inside the right wrapper frame.
        """
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1, uniform="half")
        outer.columnconfigure(1, weight=1, uniform="half")
        outer.rowconfigure(0, weight=1)

        # Left panel — no extra border
        self._p1_tbl, self._p1_no_svc = self._make_panel(
            outer, grid_col=0, label=PLATFORM_1_LABEL, left_border=False)
        # Right panel — 3 px ACCENT left border to act as the centre divider
        self._p2_tbl, self._p2_no_svc = self._make_panel(
            outer, grid_col=1, label=PLATFORM_2_LABEL, left_border=True)

    def _make_panel(self, outer: tk.Frame, grid_col: int,
                    label: str, left_border: bool) -> tk.Frame:
        """
        Creates one platform panel.
        `left_border=True` wraps the panel in a 3 px ACCENT frame to draw the divider.
        Returns the inner Frame used for the departure grid.
        """
        if left_border:
            wrapper = tk.Frame(outer, bg=ACCENT)
            wrapper.grid(row=0, column=grid_col, sticky="nsew")
            panel = tk.Frame(wrapper, bg=BG)
            panel.pack(fill="both", expand=True, padx=(3, 0))
        else:
            panel = tk.Frame(outer, bg=BG)
            panel.grid(row=0, column=grid_col, sticky="nsew")

        # ── Column proportions within each panel ──────────────────────────
        # Route badge | Destination (flex) | Sched. | Arriving
        panel.columnconfigure(0, minsize=80)   # route badge
        panel.columnconfigure(1, weight=1)       # destination
        panel.columnconfigure(2, minsize=60)    # scheduled
        panel.columnconfigure(3, minsize=100)    # arriving

        # row 0 — platform name banner
        tk.Label(panel, text=label,
                 bg=ACCENT, fg="white", font=("Helvetica", 24, "bold"),
                 anchor="w", padx=22, pady=12
                 ).grid(row=0, column=0, columnspan=4, sticky="ew")

        # row 1 — column headers
        for col, (txt, anch) in enumerate([
            ("Route",       "w"),
            ("Destination", "w"),
            ("Sched.",      "w"),
            ("Arriving",    "e"),
        ]):
            tk.Label(panel, text=txt.upper(),
                     bg=TABLE_HEAD, fg=MUTED, font=("Helvetica", 15, "bold"),
                     anchor=anch, padx=18, pady=10
                     ).grid(row=1, column=col, sticky="ew")

        # row 2 — separator
        tk.Frame(panel, bg=BORDER, height=1).grid(
            row=2, column=0, columnspan=4, sticky="ew")

        # row 3 — loading/no-service placeholder (kept alive; shown/hidden as needed)
        no_svc = tk.Label(panel, text="Loading…",
                          bg=BG, fg=MUTED, font=("Helvetica", 28))
        no_svc.grid(row=3, column=0, columnspan=4, pady=50)

        # Fix row heights: always divide space into MAX_PER_PLATFORM equal slots
        for i in range(MAX_PER_PLATFORM):
            panel.rowconfigure(i * 2 + 3, weight=1)

        return panel, no_svc

    def _build_status_bar(self):
        sb = tk.Frame(self, bg=STATUS_BG, height=40)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        tk.Frame(sb, bg=BORDER, height=1).pack(fill="x", side="top")
        self.status_lbl = tk.Label(sb, text="Connecting…",
                                   bg=STATUS_BG, fg=MUTED, font=("Helvetica", 14),
                                   anchor="w", padx=16)
        self.status_lbl.pack(side="left")
        tk.Label(sb, text="TransLink Open Data",
                 bg=STATUS_BG, fg=MUTED, font=("Helvetica", 14), padx=16
                 ).pack(side="right")

    # ── 1-second tick ─────────────────────────────────────────────────────────

    def _tick(self):
        self.clock_lbl.config(text=datetime.now().strftime("%H:%M:%S"))
        self._blink_on = not self._blink_on

        if _cache["dirty"]:
            _cache["dirty"] = False
            self._render()

        now_ts = int(time.time())
        for refs in (self._p1_refs, self._p2_refs):
            for dep, arr_lbl, row_widgets in refs:
                text, color, blink_text = _fmt_arrival(dep["arrival_ts"], now_ts)
                arr_lbl.config(
                    text=text,
                    fg=color if not (blink_text and not self._blink_on) else BG,
                )

        # 1分前アラート: 各バスにつき1回だけ再生
        for dep in _cache["p1"] + _cache["p2"]:
            diff = dep["arrival_ts"] - now_ts
            if 0 < diff <= 60 and dep["arrival_ts"] not in self._alerted:
                self._alerted.add(dep["arrival_ts"])
                _play_sound()
        # 過去の記録を掃除
        self._alerted = {ts for ts in self._alerted if ts > now_ts - 180}

        self.after(self.TICK_MS, self._tick)

    # ── Table render ──────────────────────────────────────────────────────────

    def _render(self):
        self._render_panel(self._p1_tbl, _cache["p1"], self._p1_refs,
                           self._p1_row_cache, self._p1_no_svc)
        self._render_panel(self._p2_tbl, _cache["p2"], self._p2_refs,
                           self._p2_row_cache, self._p2_no_svc)

    def _render_panel(self, panel: tk.Frame, deps: list, refs: list,
                      row_cache: list, no_svc_lbl: tk.Label):
        refs.clear()
        now_ts = int(time.time())

        if not deps:
            # Hide all cached rows without destroying them
            for entry in row_cache:
                for w in entry:
                    w.grid_remove()
            no_svc_lbl.config(text="No upcoming services")
            no_svc_lbl.grid(row=3, column=0, columnspan=4, pady=50)
            return

        # Hide the no-service label
        no_svc_lbl.grid_remove()

        for i, dep in enumerate(deps):
            data_row = i * 2 + 3    # 3, 5, 7, …
            sep_row  = data_row + 1

            if i < len(row_cache):
                # ── Update existing row in-place (no flicker) ─────────────
                cell, badge_lbl, dest_lbl, sched_lbl, arr_lbl, sep = row_cache[i]
                cell.grid(row=data_row, column=0, sticky="nsew")
                dest_lbl.grid(row=data_row, column=1, sticky="nsew")
                sched_lbl.grid(row=data_row, column=2, sticky="nsew")
                arr_lbl.grid(row=data_row, column=3, sticky="nsew")
                sep.grid(row=sep_row, column=0, columnspan=4, sticky="ew")
                badge_lbl.config(text=dep["route"])
                dest_lbl.config(text=dep.get("headsign") or "—")
                sched_lbl.config(text=dep["scheduled"])
                text, color, _ = _fmt_arrival(dep["arrival_ts"], now_ts)
                arr_lbl.config(text=text, fg=color)
            else:
                # ── Create a new row ──────────────────────────────────────
                cell = tk.Frame(panel, bg=BG, padx=18, pady=14)
                cell.grid(row=data_row, column=0, sticky="nsew")
                badge_lbl = tk.Label(cell, text=dep["route"],
                                     bg=ACCENT, fg="white", font=("Helvetica", 28, "bold"),
                                     padx=14, pady=6)
                badge_lbl.pack()

                dest_lbl = tk.Label(panel, text=dep.get("headsign") or "—",
                                    bg=BG, fg=TEXT, font=("Helvetica", 32),
                                    anchor="w", padx=18, pady=14)
                dest_lbl.grid(row=data_row, column=1, sticky="nsew")

                sched_lbl = tk.Label(panel, text=dep["scheduled"],
                                     bg=BG, fg=TEXT, font=("Helvetica", 28),
                                     anchor="w", padx=18)
                sched_lbl.grid(row=data_row, column=2, sticky="nsew")

                text, color, _ = _fmt_arrival(dep["arrival_ts"], now_ts)
                arr_lbl = tk.Label(panel, text=text,
                                   bg=BG, fg=color, font=("Helvetica", 36, "bold"),
                                   anchor="e", padx=18)
                arr_lbl.grid(row=data_row, column=3, sticky="nsew")

                sep = tk.Frame(panel, bg=BORDER, height=1)
                sep.grid(row=sep_row, column=0, columnspan=4, sticky="ew")

                row_cache.append((cell, badge_lbl, dest_lbl, sched_lbl, arr_lbl, sep))

            refs.append((dep, arr_lbl, [cell, dest_lbl, sched_lbl, arr_lbl]))

        # Destroy rows that are no longer needed
        while len(row_cache) > len(deps):
            cell, badge_lbl, dest_lbl, sched_lbl, arr_lbl, sep = row_cache.pop()
            cell.destroy()
            dest_lbl.destroy()
            sched_lbl.destroy()
            arr_lbl.destroy()
            sep.destroy()


    # ── Background fetch ──────────────────────────────────────────────────────

    def _do_fetch(self):
        def worker():
            now = time.time()
            if now - _cache["fetched_at"] >= CACHE_TTL:
                if not _PROTO_OK:
                    _cache["error"] = "gtfs-realtime-bindings not installed"
                else:
                    try:
                        resp = requests.get(GTFS_RT_URL, timeout=10,
                                            headers={"Accept": "application/x-protobuf"})
                        resp.raise_for_status()
                        raw = resp.content
                        _cache["raw"]        = raw
                        _cache["p1"]         = _parse_feed(raw, PLATFORM_1_STOP_IDS)
                        _cache["p2"]         = _parse_feed(raw, PLATFORM_2_STOP_IDS)
                        _cache["fetched_at"] = now
                        _cache["error"]      = None
                    except requests.exceptions.HTTPError as e:
                        _cache["error"] = f"API Error: {e.response.status_code}"
                    except requests.exceptions.Timeout:
                        _cache["error"] = "API Timeout"
                    except Exception as e:
                        _cache["error"] = f"Error: {type(e).__name__}"
            self.after(0, self._on_fetch_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_fetch_done(self):
        self._render()
        all_stops = ", ".join(sorted(PLATFORM_1_STOP_IDS | PLATFORM_2_STOP_IDS))
        if _cache["error"]:
            self.status_lbl.config(text=f"Error: {_cache['error']}", fg=RED)
        else:
            self.status_lbl.config(
                text=f"Updated: {datetime.now().strftime('%H:%M:%S')}  |  Stops: {all_stops}",
                fg=MUTED)
        self.after(self.FETCH_MS, self._do_fetch)


if __name__ == "__main__":
    SignageApp().mainloop()
