"""CLI to control the Bosch Spotless BCRD2W (and any Home Connect device) from the laptop.

Examples:
    python -m src.cli login
    python -m src.cli appliances
    python -m src.cli status
    python -m src.cli start            # start cleaning (BSH: CleanAll program)
    python -m src.cli stop
    python -m src.cli resume           # resume (unpause) cleaning
"""

from __future__ import annotations

import argparse
import os
import sys

from .config import load_env
from .home_connect.auth import (
    DEFAULT_REDIRECT_URI,
    DEFAULT_SCOPES,
    TokenStore,
    build_authorization_url,
    exchange_code,
    extract_code_from_url,
)
from .home_connect.client import (
    COMMAND_RESUME,
    ROBOT_CLEAN_ALL_PROGRAM,
    ROBOT_GO_HOME_PROGRAM,
    HomeConnectClient,
    HomeConnectError,
)
from .ai.agent import VacuumAgent
from .ai.llm import LLMError
from .ai import smart_empty
from .ai import coverage as coverage_ai
from .ai import obstacle as obstacle_ai


def get_credentials() -> tuple[str, str]:
    client_id = os.environ.get("HOME_CONNECT_CLIENT_ID", "").strip()
    client_secret = os.environ.get("HOME_CONNECT_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        print(
            "Missing credentials. Set HOME_CONNECT_CLIENT_ID and "
            "HOME_CONNECT_CLIENT_SECRET in the .env file (see .env.example).",
            file=sys.stderr,
        )
        sys.exit(1)
    return client_id, client_secret


def build_client() -> HomeConnectClient:
    client_id, client_secret = get_credentials()
    store = TokenStore()
    token = store.load()
    if token is None:
        print(
            "No stored token. Run: python -m src.cli login",
            file=sys.stderr,
        )
        sys.exit(1)
    return HomeConnectClient(
        client_id,
        client_secret,
        token,
        refresh_callback=store.save,
    )


def resolve_ha_id(client: HomeConnectClient, args: argparse.Namespace) -> str:
    """Use --ha-id if given, otherwise the only appliance or the first connected one."""
    if getattr(args, "ha_id", None):
        return args.ha_id
    appliances = client.get_appliances()
    if not appliances:
        print("No home appliances found.", file=sys.stderr)
        sys.exit(1)
    if len(appliances) == 1:
        return appliances[0]["haId"]
    for app in appliances:
        if app.get("connected"):
            return app["haId"]
    print("Multiple appliances - pass one explicitly with --ha-id.", file=sys.stderr)
    sys.exit(1)


def cmd_login(args: argparse.Namespace) -> None:
    client_id, client_secret = get_credentials()
    redirect_uri = os.environ.get("HOME_CONNECT_REDIRECT_URI", DEFAULT_REDIRECT_URI)
    scope = os.environ.get("HOME_CONNECT_SCOPE", DEFAULT_SCOPES)

    url = build_authorization_url(client_id, redirect_uri=redirect_uri, scope=scope)
    print("1. Open this URL in your browser and log in with your Home Connect account:")
    print(f"   {url}")
    print()
    print("2. After authorizing, you will be redirected. Paste the FULL redirect URL")
    print("   (or just the ?code=... part) below:")

    raw = input("> ").strip()
    if not raw:
        print("Nothing entered. Aborting.", file=sys.stderr)
        sys.exit(1)
    if "code=" in raw:
        code = extract_code_from_url(raw)
    else:
        code = raw

    token = exchange_code(client_id, client_secret, code, redirect_uri=redirect_uri)
    TokenStore().save(token)
    print("Login successful. Token stored locally (gitignored).")


def cmd_appliances(args: argparse.Namespace) -> None:
    client = build_client()
    appliances = client.get_appliances()
    if not appliances:
        print("No home appliances found.")
        return
    for app in appliances:
        print(
            f"- {app.get('name')}: type={app.get('type')} "
            f"connected={app.get('connected')} haId={app.get('haId')}"
        )


