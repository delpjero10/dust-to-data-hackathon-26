"""Minimal OpenAI-compatible chat client for the Bosch on-prem model.

The model is served from a vLLM endpoint that speaks the standard OpenAI
`/chat/completions` wire format, so a small `requests`-based client is enough —
no SDK dependency needed.

Configuration (env vars, see `.env.example`):
    AI_BASE_URL  base URL of the OpenAI-compatible endpoint (defaults to the
                 Bosch on-prem endpoint configured in opencode)
    AI_API_KEY   bearer token for the endpoint
    AI_MODEL     model id (default: discretestack-stable)
"""

from __future__ import annotations

import os
import requests

from ..config import load_env

DEFAULT_BASE_URL = "https://ews-emea.api.bosch.com/it/application/emea-ds3326-endp01/v1"
DEFAULT_MODEL = "discretestack-stable"


class LLMError(Exception):
    """Raised when the LLM endpoint returns an error."""


class LLMClient:
    """Chat completions client for an OpenAI-compatible endpoint."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        load_env()
        self.base_url = (base_url or os.environ.get("AI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = api_key or os.environ.get("AI_API_KEY", "")
        self.model = model or os.environ.get("AI_MODEL", DEFAULT_MODEL)
        if not self.api_key:
            raise LLMError("Missing AI_API_KEY. Set it in the .env file.")

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat request and return the assistant message text."""
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=90,
        )
        if resp.status_code != 200:
            raise LLMError(f"LLM endpoint -> {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            raise LLMError(f"Unexpected LLM response: {data}")
