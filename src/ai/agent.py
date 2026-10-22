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
from ..home_connect.client import ROBOT_CLEAN_ALL_PROGRAM, HomeConnectClient

SYSTEM_PROMPT = """You are the AI assistant for a Bosch Spotless BCRD2W robot vacuum.

You receive the device status and a user request. Decide the ACTION to take and reply
with ONLY a JSON object:

{"action": "start" | "stop" | "status" | "empty" | "answer", "reply": "what you tell the user"}

Rules:
- action "start": user asked to start/begin/run cleaning. NOTE: this device only
  supports full cleaning (CleanAll) - there are no spot/room/zone types.
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
            self.client.start_program(ha_id, ROBOT_CLEAN_ALL_PROGRAM)
            return reply or "Started cleaning."
        if action == "stop":
            self.client.stop_program(ha_id)
            return reply or "Stopped cleaning."
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
