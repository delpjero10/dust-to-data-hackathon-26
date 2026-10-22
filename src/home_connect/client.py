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

# The BCRD2W only exposes this program (no CleanType options) — confirmed against the
# real device via GET .../programs/available. `BSH.Common.Root.SelectedProgram` is
# REJECTED with 409 SDK.Error.UnsupportedProgram, so always start with this key.
ROBOT_CLEAN_ALL_PROGRAM = "ConsumerProducts.CleaningRobot.Program.Cleaning.CleanAll"

# "Return to base" program. Only listed by /programs/available while the robot is off
# the dock (after cleaning/stops). Starting it sends the robot back to charge — and is
# exactly the moment the station runs the (often unjustified) dust-box empty.
ROBOT_GO_HOME_PROGRAM = "ConsumerProducts.CleaningRobot.Program.Basic.GoHome"


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

        On the BCRD2W, `key` must be `ROBOT_CLEAN_ALL_PROGRAM` (the device rejects
        `BSH.Common.Root.SelectedProgram` and accepts no options). Confirm valid keys
        from `/programs/available` before sending.
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

    # -- settings (CleaningRobot-Settings) -----------------------------------
    def get_settings(self, ha_id: str) -> list[dict]:
        """GET /homeappliances/{haId}/settings — all settings."""
        resp = self._request("GET", f"/homeappliances/{ha_id}/settings")
        return resp.json().get("data", {}).get("settings", [])

    def get_setting(self, ha_id: str, key: str) -> dict | None:
        """GET /homeappliances/{haId}/settings/{key} — a specific setting."""
        resp = self._request("GET", f"/homeappliances/{ha_id}/settings/{key}")
        return resp.json().get("data")

    def set_setting(self, ha_id: str, key: str, value) -> None:
        """PUT /homeappliances/{haId}/settings/{key} — set a specific setting.

        Confirm the setting key is writable (constraints.access == "readWrite")
        before sending, and verify allowed values for enums.
        """
        body = {"data": {"key": key, "value": value}}
        self._request("PUT", f"/homeappliances/{ha_id}/settings/{key}", json=body)

    # -- map (CleaningRobot-Map) ---------------------------------------------
    def get_maps(self, ha_id: str) -> list[dict]:
        """GET /homeappliances/{haId}/map/maps — all maps of the cleaning robot."""
        resp = self._request("GET", f"/homeappliances/{ha_id}/map/maps")
        return resp.json().get("data", {}).get("maps", [])

    def get_map(self, ha_id: str, map_id: str) -> dict | None:
        """GET /homeappliances/{haId}/map/maps/{mapId} — basic data of a map."""
        resp = self._request("GET", f"/homeappliances/{ha_id}/map/maps/{map_id}")
        return resp.json().get("data")

    def get_map_occupancy_grid(self, ha_id: str, map_id: str):
        """GET .../map/maps/{mapId}/occupancyGrid — grid-based raw layout."""
        resp = self._request(
            "GET", f"/homeappliances/{ha_id}/map/maps/{map_id}/occupancyGrid"
        )
        return resp.json().get("data")

    def get_map_layout(self, ha_id: str, map_id: str):
        """GET .../map/maps/{mapId}/layout — vector layout (walls and doors)."""
        resp = self._request(
            "GET", f"/homeappliances/{ha_id}/map/maps/{map_id}/layout"
        )
        return resp.json().get("data")

    def get_map_cleaning_status(self, ha_id: str, map_id: str):
        """GET .../map/maps/{mapId}/cleaningStatus — cleaning status of a map."""
        resp = self._request(
            "GET", f"/homeappliances/{ha_id}/map/maps/{map_id}/cleaningStatus"
        )
        return resp.json().get("data")

    def get_map_detected_objects(self, ha_id: str, map_id: str) -> list[dict]:
        """GET .../map/maps/{mapId}/cleaningStatus/objects — detected objects."""
        resp = self._request(
            "GET", f"/homeappliances/{ha_id}/map/maps/{map_id}/cleaningStatus/objects"
        )
        return resp.json().get("data", {}).get("objects", [])

    def get_map_detected_object(self, ha_id: str, map_id: str, object_id: str):
        """GET .../map/maps/{mapId}/cleaningStatus/objects/{objectId}."""
        resp = self._request(
            "GET",
            f"/homeappliances/{ha_id}/map/maps/{map_id}/cleaningStatus/objects/{object_id}",
        )
        return resp.json().get("data")

    def get_map_rooms(self, ha_id: str, map_id: str) -> list[dict]:
        """GET .../map/maps/{mapId}/rooms — rooms defined on the map."""
        resp = self._request(
            "GET", f"/homeappliances/{ha_id}/map/maps/{map_id}/rooms"
        )
        return resp.json().get("data", {}).get("rooms", [])

    def get_map_room(self, ha_id: str, map_id: str, room_id: str):
        """GET .../map/maps/{mapId}/rooms/{roomId} — a specific room."""
        resp = self._request(
            "GET", f"/homeappliances/{ha_id}/map/maps/{map_id}/rooms/{room_id}"
        )
        return resp.json().get("data")

    def get_map_zones(self, ha_id: str, map_id: str) -> list[dict]:
        """GET .../map/maps/{mapId}/zones — zones defined on the map."""
        resp = self._request(
            "GET", f"/homeappliances/{ha_id}/map/maps/{map_id}/zones"
        )
        return resp.json().get("data", {}).get("zones", [])

    def get_map_zone(self, ha_id: str, map_id: str, zone_id: str):
        """GET .../map/maps/{mapId}/zones/{zoneId} — a specific zone."""
        resp = self._request(
            "GET", f"/homeappliances/{ha_id}/map/maps/{map_id}/zones/{zone_id}"
        )
        return resp.json().get("data")

    def get_robot_position(self, ha_id: str):
        """GET /homeappliances/{haId}/map/robot/position — current robot position."""
        resp = self._request("GET", f"/homeappliances/{ha_id}/map/robot/position")
        return resp.json().get("data")

    def get_map_config_restrictions(self, ha_id: str):
        """GET /homeappliances/{haId}/map/config/restrictions — map config restrictions."""
        resp = self._request("GET", f"/homeappliances/{ha_id}/map/config/restrictions")
        return resp.json().get("data")

    def get_cleaning_summaries(self, ha_id: str) -> list[dict]:
        """GET /homeappliances/{haId}/map/cleaningSummary — all cleaning summaries."""
        resp = self._request("GET", f"/homeappliances/{ha_id}/map/cleaningSummary")
        return resp.json().get("data", {}).get("cleaningSummaries", [])

    def get_cleaning_summary(self, ha_id: str, counter: str):
        """GET /homeappliances/{haId}/map/cleaningSummary/{counter}."""
        resp = self._request(
            "GET", f"/homeappliances/{ha_id}/map/cleaningSummary/{counter}"
        )
        return resp.json().get("data")
