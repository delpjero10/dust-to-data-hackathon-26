"""OAuth2 authorization-code flow helpers for the Home Connect API.

Home Connect uses the OAuth2 authorization code grant (RFC 6749). The user logs in
through the Home Connect web page, which redirects to a redirect URI carrying the
authorization code. We exchange that code for tokens at the token endpoint.

All URLs below are taken from `hcsdk-production.yaml` (securityDefinitions ->
`homeconnect_auth`).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse, parse_qs

import requests

AUTHORIZATION_URL = "https://api.home-connect.com/security/oauth/authorize"
TOKEN_URL = "https://api.home-connect.com/security/oauth/token"
REVOKE_URL = "https://api.home-connect.com/security/oauth/revoke"

DEFAULT_REDIRECT_URI = "https://apiclient.home-connect.com/o2c.html"

# Scopes required to read + control a cleaning robot (incl. map endpoints). See the
# `homeconnect_auth` scopes in hcsdk-production.yaml.
DEFAULT_SCOPES = " ".join(
    [
        "IdentifyAppliance",
        "CleaningRobot",
        "CleaningRobot-Control",
        "CleaningRobot-Monitor",
        "CleaningRobot-Settings",
        "CleaningRobot-Map",
    ]
)


@dataclass
class Token:
    """A Home Connect access/refresh token pair."""

    access_token: str
    refresh_token: str | None = None
    expires_in: int = 3600
    token_type: str = "Bearer"

    @classmethod
    def from_dict(cls, data: dict) -> "Token":
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in", 3600),
            token_type=data.get("token_type", "Bearer"),
        )


class TokenStore:
    """Persists tokens to a JSON file so you don't have to log in every time."""

    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(
            os.path.dirname(__file__), "..", "..", ".token.json"
        )

    def load(self) -> Token | None:
        if not os.path.exists(self.path):
            return None
        with open(self.path, "r", encoding="utf-8") as fh:
            return Token.from_dict(json.load(fh))

    def save(self, token: Token) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "access_token": token.access_token,
                    "refresh_token": token.refresh_token,
                    "expires_in": token.expires_in,
                    "token_type": token.token_type,
                },
                fh,
                indent=2,
            )

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)


def build_authorization_url(
    client_id: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scope: str = DEFAULT_SCOPES,
) -> str:
    """Build the URL to open in a browser to authorize the app."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
    }
    return f"{AUTHORIZATION_URL}?{urlencode(params)}"


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> Token:
    """Exchange an authorization code for an access token."""
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return Token.from_dict(resp.json())


def extract_code_from_url(url: str) -> str:
    """Extract the `code` query parameter from the redirect URL."""
    parsed = parse_qs(urlparse(url).query)
    return parsed["code"][0]


def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token_code: str,
) -> Token:
    """Exchange a refresh token for a fresh access token."""
    resp = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token_code,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    resp.raise_for_status()
    return Token.from_dict(resp.json())
