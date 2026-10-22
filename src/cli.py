"""CLI to control the Bosch Spotless BCRD2W (and any Home Connect device) from the laptop.

Examples:
    python -m src.cli login
    python -m src.cli appliances
    python -m src.cli status
    python -m src.cli start            # default: Auto cleaning
    python -m src.cli start --type CleanSpot
    python -m src.cli stop
"""

from __future__ import annotations

import argparse
import os
import sys

from .home_connect.auth import (
    DEFAULT_REDIRECT_URI,
    DEFAULT_SCOPES,
    TokenStore,
    build_authorization_url,
    exchange_code,
    extract_code_from_url,
)
from .home_connect.client import HomeConnectClient

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)


def load_env(path: str | None = None) -> None:
    """Minimal .env loader (no external dependency)."""
    env_path = path or os.path.join(ROOT_DIR, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


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
    options = [{"key": "RobotCleaner.Option.CleanType", "value": args.type}]
    client.start_program(ha_id, "BSH.Common.Root.SelectedProgram", options)
    print(f"Started cleaning (CleanType={args.type}) on {ha_id}.")


def cmd_stop(args: argparse.Namespace) -> None:
    client = build_client()
    ha_id = resolve_ha_id(client, args)
    client.stop_program(ha_id)
    print(f"Stopped the active program on {ha_id}.")


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
    start_parser = sub.add_parser("start", help="Start cleaning")
    start_parser.add_argument(
        "--type",
        default="Auto",
        help="Cleaning type (Auto, CleanSpot, CleanTurbo, CleanRoom, CleanZone...)",
    )
    sub.add_parser("stop", help="Stop the active program")

    args = parser.parse_args()
    handler = {
        "login": cmd_login,
        "appliances": cmd_appliances,
        "status": cmd_status,
        "programs": cmd_programs,
        "start": cmd_start,
        "stop": cmd_stop,
    }[args.command]
    handler(args)


if __name__ == "__main__":
    main()
