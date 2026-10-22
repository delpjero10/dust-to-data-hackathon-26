"""Smart dust-box emptying for the BCRD2W.

Observed bug (see docs/ai-features.md): the docking station empties the dust box on
every return to base, even when the robot barely cleaned. The Home Connect API for
this device only exposes PauseProgram/ResumeProgram/AcknowledgeEvent commands — there
is no direct "empty" trigger — so this module implements the AI-layer decision:

* an empty is only justified when the cleaning session actually ran long enough
  (default threshold 2 minutes = 120 s, configurable via AI_MIN_CLEAN_SECONDS);
* `EmptyMonitor` is the real-time, demo-able part: it watches the status stream and,
  whenever the robot returns to base (docks) after a cleaning session, flags whether
  the dock-triggered empty was justified or a "false empty".
* it is ready to gate a real empty command once/if the API exposes one.

Timing: the API has no reliable wall clock on the robot, so `EmptyMonitor` measures
the session with local wall-clock time (from OperationState=Run until the robot
docks/charges). Good enough for the demo; `smart-empty` uses the device-reported
`BSH.Common.Option.ElapsedProgramTime` when a program is active.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

from ..config import load_env
from ..home_connect.client import HomeConnectClient

ELAPSED_OPTION_KEY = "BSH.Common.Option.ElapsedProgramTime"
DEFAULT_MIN_CLEAN_SECONDS = 120

OPERATION_READY = "BSH.Common.EnumType.OperationState.Ready"
OPERATION_RUN = "BSH.Common.EnumType.OperationState.Run"
CHARGING = "BSH.Common.EnumType.BatteryChargingState.Charging"


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


@dataclass
class EmptyEvent:
    """Result of detecting the robot docking after a cleaning session.

    The docking station empties the dust box on every return to base, so this event
    classifies that empty: justified (long cleaning) or a FALSE EMPTY (too short).
    """

    cleaning_seconds: float
    empty_justified: bool
    min_clean_seconds: int
    reason: str


class EmptyMonitor:
    """State machine that flags dock-triggered "false empties" from a status stream.

    Feed it one status snapshot at a time (list of `{"key": ..., "value": ...}`). It
    remembers when a cleaning session starts (`OperationState` -> Run) and, when the
    robot docks (`OperationState` Ready + charging), it emits an `EmptyEvent` with the
    wall-clock cleaning duration. Pure/thread-safe: no I/O, easy to unit-test.
    """

    def __init__(self, min_seconds: int | None = None):
        self.min_seconds = (
            get_min_clean_seconds() if min_seconds is None else max(0, min_seconds)
        )
        self._session_started_at: float | None = None

    @staticmethod
    def _values(status_items: list[dict]) -> dict:
        return {item.get("key"): item.get("value") for item in status_items}

    @property
    def session_active(self) -> bool:
        return self._session_started_at is not None

    def on_status(
        self,
        status_items: list[dict],
        now: float | None = None,
    ) -> EmptyEvent | None:
        """Process one status snapshot; returns an EmptyEvent when the robot docks."""
        now = time.time() if now is None else now
        values = self._values(status_items)
        operation = values.get("BSH.Common.Status.OperationState")
        charging = values.get("BSH.Common.Status.BatteryChargingState")

        if operation == OPERATION_RUN and self._session_started_at is None:
            self._session_started_at = now
            return None

        if (
            operation == OPERATION_READY
            and charging == CHARGING
            and self._session_started_at is not None
        ):
            cleaning_seconds = now - self._session_started_at
            self._session_started_at = None
            justified = cleaning_seconds >= self.min_seconds
            if justified:
                reason = (
                    f"Robot docked after cleaning for {_format_duration(cleaning_seconds)} "
                    "- emptying the dust box is justified."
                )
            else:
                reason = (
                    f"Robot docked after only {_format_duration(cleaning_seconds)} of "
                    f"cleaning - FALSE EMPTY: the station emptied although that was "
                    f"unnecessary (min {_format_duration(self.min_seconds)} required)."
                )
            return EmptyEvent(
                cleaning_seconds=cleaning_seconds,
                empty_justified=justified,
                min_clean_seconds=self.min_seconds,
                reason=reason,
            )
        return None


def watch(
    client: HomeConnectClient,
    ha_id: str,
    interval: float = 5.0,
    timeout: float | None = None,
    on_event=None,
) -> EmptyEvent | None:
    """Poll status and flag a false empty the moment the robot docks after cleaning.

    Prints live updates; `on_event` (callable) is invoked with the EmptyEvent before
    returning it (used by the CLI to also print structured JSON). Returns None on
    timeout or if stopped before the robot ever docked.
    """
    monitor = EmptyMonitor()
    print("Watching for a false empty: waiting for the robot to start cleaning...")
    started_at = time.time()
    while True:
        if timeout is not None and time.time() - started_at > timeout:
            print(
                f"Timeout: the robot never docked within {_format_duration(timeout)}. "
                "Nothing to report."
            )
            return None

        try:
            status_items = client.get_status(ha_id)
        except Exception as exc:  # noqa: BLE001 - keep watching through API hiccups
            print(f"(status fetch failed, retrying: {exc})")
            time.sleep(interval)
            continue

        if monitor.session_active:
            print(
                f"Cleaning in progress... {_format_duration(time.time() - monitor._session_started_at)}"
                f" (min {_format_duration(monitor.min_seconds)})"
            )

        event = monitor.on_status(status_items)
        if event is not None:
            if on_event:
                on_event(event)
            return event

        if monitor.session_active is False:
            print("Waiting for the robot to leave the dock / start cleaning...")

        time.sleep(interval)
