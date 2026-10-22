"""Shared config helpers (minimal .env loading, no external dependency)."""

from __future__ import annotations

import os

from . import ROOT_DIR  # noqa: F401 - re-export for convenience


def load_env(path: str | None = None) -> None:
    """Load KEY=VALUE lines from a .env file into os.environ (existing vars win)."""
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