def cmd_status(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    for item in client.get_status(ha_id):
        value = item.get("value")
        display = item.get("displayvalue")
        if display:
            value = f"{value} ({display})"
        print(f"  {item.get('key')}: {value}")


def cmd_programs(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    for prog in client.get_available_programs(ha_id):
        print(f"- {prog.get('key')}  ({prog.get('name', '')})")


def cmd_start(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    # The BCRD2W accepts only ROBOT_CLEAN_ALL_PROGRAM and no options (verified via
    # /programs/available). BSH.Common.Root.SelectedProgram is rejected with 409.
    client.start_program(ha_id, ROBOT_CLEAN_ALL_PROGRAM)
    print(f"Started cleaning on {ha_id}.")


def cmd_stop(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    client.stop_program(ha_id)
    print(f"Stopped the active program on {ha_id}.")


def cmd_resume(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    # ResumeProgram unpauses a paused cleaning (BSH.Common.Command.ResumeProgram).
    client.execute_command(ha_id, COMMAND_RESUME)
    print(f"Resumed cleaning on {ha_id}.")


def cmd_dock(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    client.start_program(ha_id, ROBOT_GO_HOME_PROGRAM)
    print(f"Sending the robot back to base (GoHome) on {ha_id}.")


def cmd_chat(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    try:
        agent = VacuumAgent(client)
    except LLMError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
    try:
        reply = agent.run(ha_id, args.message)
    except HomeConnectError as exc:
        print(f"Device error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(reply)


def cmd_settings(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    for item in client.get_settings(ha_id):
        value = item.get("value")
        display = item.get("displayvalue")
        if display:
            value = f"{value} ({display})"
        print(f"  {item.get('key')}: {value}")


def cmd_maps(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    for m in client.get_maps(ha_id):
        print(f"- mapId={m.get('mapId')}  saved={m.get('isSaved')}  name={m.get('name', '')}")


def cmd_mapinfo(args: argparse.Namespace) -> None:
    import json

    client = build_client()
    ha_id = resolve_ha_id(client, args)
    getters = {
        "occupancyGrid": client.get_map_occupancy_grid,
        "layout": client.get_map_layout,
        "cleaningStatus": client.get_map_cleaning_status,
        "objects": client.get_map_detected_objects,
        "rooms": client.get_map_rooms,
        "zones": client.get_map_zones,
    }
    data = client.get_map(ha_id, args.map_id)
    if args.field != "all":
        data = getters[args.field](ha_id, args.map_id)
    print(json.dumps(data, indent=2, default=str))


def cmd_robot(args: argparse.Namespace) -> None:
    import json

    client = build_client()
    ha_id = resolve_ha_id(client, args)
    print(json.dumps(client.get_robot_position(ha_id), indent=2, default=str))


def cmd_summaries(args: argparse.Namespace) -> None:
    import json

    client = build_client()
    ha_id = resolve_ha_id(client, args)
    print(json.dumps(client.get_cleaning_summaries(ha_id), indent=2, default=str))


def cmd_smart_empty(args: argparse.Namespace) -> None:
    import json

    client = build_client()
    ha_id = resolve_ha_id(client, args)
    seconds = smart_empty.get_cleaning_duration(client, ha_id)
    verdict = smart_empty.empty_verdict(seconds)
    print(verdict.pop("reason"))
    print(json.dumps(verdict, indent=2, default=str))


def cmd_watch(args: argparse.Namespace) -> None:
    import json

    client = build_client()
    ha_id = resolve_ha_id(client, args)
    interval = getattr(args, "interval", 5)
    timeout = getattr(args, "timeout", None)
    min_clean = smart_empty.get_min_clean_seconds()

    print("watch: Smart Emptying live monitor")
    verbatim = " ".join(sys.argv[2:]) or "(no extra args)"
    print(f"  invoked : python3 -m src.cli watch {verbatim}")
    print(f"  ha_id   : {ha_id}")
    print(f"  interval: {interval} s")
    print(f"  timeout : {timeout if timeout is not None else 'none (watch until Ctrl-C)'}")
    print(f"  min clean: {min_clean} s (env AI_MIN_CLEAN_SECONDS)")
    print()

    def emit(event: smart_empty.EmptyEvent) -> None:
        print("\n" + event.reason)
        print(
            json.dumps(
                {
                    "cleaning_seconds": round(event.cleaning_seconds, 1),
                    "empty_justified": event.empty_justified,
                    "min_clean_seconds": event.min_clean_seconds,
                },
                indent=2,
            )
        )

    try:
        smart_empty.watch(
            client,
            ha_id,
            interval=interval,
            timeout=timeout,
            on_event=emit,
        )
    except KeyboardInterrupt:
        print("\nStopped watching.")


def _robot_spot(r: dict) -> str:
    """Human description of where the robot is (e.g. 'at the base station')."""
    pos = (r.get("robot_position") or {}).get("position")
    base = r.get("base_station") or {}
    if not pos or not isinstance(base, dict) or "x" not in base:
        return "unknown"
    dist = ((pos.get("x", 0) - base.get("x", 0)) ** 2 + (pos.get("y", 0) - base.get("y", 0)) ** 2) ** 0.5
    where = "at the base station" if dist < 1500 else "in the room"
    return f"{where} (x={pos.get('x')}, y={pos.get('y')})"


def print_coverage_report(r: dict) -> None:
    g = r["grid"]
    cell_m2 = (g["resolution_cm"] / 100.0) ** 2
    free_m2 = (g["free_cells"] or 0) * cell_m2
    obs_m2 = (g["obstacle_cells"] or 0) * cell_m2
    total_cells = g["width"] * g["height"]
    unknown_pct = ((g["unknown_cells"] or 0) / total_cells * 100.0) if total_cells else 0.0

    print("=== Coverage report ===")
    print()
    print(f"Map {r['map_id']} ('{r['map_name']}')")
    print(f"Robot position: {_robot_spot(r)}")
    print()
    print("Cleaning effort")
    print(f"  - Distance travelled:      {r['distance_m']} m")
    print(f"  - Distinct spots cleaned:  {r['distinct_cells_visited']}")
    print(f"  - Area swept (span):       {r['path_span_m']} m")
    cov = r["coverage_percent"]
    if cov is not None:
        print(f"  - Coverage of that area:   ~{cov}%")
    else:
        print("  - Coverage of that area:   not estimable (path too short)")
    print()
    print("Map knowledge")
    print(f"  - Floor mapped:            ~{free_m2:.1f} m^2 ({g['free_cells']} cells)")
    print(f"  - Obstacles detected:      ~{obs_m2:.1f} m^2 ({g['obstacle_cells']} cells)")
    print(f"  - Still unmapped:          ~{unknown_pct:.0f}% of the map canvas")
    print()
    print("Health check")
    if r["fake_cleaning"]:
        print("  [WARN] " + r["fake_cleaning_reason"])
    elif r["distance_m"] < 1.0:
        print("  [INFO] The robot has barely cleaned so far - this reading is not meaningful")
        print("         yet. Start it and collect live, e.g. `make start`, then")
        print("         `make coverage-live COLLECT_SECONDS=60`.")
    else:
        print("  [OK] " + r["fake_cleaning_reason"])


def cmd_coverage(args: argparse.Namespace) -> None:
    import json

    client = build_client()
    ha_id = resolve_ha_id(client, args)
    r = coverage_ai.analyze_device_map(
        client,
        ha_id,
        map_id=getattr(args, "map_id", None),
        collect_seconds=getattr(args, "collect", 0) or 0.0,
        interval=getattr(args, "interval", 3.0),
    )
    if getattr(args, "json", False):
        print(json.dumps(r, indent=2, default=str))
        return
    print_coverage_report(r)
    if getattr(args, "ai", False):
        from .ai.insight import ai_insight

        print()
        print("AI insight (what this means)")
        print("  " + ai_insight(r).replace("\n", "\n  "))


def cmd_obstacles(args: argparse.Namespace) -> None:
    import json

    client = build_client()
    ha_id = resolve_ha_id(client, args)
    r = obstacle_ai.analyze_device_obstacles(
        client,
        ha_id,
        map_id=getattr(args, "map_id", None),
        collect_seconds=getattr(args, "collect", 0) or 0.0,
        interval=getattr(args, "interval", 3.0),
    )

    print(f"Map {r['map_id']} | path points: {r['path_points']}")
    print(r["reason"])
    print(f"Recommendation: {r['recommendation']}")

    recovery = None
    if getattr(args, "auto", False) and r["problem"]:
        print("\nRecovery plan (touches the real device):")
        for step in r["recovery_steps"]:
            print(f"  - {step}")
        if not getattr(args, "yes", False):
            answer = input("Execute on the robot? type 'yes': ").strip().lower()
            if answer != "yes":
                print("Aborted by user.")
                recovery = [{"step": "aborted", "ok": False, "detail": "user declined"}]
        if recovery is None:
            print("\nExecuting recovery...")
            recovery = obstacle_ai.run_recovery(client, ha_id)
            print("Recovery results:")
            for step in recovery:
                status = "OK" if step["ok"] else "FAIL"
                print(f"  [{status}] {step['step']}: {step['detail']}")

    print(json.dumps({"report": r, "recovery": recovery}, indent=2, default=str))


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Home Connect device control")
    parser.add_argument(
        "--ha-id", help="Home appliance id (auto-selected if only one appliance)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("login", help="Authenticate and store the token")
    sub.add_parser("appliances", help="List paired home appliances")
    sub.add_parser("status", help="Show live device status")
    sub.add_parser("programs", help="List available programs")
    sub.add_parser("start", help="Start cleaning (BSH: CleanAll program)")
    sub.add_parser("stop", help="Stop the active program")
    sub.add_parser("resume", help="Resume (unpause) the active program")
    sub.add_parser("dock", help="Send the robot back to base (GoHome program)")
    chat_parser = sub.add_parser("chat", help="Control the device in natural language (AI layer)")
    chat_parser.add_argument("message", help="What do you want, e.g. 'start cleaning'")
    sub.add_parser("settings", help="List device settings (CleaningRobot-Settings)")
    sub.add_parser("maps", help="List robot maps (CleaningRobot-Map)")
    mapinfo_parser = sub.add_parser("mapinfo", help="Show map data as JSON (CleaningRobot-Map)")
    mapinfo_parser.add_argument("--map-id", required=True, help="Map id (see 'maps')")
    mapinfo_parser.add_argument(
        "--field",
        default="all",
        choices=["all", "occupancyGrid", "layout", "cleaningStatus", "objects", "rooms", "zones"],
        help="Which map data to show (default: all basic info)",
    )
    sub.add_parser("robot", help="Show robot position (CleaningRobot-Map)")
    sub.add_parser("summaries", help="Show cleaning summaries (CleaningRobot-Map)")
    sub.add_parser(
        "smart-empty",
        help="Smart Emptying: is emptying the dust box justified for the current session? (AI layer)",
    )
    watch_parser = sub.add_parser(
        "watch",
        help="Smart Emptying (live): detect a false empty the moment the robot docks (AI layer)",
    )
    watch_parser.add_argument(
        "--interval", type=float, default=5.0, help="Polling interval in seconds (default 5)"
    )
    watch_parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Stop watching after N seconds if the robot never docks",
    )
    coverage_parser = sub.add_parser(
        "coverage",
        help="Coverage analysis + fake-cleaning detection from the map (AI layer)",
    )
    coverage_parser.add_argument(
        "--map-id", type=int, default=None, help="Map id (default: first map)"
    )
    coverage_parser.add_argument(
        "--collect",
        type=float,
        default=0,
        help="Collect the cleaning path live for N seconds first (run 'make start' in "
        "another terminal)",
    )
    coverage_parser.add_argument(
        "--interval", type=float, default=3.0, help="Sampling interval for --collect"
    )
    coverage_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full raw report as JSON instead of the human summary",
    )
    coverage_parser.add_argument(
        "--ai",
        action="store_true",
        help="Also explain the report in natural language with the LLM (AI layer)",
    )
    obs_parser = sub.add_parser(
        "obstacles",
        help="Obstacle-loop detection (AI layer); --auto recovers the robot",
    )
    obs_parser.add_argument(
        "--map-id", type=int, default=None, help="Map id (default: first map)"
    )
    obs_parser.add_argument(
        "--collect",
        type=float,
        default=0,
        help="Collect the cleaning path live for N seconds first (run 'make start' in "
        "another terminal)",
    )
    obs_parser.add_argument(
        "--interval", type=float, default=3.0, help="Sampling interval for --collect"
    )
    obs_parser.add_argument(
        "--auto",
        action="store_true",
        help="If a stuck-at-obstacle is detected, execute recovery on the real device "
        "(stop -> GoHome -> wait docked -> restart cleaning)",
    )
    obs_parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt when using --auto",
    )

    args = parser.parse_args()
    handler = {
        "login": cmd_login,
        "appliances": cmd_appliances,
        "status": cmd_status,
        "programs": cmd_programs,
        "start": cmd_start,
        "stop": cmd_stop,
        "resume": cmd_resume,
        "dock": cmd_dock,
        "chat": cmd_chat,
        "settings": cmd_settings,
        "maps": cmd_maps,
        "mapinfo": cmd_mapinfo,
        "robot": cmd_robot,
        "summaries": cmd_summaries,
        "smart-empty": cmd_smart_empty,
        "watch": cmd_watch,
        "coverage": cmd_coverage,
        "obstacles": cmd_obstacles,
    }[args.command]
    handler(args)


if __name__ == "__main__":
    main()
