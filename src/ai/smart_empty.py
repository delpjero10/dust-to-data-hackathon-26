"""Smart dust-box emptying policy for the BCRD2W.

Observed bug (see docs/ai-features.md): the docking station empties the dust box on
every return to base, even when the robot barely cleaned. The Home Connect API for
this device only exposes PauseProgram/ResumeProgram/AcknowledgeEvent commands — there
is no direct "empty" trigger — so this module implements the AI-layer decision:

* an empty is only justified when the cleaning session actually ran long enough
  (default threshold 2 minutes = 120 s, configurable via AI_MIN_CLEAN_SECONDS);
* it flags "false empties" (robot emptied although cleaning was too short) and is
  ready to gate a real empty command once/if the API exposes one.

Policy uses `BSH.Common.Option.ElapsedProgramTime` reported by the active program.
"""

from __future__ import annotations

import os

from ..config import load_env
from ..home_connect.client import HomeConnectClient

ELAPSED_OPTION_KEY = "BSH.Common.Option.ElapsedProgramTime"
DEFAULT_MIN_CLEAN_SECONDS = 120


def get_min_clean_seconds() -> int:
    """The shortest cleaning session that justifies an empty (seconds)."""
    load_env()
    raw = os.environ.get("AI_MIN_CLEAN_SECONDS", str(DEFAULT_MIN_CLEAN_SECONDS))
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_MIN_CLEAN_SECONDS


def parse_elapsed_seconds(active_program: dict | None) -> int | None:
    """Extract the elapsed program time (seconds) from an active program object."""
    if not active_program:
        return None
    for option in active_program.get("options") or []:
        if option.get("key") == ELAPSED_OPTION_KEY:
            try:
                return int(option.get("value"))
            except (TypeError, ValueError):
                return None
    return None


def should_empty(cleaning_seconds: int | None, min_seconds: int | None = None) -> bool:
    """An empty is justified only if the robot actually cleaned long enough."""
    threshold = get_min_clean_seconds() if min_seconds is None else max(0, min_seconds)
    if cleaning_seconds is None:
        return False
    return cleaning_seconds >= threshold


def get_cleaning_duration(client: HomeConnectClient, ha_id: str) -> int | None:
    """Current elapsed cleaning time in seconds (None if no program is active)."""
    return parse_elapsed_seconds(client.get_active_program(ha_id))


def empty_verdict(cleaning_seconds: int | None, min_seconds: int | None = None) -> dict:
    """Decide whether emptying the dust box is justified for a cleaning session."""
    threshold = get_min_clean_seconds() if min_seconds is None else max(0, min_seconds)
    needed = should_empty(cleaning_seconds, threshold)

    if cleaning_seconds is None:
        reason = (
            "No active cleaning session - the robot is not cleaning (e.g. it is docked "
            "or idle), so emptying the dust box is unnecessary."
        )
    elif needed:
        reason = (
            f"Robot cleaned for {_format_duration(cleaning_seconds)} - emptying the "
            "dust box is justified."
        )
    else:
        reason = (
            f"Robot cleaned for only {_format_duration(cleaning_seconds)} - emptying "
            "the dust box was unnecessary (false empty)."
        )

    return {
        "empty_needed": needed,
        "cleaning_seconds": cleaning_seconds,
        "min_clean_seconds": threshold,
        "reason": reason,
    }


def _format_duration(seconds: int) -> str:
    minutes, secs = divmod(int(seconds), 60)
    if minutes:
        return f"{minutes} min {secs} s"
    return f"{secs} s"
