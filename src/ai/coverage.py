"""Coverage analysis and fake-cleaning detection for the BCRD2W map data.

Data sources (all verified against the real device):
- **Occupancy grid**: `GET .../map/maps/{mapId}/occupancyGrid` returns
  `{"gridMapCompressedZstd": "<base64url>"}`, a Zstandard-compressed flat array of
  ints (row-major, starting bottom-left) where 0=unknown, 1=free, 2=obstacle/wall.
- **Cleaning path**: `GET .../map/maps/{mapId}/cleaningStatus` returns
  `{"cleaningPathCompressedZstd": "<base64url>"}`, a Zstandard-compressed list of
  `{"x": ..., "y": ...}` points describing where the robot actually cleaned.
- **Map metadata / base station**: the map object (see `HomeConnectClient.get_maps`).

These power two AI-layer features (see docs/ai-features.md):
1. **Coverage analysis** — of the area the robot entered (its path bounding box), what
   share did it actually cover (a full sweep = ~100%, gaps/misses = much less). The
   device does not expose the grid resolution, so coverage is computed purely from the
   path, which keeps it scale-independent.
2. **Fake-cleaning detection** — flag paths where the robot travelled a lot but stayed
   in a tiny area (e.g. stuck in place / circling a cable), so cleaning "ran" but
   achieved nothing.

Heuristics: the real device omits `width`/`height`/`resolution` from the grid payload,
so we assume 800x800 cells (verified: 640000 values) and a cell resolution of
`DEFAULT_RESOLUTION_CM`; path coordinates are treated as millimeters.
"""

from __future__ import annotations

import base64
import json
import math
import time
import zstandard

from ..home_connect.client import HomeConnectClient

# Grid cells: 0 unknown, 1 free, 2 obstacle/wall (Home Connect spec).
GRID_UNKNOWN = 0
GRID_FREE = 1
GRID_OBSTACLE = 2

DEFAULT_GRID_WIDTH = 800
DEFAULT_GRID_HEIGHT = 800
DEFAULT_RESOLUTION_CM = 5.0

# Map coordinates are in millimeters; cell step in mm = resolution_cm * 10.
MM_PER_CM = 10


class CoverageError(Exception):
    """Raised when map/cleaning data cannot be decoded."""


# -- decoding -------------------------------------------------------------

def decode_zstd_blob(blob: str) -> bytes:
    """Decode a base64url + Zstandard compressed payload."""
    if not blob:
        raise CoverageError("Empty zstd blob")
    s = blob.strip()
    s = s + "=" * (-len(s) % 4)  # restore padding stripped by base64url
    try:
        raw = base64.urlsafe_b64decode(s)
    except Exception as exc:  # noqa: BLE001 - wrap decode errors
        raise CoverageError(f"Invalid base64url payload: {exc}") from exc
    try:
        return zstandard.ZstdDecompressor().decompress(raw, max_output_size=200_000_000)
    except Exception as exc:  # noqa: BLE001
        raise CoverageError(f"Zstd decompression failed: {exc}") from exc


def decode_occupancy_grid(blob: str) -> list[int]:
    """Decode `gridMapCompressedZstd` into a flat list of cell values."""
    data = json.loads(decode_zstd_blob(blob))
    if not isinstance(data, list):
        raise CoverageError(f"Occupancy grid is not a list (got {type(data).__name__})")
    return [int(v) for v in data]


def parse_occupancy_grid(payload: dict) -> dict:
    """Build a grid-info dict from a raw `/occupancyGrid` response body.

    The device is inconsistent: it sometimes includes `width`/`height`/`resolution`/
    `origin` and sometimes not - fall back to the BCRD2W defaults.
    """
    grid = decode_occupancy_grid(payload["gridMapCompressedZstd"])
    return {
        "cells": grid,
        "width": int(payload.get("width") or DEFAULT_GRID_WIDTH),
        "height": int(payload.get("height") or DEFAULT_GRID_HEIGHT),
        "resolution_cm": float(payload.get("resolution") or DEFAULT_RESOLUTION_CM),
        "origin": payload.get("origin"),
    }


def decode_cleaning_path(blob: str) -> list[tuple[float, float]]:
    """Decode `cleaningPathCompressedZstd` into a list of (x, y) points."""
    data = json.loads(decode_zstd_blob(blob))
    if not isinstance(data, list):
        raise CoverageError(f"Cleaning path is not a list (got {type(data).__name__})")
    points = []
    for item in data:
        if not isinstance(item, dict) or "x" not in item or "y" not in item:
            continue
        points.append((float(item["x"]), float(item["y"])))
    return points


