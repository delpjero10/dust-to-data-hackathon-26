"""Thin HTTP client for the Home Connect API.

Endpoints and media types are taken from `hcsdk-production.yaml` in this repo.
Use that file as the source of truth when extending this client.
"""

from __future__ import annotations

import logging

import requests

from .auth import (
    Token,
    refresh_access_token,
)

log = logging.getLogger(__name__)

API_BASE = "https://api.home-connect.com/api"
MEDIA_TYPE = "application/vnd.bsh.sdk.v1+json"


class HomeConnectError(Exception):
    """Raised when the Home Connect API returns an error."""


class HomeConnectClient:
    """Automatically authenticates and refreshes tokens for API requests."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token: Token,
        refresh_callback=None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = token
        # Optional callable(token: Token) -> None to persist a refreshed token.
        self.refresh_callback = refresh_callback
        self._session = requests.Session()

    # -- low level -----------------------------------------------------------
    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{API_BASE}{path}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("Accept", MEDIA_TYPE)
        headers.setdefault("Content-Type", MEDIA_TYPE)
        resp = self._session.request(
            method,
            url,
            headers={"Authorization": f"Bearer {self.token.access_token}", **headers},
            timeout=30,
            **kwargs,
        )
        if resp.status_code == 401:
            self._try_refresh()
            headers["Authorization"] = f"Bearer {self.token.access_token}"
            resp = self._session.request(
                method, url, headers=headers, timeout=30, **kwargs
            )
        if resp.status_code >= 400:
            raise HomeConnectError(
                f"{method} {url} -> {resp.status_code}: {resp.text[:500]}"
            )
        return resp

    def _try_refresh(self) -> None:
        if not self.token.refresh_token:
            raise HomeConnectError(
                "Access token expired and no refresh token is available. "
                "Run the login command again."
            )
        new_token = refresh_access_token(
            self.client_id, self.client_secret, self.token.refresh_token
        )
        new_token.refresh_token = self.token.refresh_token
        self.token = new_token
        if self.refresh_callback:
            self.refresh_callback(new_token)
        log.info("Access token refreshed.")

    # -- appliances ----------------------------------------------------------
    def get_appliances(self) -> list[dict]:
        """GET /homeappliances — all appliances paired with the account."""
        resp = self._request("GET", "/homeappliances")
        return resp.json().get("data", {}).get("homeappliances", [])

    # -- programs ------------------------------------------------------------
    def get_available_programs(self, ha_id: str) -> list[dict]:
        """GET /homeappliances/{haId}/programs/available — programs currently available."""
        resp = self._request("GET", f"/homeappliances/{ha_id}/programs/available")
        return resp.json().get("data", {}).get("programs", [])

    def get_active_program(self, ha_id: str) -> dict | None:
        """GET /homeappliances/{haId}/programs/active — the running program (or None)."""
        try:
            resp = self._request("GET", f"/homeappliances/{ha_id}/programs/active")
        except HomeConnectError as exc:
            if "404" in str(exc):
                return None
            raise
        return resp.json().get("data")

    def start_program(
        self,
        ha_id: str,
        key: str,
        options: list[dict] | None = None,
    ) -> None:
        """PUT /homeappliances/{haId}/programs/active — start the given program.

        For a cleaning robot, `key` is usually `BSH.Common.Root.SelectedProgram`
        with an option `RobotCleaner.Option.CleanType` (e.g. value `Auto`).
        Confirm valid keys/options from `/programs/available` before sending.
        """
        body: dict = {"data": {"key": key}}
        if options:
            body["data"]["options"] = [
                {"key": o["key"], "value": o["value"]} for o in options
            ]
        self._request("PUT", f"/homeappliances/{ha_id}/programs/active", json=body)

    def stop_program(self, ha_id: str) -> None:
        """DELETE /homeappliances/{haId}/programs/active — stop the running program."""
        self._request("DELETE", f"/homeappliances/{ha_id}/programs/active")

    # -- status --------------------------------------------------------------
    def get_status(self, ha_id: str) -> list[dict]:
        """GET /homeappliances/{haId}/status — live status values."""
        resp = self._request("GET", f"/homeappliances/{ha_id}/status")
        return resp.json().get("data", {}).get("status", [])
