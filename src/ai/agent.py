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
from ..home_connect.client import HomeConnectClient

SYSTEM_PROMPT = """You are the AI assistant for a Bosch Spotless BCRD2W robot vacuum.

You receive the device status and a user request. Decide the ACTION to take and reply
with ONLY a JSON object:

{"action": "start" | "stop" | "status" | "answer", "cleaning_type": "Auto", "reply": "what you tell the user"}

Rules:
- action "start": user asked to start/begin/run cleaning. cleaning_type is one of
  Auto, CleanSpot, CleanTurbo, CleanRoom, CleanZone (default Auto).
- action "stop": user asked to stop/pause/end cleaning.
- action "status": user asked about the device state.
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
            clean_type = decision.get("cleaning_type", "Auto")
            options = [{"key": "RobotCleaner.Option.CleanType", "value": clean_type}]
            self.client.start_program(ha_id, "BSH.Common.Root.SelectedProgram", options)
            return reply or f"Started cleaning ({clean_type})."
        if action == "stop":
            self.client.stop_program(ha_id)
            return reply or "Stopped cleaning."
        if action == "status":
            return reply or f"Device status:\n{status}"
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