def grid_histogram(grid: list[int]) -> dict[int, int]:
    """Count cells per value (0 = unknown, 1 = free, 2 = obstacle)."""
    counts = {GRID_UNKNOWN: 0, GRID_FREE: 0, GRID_OBSTACLE: 0}
    for value in grid:
        counts[value] = counts.get(value, 0) + 1
    return counts


# -- geometry helpers -----------------------------------------------------

def path_distance_m(points: list[tuple[float, float]]) -> float:
    return sum(
        math.hypot(x2 - x1, y2 - y1)
        for (x1, y1), (x2, y2) in zip(points, points[1:])
    ) / MM_PER_CM / 100.0


def distinct_cells(
    points: list[tuple[float, float]], resolution_cm: float = DEFAULT_RESOLUTION_CM
) -> set[tuple[int, int]]:
    """Quantize path points onto a grid of `resolution_cm` cells (returns unique cells)."""
    step = resolution_cm * MM_PER_CM  # millimeters per cell
    return {(int(x // step), int(y // step)) for x, y in points}


def path_span_m(points: list[tuple[float, float]]) -> float:
    """Diagonal of the bounding box of the path, in meters."""
    if not points:
        return 0.0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / MM_PER_CM / 100.0


# -- analysis -------------------------------------------------------------

def coverage_percent(
    points: list[tuple[float, float]],
    resolution_cm: float = DEFAULT_RESOLUTION_CM,
) -> float | None:
    """How much of the area the robot entered (its path bounding box) it actually covered.

    Of the quantized cells inside the path's bounding box, what share did the path
    visit? 100% would mean a full sweep; a low value means big gaps/missed areas. This
    is self-contained (no map georeferencing needed) and scale-independent, since the
    device does not expose the grid resolution.
    """
    if len(points) < 2:
        return None
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    step = resolution_cm * MM_PER_CM
    cols = int((max(xs) - min(xs)) // step) + 1
    rows = int((max(ys) - min(ys)) // step) + 1
    bbox_cells = cols * rows
    if bbox_cells <= 0:
        return None
    visited = len(distinct_cells(points, resolution_cm))
    return min(100.0, visited / bbox_cells * 100.0)


def fake_cleaning_verdict(
    points: list[tuple[float, float]],
    resolution_cm: float = DEFAULT_RESOLUTION_CM,
    min_distance_m: float = 5.0,
    min_cells_per_m: float = 2.0,
) -> tuple[bool, str]:
    """Decide whether the cleaning path looks like "fake cleaning" (stuck/circling).

    The metric is **new cells per metre travelled**: a healthy robot keeps entering new
    cells (a dense sweep does ~10-20 cells/m), while a stuck/circling one revisits the
    same handful of cells, so unique cells saturate while distance keeps growing and
    cells/m drops towards zero. (A naive "long path in a small room" heuristic would
    wrongly flag normal lawnmower cleaning, which legitimately covers a small room with
    100+ m of travel.)
    """
    if len(points) < 3:
        return False, "Not enough path data to assess (need >= 3 points)."

    distance = path_distance_m(points)
    span = path_span_m(points)
    cells = distinct_cells(points, resolution_cm)

    if distance < min_distance_m:
        return False, f"Short cleaning path ({distance:.1f} m travelled) - nothing unusual."

    cells_per_m = len(cells) / distance

    if cells_per_m < min_cells_per_m:
        return True, (
            f"SUSPECTED FAKE CLEANING: robot travelled {distance:.1f} m but only entered "
            f"{len(cells)} distinct cells ({cells_per_m:.2f} cells/m; healthy cleaning is "
            f"> {min_cells_per_m}) - it keeps re-cleaning the same spot instead of covering "
            f"new ground (possibly stuck)."
        )
    return False, (
        f"Cleaning looks normal: {distance:.1f} m travelled over a {span:.2f} m span, "
        f"{len(cells)} distinct cells visited ({cells_per_m:.1f} cells/m)."
    )


def analyze_cleaning(
    grid: list[int] | None,
    points: list[tuple[float, float]],
    resolution_cm: float = DEFAULT_RESOLUTION_CM,
    grid_width: int = DEFAULT_GRID_WIDTH,
    grid_height: int = DEFAULT_GRID_HEIGHT,
) -> dict:
    """Full report: cleaning-path coverage % + metrics + fake-cleaning verdict."""
    cells = distinct_cells(points, resolution_cm)
    counts = grid_histogram(grid) if grid else None
    fake, fake_reason = fake_cleaning_verdict(points, resolution_cm)
    return {
        "path_points": len(points),
        "distance_m": round(path_distance_m(points), 2),
        "path_span_m": round(path_span_m(points), 2),
        "distinct_cells_visited": len(cells),
        "grid": {
            "width": grid_width,
            "height": grid_height,
            "free_cells": counts[GRID_FREE] if counts else None,
            "unknown_cells": counts[GRID_UNKNOWN] if counts else None,
            "obstacle_cells": counts[GRID_OBSTACLE] if counts else None,
            "resolution_cm": resolution_cm,
        },
        "coverage_percent": (
            round(coverage_percent(points, resolution_cm), 1) if len(points) >= 2 else None
        ),
        "fake_cleaning": fake,
        "fake_cleaning_reason": fake_reason,
    }


# -- live device ----------------------------------------------------------

def collect_cleaning_path(
    client: HomeConnectClient,
    ha_id: str,
    map_id,
    seconds: float = 30.0,
    interval: float = 3.0,
) -> list[tuple[float, float]]:
    """Accumulate the cleaning path while the robot runs (for a richer coverage report).

    The device's `cleaningStatus` path is short/sparse when reached from a docked or
    just-docked state, so for the demo we sample it during a real cleaning run and merge
    every unique point the device reports. Run `make start` in another terminal while
    this collects.
    """
    points: dict[tuple[float, float], bool] = {}
    deadline = time.time() + seconds
    seen = 0
    while time.time() < deadline:
        blob = None
        try:
            data = client.get_map_cleaning_status(ha_id, map_id)
            blob = data.get("cleaningPathCompressedZstd") if data else None
        except Exception:  # noqa: BLE001 - keep collecting through hiccups
            pass
        if blob:
            for point in decode_cleaning_path(blob):
                points[point] = True
            new = len(points)
            if new != seen:
                print(
                    f"  collected {new} cleaning points... "
                    f"({int(deadline - time.time())}s left)"
                )
                seen = new
        time.sleep(interval)
    return [p for p in points]


def analyze_device_map(
    client: HomeConnectClient,
    ha_id: str,
    map_id: str | None = None,
    resolution_cm: float | None = None,
    points: list[tuple[float, float]] | None = None,
    collect_seconds: float = 0.0,
    interval: float = 3.0,
) -> dict:
    """Fetch grid + cleaning path from the device and build the full report.

    If `collect_seconds` > 0 the cleaning path is first accumulated during a live run.
    """
    maps = client.get_maps(ha_id)
    if not maps:
        raise CoverageError("No maps available on the device.")
    if map_id is None:
        map_id = maps[0]["mapId"]
    target = next((m for m in maps if m.get("mapId") == map_id), maps[0])

    occ = client.get_map_occupancy_grid(ha_id, map_id)
    grid_info = (
        parse_occupancy_grid(occ) if occ and occ.get("gridMapCompressedZstd") else None
    )
    if resolution_cm is None:
        resolution_cm = (
            grid_info["resolution_cm"] if grid_info else DEFAULT_RESOLUTION_CM
        )

    if collect_seconds and collect_seconds > 0:
        points = collect_cleaning_path(client, ha_id, map_id, collect_seconds, interval)
    elif points is None:
        data = client.get_map_cleaning_status(ha_id, map_id)
        blob = data.get("cleaningPathCompressedZstd") if data else None
        points = decode_cleaning_path(blob) if blob else []

    report = analyze_cleaning(
        grid_info["cells"] if grid_info else None,
        points,
        resolution_cm=resolution_cm,
        grid_width=grid_info["width"] if grid_info else DEFAULT_GRID_WIDTH,
        grid_height=grid_info["height"] if grid_info else DEFAULT_GRID_HEIGHT,
    )
    report["map_id"] = map_id
    report["map_name"] = target.get("name") or "(unnamed)"
    report["base_station"] = (target.get("baseStations") or [None])[0]
    report["robot_position"] = client.get_robot_position(ha_id) or {}
    return report
