"""Live device logger (AI layer): turn the polled status stream into a readable log.

`make watch` used to watch only for dock-triggered (false) empties. Now it logs the
whole device lifecycle in plain language - operation-state transitions, docking,
charging and battery changes - as they happen, and it still flags "false empty"
events when the robot docks after a cleaning session (the Smart Emptying policy, see
`src/ai/smart_empty.py`).

Pure state machine: feed it one status snapshot (list of `{"key": ..., "value": ...}`)
and it returns the log lines for whatever changed since the last snapshot.
"""

from __future__ import annotations

import time

from . import smart_empty

KEY_OPERATION = "BSH.Common.Status.OperationState"
KEY_CHARGING = "BSH.Common.Status.BatteryChargingState"
KEY_BATTERY = "BSH.Common.Status.BatteryLevel"

OPERATION_READY = "BSH.Common.EnumType.OperationState.Ready"
CHARGING = "BSH.Common.EnumType.BatteryChargingState.Charging"

FRIENDLY_OPERATION = {
    "BSH.Common.EnumType.OperationState.Inactive": "inactive",
    "BSH.Common.EnumType.OperationState.Ready": "ready/idle",
    "BSH.Common.EnumType.OperationState.DelayedStart": "delayed start scheduled",
    "BSH.Common.EnumType.OperationState.Run": "cleaning",
    "BSH.Common.EnumType.OperationState.Pause": "paused",
    "BSH.Common.EnumType.OperationState.ActionRequired": "action required",
    "BSH.Common.EnumType.OperationState.Finished": "finished",
    "BSH.Common.EnumType.OperationState.Error": "error",
    "BSH.Common.EnumType.OperationState.Aborting": "aborting",
}


def timestamp() -> str:
    return time.strftime("%H:%M:%S")


class LiveLogger:
    """Diff-based logger: prints a line only when a status value actually changes."""

    def __init__(self):
        self._last: dict[str, object] = {}
        self._docked: bool | None = None
        self._monitor = smart_empty.EmptyMonitor()
        self.last_event: smart_empty.EmptyEvent | None = None

    def on_status(self, status_items: list[dict]):
        """Process one status snapshot; returns (log_lines, smart_empty_event)."""
        values = {item.get("key"): item.get("value") for item in status_items}
        first = not self._last
        lines: list[str] = []

        op = values.get(KEY_OPERATION)
        charging = values.get(KEY_CHARGING)
        battery = values.get(KEY_BATTERY)

        if first:
            bits = [FRIENDLY_OPERATION.get(op, op or "?") if op else "state unknown"]
            if charging:
                bits.append("charging" if charging == CHARGING else "on battery")
            if battery is not None:
                bits.append(f"battery {battery}%")
            lines.append("current state: " + ", ".join(bits))
            self._docked = bool(op == OPERATION_READY and charging == CHARGING)
        else:
            docked = bool(op == OPERATION_READY and charging == CHARGING)
            if docked != self._docked:
                lines.append("robot docked (charging)" if docked else "robot left the dock")
                self._docked = docked
            elif charging != self._last.get(KEY_CHARGING):
                lines.append("charging" if charging == CHARGING else "on battery (not charging)")
            if op != self._last.get(KEY_OPERATION):
                lines.append(f"state: {FRIENDLY_OPERATION.get(op, op or '?')}")
            if battery is not None and battery != self._last.get(KEY_BATTERY):
                lines.append(f"battery {battery}%")
            for key, value in values.items():
                if key in (KEY_OPERATION, KEY_CHARGING, KEY_BATTERY):
                    continue
                if value != self._last.get(key):
                    lines.append(f"{key.rsplit('.', 1)[-1]}: {value}")

        self.last_event = self._monitor.on_status(status_items)
        if self.last_event is not None:
            lines.append(self.last_event.reason)

        self._last = values
        return lines, self.last_event
