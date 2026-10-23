"""Obstacle-loop detection + auto-recovery for the BCRD2W.

When a robot vacuum gets stuck (cable, rug fringe, a chair leg, ...), it keeps trying:
it drives into the obstacle, backs up, tries again - there is no sign of a fresh area,
and the room does not get clean. This module is the AI layer that:

1. **detects** the "hit sadly N times in a row" pattern from the live cleaning path
   (without extra hardware - the API exposes no collision telemetry directly), and
2. **recovers** by "rolling back to normal" and resuming: stop the run -> send the
   robot home (GoHome) -> wait until it docks -> restart cleaning. All steps use the
   exact operations we already verified against the real device.

Detection signal (robust, no false positives on normal cleaning): take the most recent
`window_points` path points. A healthy robot spans a large area in any short window; a
stuck one covers only a tiny radius while still travelling a lot and reversing
direction repeatedly (each reversal = one failed attempt/hit against the obstacle).
"""

from __future__ import annotations

import math
import time

from ..home_connect.client import (
    ROBOT_CLEAN_ALL_PROGRAM,
    ROBOT_GO_HOME_PROGRAM,
    HomeConnectClient,
)
from .coverage import (
    CoverageError,
    collect_cleaning_path,
    decode_cleaning_path,
    parse_occupancy_grid,
)

MM_PER_CM = 10
MM_PER_M = 1000


# -- pure geometry helpers -------------------------------------------------

