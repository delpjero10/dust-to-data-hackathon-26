"""Chat client for the Bosch on-prem model or Anthropic Claude.

The default provider is an OpenAI-compatible `/chat/completions` endpoint (the Bosch
on-prem model, served from vLLM). Set `AI_MODEL_PROVIDER=anthropic` to use Claude via
the Anthropic Messages API (`ANTHROPIC_API_KEY` from `.env`).

Configuration (env vars, see `.env.example`):
    AI_MODEL_PROVIDER   "openai" (default) or "anthropic"
    OpenAI-compatible:
        AI_BASE_URL  base URL of the OpenAI-compatible endpoint (defaults to the
                     Bosch on-prem endpoint configured in opencode)
        AI_API_KEY   bearer token for the endpoint
        AI_MODEL     model id (default: discretestack-stable)
    Anthropic (Claude):
        ANTHROPIC_API_KEY       API key for api.anthropic.com
        ANTHROPIC_WORKSPACE_ID  workspace id (required when the API key is not scoped
                                to a single workspace; sent as anthropic-workspace-id)
        AI_CLAUDE_BASE_URL      base URL (default https://api.anthropic.com)
        AI_CLAUDE_MODEL         model id (default: claude-sonnet-4-6)
"""

from __future__ import annotations

import os
import requests

from ..config import load_env

DEFAULT_BASE_URL = "https://ews-emea.api.bosch.com/it/application/emea-ds3326-endp01/v1"
DEFAULT_MODEL = "discretestack-stable"

# Anthropic (Claude) provider — used when AI_MODEL_PROVIDER=anthropic.
ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-4-6"
ANTHROPIC_VERSION = "2023-06-01"


class LLMError(Exception):
    """Raised when the LLM endpoint returns an error."""


class LLMClient:
    """Chat client for an OpenAI-compatible or the Anthropic (Claude) endpoint.

    Provider is selected with `AI_MODEL_PROVIDER`:
      - "openai"   (default)  -> OpenAI-compatible endpoint (Bosch on-prem vLLM)
      - "anthropic"            -> Anthropic Messages API (Claude)

    OpenAI-compatible config: AI_BASE_URL / AI_API_KEY / AI_MODEL
    Anthropic config:          ANTHROPIC_API_KEY (or AI_CLAUDE_API_KEY),
                               ANTHROPIC_WORKSPACE_ID (optional), AI_CLAUDE_BASE_URL,
                               AI_CLAUDE_MODEL
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ):
        load_env()
        self.provider = (provider or os.environ.get("AI_MODEL_PROVIDER") or "openai").lower()
        if self.provider == "anthropic":
            self.base_url = (
                base_url or os.environ.get("AI_CLAUDE_BASE_URL") or ANTHROPIC_BASE_URL
            ).rstrip("/")
            self.api_key = api_key or os.environ.get("AI_CLAUDE_API_KEY") or os.environ.get(
                "ANTHROPIC_API_KEY", ""
            )
            self.model = model or os.environ.get("AI_CLAUDE_MODEL", ANTHROPIC_DEFAULT_MODEL)
            self.workspace_id = os.environ.get("ANTHROPIC_WORKSPACE_ID") or os.environ.get(
                "AI_CLAUDE_WORKSPACE_ID", ""
            )
        else:
            self.base_url = (
                base_url or os.environ.get("AI_BASE_URL") or DEFAULT_BASE_URL
            ).rstrip("/")
            self.api_key = api_key or os.environ.get("AI_API_KEY", "")
            self.model = model or os.environ.get("AI_MODEL", DEFAULT_MODEL)
        if not self.api_key:
            raise LLMError(f"Missing API key for provider '{self.provider}'. Set it in the .env file.")

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat request and return the assistant message text."""
        if self.provider == "anthropic":
            return self._chat_anthropic(messages, temperature, max_tokens)
        return self._chat_openai(messages, temperature, max_tokens)

    def _chat_openai(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
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

    def _chat_anthropic(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
    ) -> str:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        conversation = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] != "system"
        ]
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": conversation,
        }
        if system:
            body["system"] = system
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        if self.workspace_id:
            headers["anthropic-workspace-id"] = self.workspace_id
        resp = requests.post(
            f"{self.base_url}/v1/messages",
            headers=headers,
            json=body,
            timeout=90,
        )
        if resp.status_code != 200:
            raise LLMError(f"Anthropic endpoint -> {resp.status_code}: {resp.text[:500]}")
        data = resp.json()
        parts = [
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ]
        text = "".join(parts)
        if not text:
            raise LLMError(f"Unexpected Anthropic response: {data}")
        return text
