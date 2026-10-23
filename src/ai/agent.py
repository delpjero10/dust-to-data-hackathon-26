"""Vacuum agent: wires the LLM (Bosch on-prem model) to the Home Connect client.

The agent always has the current device status in context. It asks the model for a
structured decision (JSON) and then executes the action through HomeConnectClient —
the same commands the CLI already uses. The device/cloud wiring is unchanged; the AI
layer simply sits in the middle (see docs/architecture.md).
"""

from __future__ import annotations

import json
import re

from .llm import LLMClient
from . import smart_empty
from ..home_connect.client import (
    COMMAND_RESUME,
    ROBOT_CLEAN_ALL_PROGRAM,
    HomeConnectClient,
    HomeConnectError,
)

STATUS_OPERATION = "BSH.Common.Status.OperationState"
OPERATION_READY = "BSH.Common.EnumType.OperationState.Ready"
OPERATION_DELAYED_START = "BSH.Common.EnumType.OperationState.DelayedStart"
OPERATION_RUN = "BSH.Common.EnumType.OperationState.Run"
OPERATION_PAUSE = "BSH.Common.EnumType.OperationState.Pause"
OPERATION_FINISHED = "BSH.Common.EnumType.OperationState.Finished"
OPERATION_INACTIVE = "BSH.Common.EnumType.OperationState.Inactive"

SYSTEM_PROMPT = """You are the AI assistant for a Bosch Spotless BCRD2W robot vacuum.

You receive the device status and a user request. Decide the ACTION to take and reply
with ONLY a JSON object:

{"action": "start" | "stop" | "status" | "empty" | "answer", "reply": "what you tell the user"}

Rules:
- action "start": user asked to start/begin/run cleaning. NOTE: this device only
  supports full cleaning (CleanAll) - there are no spot/room/zone types. The agent
  handles the robot's state itself (it resumes if paused, and refuses if it cannot
  start), so just pick "start" whenever the user wants cleaning to run.
- action "stop": user asked to stop/pause/end cleaning.
- action "status": user asked about the device state.
- action "empty": user asked about the dust box / emptying / whether the robot cleaned
  enough to justify emptying. The agent will apply the Smart Emptying policy for you.
- action "answer": any other question — answer using only the provided status.
- reply must be a short, friendly message to the user.
Output ONLY the JSON. Do not add explanations."""


class VacuumAgent:
    """Turns natural-language requests into device actions."""

    def __init__(self, client: HomeConnectClient, llm: LLMClient | None = None):
        self.client = client
        self.llm = llm or LLMClient()

    def summarize_status(self, ha_id: str) -> str:
        """Build a compact, readable summary of the current status for the prompt."""
        try:
            items = self.client.get_status(ha_id)
        except Exception as exc:  # noqa: BLE001 - surface any API error to the user
            return f"(status unavailable: {exc})"
        parts = []
        for item in items:
            value = item.get("value")
            display = item.get("displayvalue")
            if display:
                value = f"{value} ({display})"
            parts.append(f"{item.get('key')}={value}")
        return "; ".join(parts) or "(empty)"

    def smart_empty_report(self, ha_id: str) -> str:
        """Apply the Smart Emptying policy and return a human-readable verdict.

        Tells the user whether emptying the dust box is justified based on how long the
        robot actually cleaned (default threshold 2 minutes).
        """
        seconds = smart_empty.get_cleaning_duration(self.client, ha_id)
        return smart_empty.empty_verdict(seconds)["reason"]

    # -- state-aware actions ------------------------------------------------

    def current_operation(self, ha_id: str) -> str | None:
        """The device's current `OperationState` value (or None if unreadable)."""
        try:
            for item in self.client.get_status(ha_id):
                if item.get("key") == STATUS_OPERATION:
                    return item.get("value")
        except HomeConnectError:
            return None
        return None

    def _friendly_error(self, what: str, exc: HomeConnectError, operation: str | None) -> str:
        """Translate a HomeConnect API error into a short, usable message.

        The BCRD2W rejects actions with 409 SDK.Error.WrongOperationState when the robot
        is not in a state that allows them (e.g. starting while it is off the dock,
        paused, or still finishing) - show a hint instead of a raw traceback.
        """
        detail = str(exc)
        if "WrongOperationState" in detail or "409" in detail:
            state = operation.rsplit(".", 1)[-1] if operation else "unknown"
            return (
                f"I could not {what}: the robot is in state {state!r}, which does not "
                "allow that action right now. For starting cleaning, make sure it is "
                "idle and docked, then try again."
            )
        return f"I could not {what}: {detail}"

    def _start_cleaning(self, ha_id: str, fallback_reply: str) -> str:
        """Start cleaning, adapting to the robot's current state (never crashes)."""
        operation = self.current_operation(ha_id)
        if operation == OPERATION_PAUSE:
            try:
                # Paused mid-cleaning: resume instead of restarting from scratch.
                self.client.execute_command(ha_id, COMMAND_RESUME)
            except HomeConnectError as exc:
                return self._friendly_error("resume cleaning", exc, operation)
            return "The robot was paused - I resumed cleaning."
        if operation in (OPERATION_RUN, OPERATION_DELAYED_START):
            return "The robot is already cleaning (or has a cleaning scheduled)."
        try:
            self.client.start_program(ha_id, ROBOT_CLEAN_ALL_PROGRAM)
        except HomeConnectError as exc:
            return self._friendly_error("start cleaning", exc, operation)
        return fallback_reply or "Started cleaning."

    def _stop_cleaning(self, ha_id: str, fallback_reply: str) -> str:
        """Stop cleaning, adapting to the robot's current state (never crashes)."""
        operation = self.current_operation(ha_id)
        if operation in (OPERATION_READY, OPERATION_FINISHED, OPERATION_INACTIVE, None):
            return "The robot is not cleaning - nothing to stop."
        try:
            self.client.stop_program(ha_id)
        except HomeConnectError as exc:
            return self._friendly_error("stop cleaning", exc, operation)
        return fallback_reply or "Stopped cleaning."

    def run(self, ha_id: str, user_message: str) -> str:
        """Process one natural-language request and return the assistant's reply."""
        status = self.summarize_status(ha_id)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Current device status:\n{status}\n\nUser request: {user_message}",
            },
        ]
        raw = self.llm.chat(messages)

        decision = self._parse_json(raw)
        if decision is None:
            # Model didn't return structured JSON - fall back to its raw text answer.
            return raw.strip() or "I could not understand the request."

        action = decision.get("action")
        reply = decision.get("reply") or ""
        if action == "start":
            # The BCRD2W only supports the CleanAll program with no options (see
            # ROBOT_CLEAN_ALL_PROGRAM in home_connect/client.py) - spot/room/zone
            # cleaning types are not available on this device.
            return self._start_cleaning(ha_id, reply)
        if action == "stop":
            return self._stop_cleaning(ha_id, reply)
        if action == "status":
            return reply or f"Device status:\n{status}"
        if action == "empty":
            verdict = self.smart_empty_report(ha_id)
            return f"{reply}\n{verdict}".strip() if reply else verdict
        return reply or f"Current device status:\n{status}"

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Extract a JSON object from the model output (robust to code fences)."""
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
            if not match:
                return None
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        return data if isinstance(data, dict) else None