def _segment(p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return dx, dy, math.hypot(dx, dy)


def count_reversals(
    points: list[tuple[float, float]],
    angle_deg: float = 120.0,
) -> int:
    """Number of sharp direction changes in the path (approaching a wall counts once,
    backing up and re-trying counts again)."""
    threshold = math.cos(math.radians(angle_deg))
    reversals = 0
    for i in range(1, len(points) - 1):
        x1, y1, l1 = _segment(points[i - 1], points[i])
        x2, y2, l2 = _segment(points[i], points[i + 1])
        if l1 == 0 or l2 == 0:
            continue
        cos_angle = (x1 * x2 + y1 * y2) / (l1 * l2)
        if cos_angle < threshold:
            reversals += 1
    return reversals


def _window(points, window_points: int) -> list[tuple[float, float]]:
    if len(points) <= window_points:
        return points
    return points[-window_points:]


def window_stuck_analysis(
    points: list[tuple[float, float]],
    window_points: int = 15,
    radius_m: float = 0.5,
    min_distance_m: float = 3.0,
    min_hits: int = 3,
    reversal_deg: float = 120.0,
) -> dict:
    """Analyse the most recent window of the path for a stuck-at-obstacle pattern.

    Returns a dict with `stuck` (bool) and the evidence (span, distance, reversals/hits,
    estimated stuck location).
    """
    if len(points) < window_points:
        return {
            "stuck": False,
            "reason": f"Not enough path data (need >= {window_points} recent points).",
        }

    recent = _window(points, window_points)
    xs = [p[0] for p in recent]
    ys = [p[1] for p in recent]
    span_m = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / MM_PER_M
    distance_m = sum(
        _segment(p, q)[2] for p, q in zip(recent, recent[1:])
    ) / MM_PER_M
    hits = count_reversals(recent, reversal_deg)
    centroid_mm = [sum(xs) / len(xs), sum(ys) / len(ys)]

    stuck = span_m < radius_m and distance_m >= min_distance_m and hits >= min_hits
    if stuck:
        reason = (
            f"STUCK AT AN OBSTACLE: the robot hit it ~{hits} times in a row (back-up and "
            f"re-try). Recent {len(recent)} path points stayed within a {span_m:.2f} m "
            f"area while travelling {distance_m:.1f} m, with {hits} direction reversals - "
            f"it cannot pass and is not covering new ground."
        )
    else:
        reason = (
            f"No obstacle loop: recent {len(recent)} points span {span_m:.2f} m over "
            f"{distance_m:.1f} m of travel ({hits} reversals)."
        )
    return {
        "stuck": stuck,
        "reason": reason,
        "window_points": len(recent),
        "span_m": round(span_m, 2),
        "distance_m": round(distance_m, 2),
        "hits": hits,
        "min_hits": min_hits,
        "centroid_mm": centroid_mm,
    }


def obstacle_approaches(
    points: list[tuple[float, float]],
    grid_info: dict | None,
    hit_radius_mm: float = 70.0,
) -> list[dict]:
    """Bonus, precise check when the occupancy grid carries `resolution` + `origin`.

    Counts how many DISTINCT approach runs the path made against each obstacle zone
    (an approach run = the robot enters the hit-radius around an obstacle and later
    leaves it). Informational only - the stuck decision uses the window analysis, which
    needs no georeferencing. Returns [] when the grid lacks resolution/origin.
    """
    if not grid_info:
        return []
    resolution_cm = grid_info.get("resolution_cm")
    origin = grid_info.get("origin")
    grid = grid_info.get("cells")
    width = grid_info.get("width")
    height = grid_info.get("height")
    if not (resolution_cm and isinstance(origin, dict) and grid and width and height):
        return []
    res_mm = resolution_cm * MM_PER_CM
    ox = float(origin.get("x", 0))
    oy = float(origin.get("y", 0))
    blockers: list[tuple[float, float]] = []
    for iy in range(height):
        for ix in range(width):
            if grid[iy * width + ix] == 2:
                blockers.append((ox + (ix + 0.5) * res_mm, oy + (iy + 0.5) * res_mm))
    if not blockers:
        return []

    step = hit_radius_mm * 2
    zone_counts: dict[tuple[int, int], int] = {}
    in_run = False
    for x, y in points:
        near = any(
            math.hypot(x - bx, y - by) <= hit_radius_mm for bx, by in blockers
        )
        if near and not in_run:
            in_run = True
            zone = (int(x // step), int(y // step))
            zone_counts[zone] = zone_counts.get(zone, 0) + 1
        elif not near:
            in_run = False
    return [
        {"x": (zone[0] + 0.5) * step, "y": (zone[1] + 0.5) * step, "count": count}
        for zone, count in sorted(zone_counts.items())
    ]


# -- full report -----------------------------------------------------------

DEFAULT_RECOVERY_STEPS = ["stop", "go_home", "wait_until_docked", "restart_cleaning"]


def analyze_obstacles(
    points: list[tuple[float, float]],
    grid_info: dict | None = None,
) -> dict:
    """Full report: is the robot stuck on an obstacle, where, and what to do."""
    window = window_stuck_analysis(points)
    approaches = obstacle_approaches(points, grid_info)
    problem = window["stuck"]
    recommendation = (
        "Rolling back to normal and resuming: stop -> return to base -> restart cleaning."
        if problem
        else "The robot is progressing normally - no intervention needed."
    )
    return {
        "problem": problem,
        "reason": window["reason"],
        "window": {k: window[k] for k in ("window_points", "span_m", "distance_m", "hits", "min_hits", "centroid_mm")},
        "obstacle_approaches": approaches,
        "recommendation": recommendation,
        "recovery_steps": list(DEFAULT_RECOVERY_STEPS) if problem else [],
    }


# -- live device -----------------------------------------------------------

def analyze_device_obstacles(
    client: HomeConnectClient,
    ha_id: str,
    map_id: str | None = None,
    collect_seconds: float = 0.0,
    interval: float = 3.0,
) -> dict:
    """Fetch the cleaning path (+ occupancy grid) and report obstacle problems."""
    maps = client.get_maps(ha_id)
    if not maps:
        raise CoverageError("No maps available on the device.")
    if map_id is None:
        map_id = maps[0]["mapId"]

    occ = client.get_map_occupancy_grid(ha_id, map_id)
    grid_info = (
        parse_occupancy_grid(occ) if occ and occ.get("gridMapCompressedZstd") else None
    )
    if collect_seconds and collect_seconds > 0:
        points = collect_cleaning_path(client, ha_id, map_id, collect_seconds, interval)
    else:
        data = client.get_map_cleaning_status(ha_id, map_id)
        blob = data.get("cleaningPathCompressedZstd") if data else None
        points = decode_cleaning_path(blob) if blob else []

    report = analyze_obstacles(points, grid_info)
    report["map_id"] = map_id
    report["path_points"] = len(points)
    return report


def _status_values(client: HomeConnectClient, ha_id: str) -> dict:
    return {i.get("key"): i.get("value") for i in client.get_status(ha_id)}


def run_recovery(
    client: HomeConnectClient,
    ha_id: str,
    wait_dock_timeout: float = 60.0,
    poll_interval: float = 3.0,
) -> list[dict]:
    """Execute the recovery steps on the physical device: stop -> GoHome -> wait for dock
    -> restart cleaning. Returns a per-step success/failure log.

    This affects the real device - only call it with explicit user consent (`--auto`).
    """
    steps: list[dict] = []

    def run(step: str, fn) -> None:
        try:
            detail = fn()
            steps.append({"step": step, "ok": True, "detail": detail})
        except Exception as exc:  # noqa: BLE001 - log any failure
            steps.append({"step": step, "ok": False, "detail": str(exc)})

    def stop():
        client.stop_program(ha_id)
        return "cleaning stopped"

    def go_home():
        client.start_program(ha_id, ROBOT_GO_HOME_PROGRAM)
        return "GoHome started"

    def wait_docked():
        deadline = time.time() + wait_dock_timeout
        while time.time() < deadline:
            v = _status_values(client, ha_id)
            if (
                v.get("BSH.Common.Status.OperationState")
                == "BSH.Common.EnumType.OperationState.Ready"
                and v.get("BSH.Common.Status.BatteryChargingState")
                == "BSH.Common.EnumType.BatteryChargingState.Charging"
            ):
                return "robot is docked and charging"
            time.sleep(poll_interval)
        raise RuntimeError(f"robot did not dock within {wait_dock_timeout}s")

    def restart():
        client.start_program(ha_id, ROBOT_CLEAN_ALL_PROGRAM)
        return "cleaning restarted"

    run("stop", stop)
    run("go_home", go_home)
    run("wait_until_docked", wait_docked)
    run("restart_cleaning", restart)
    return steps
