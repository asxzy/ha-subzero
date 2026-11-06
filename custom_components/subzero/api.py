"""Client for the Sub-Zero Group cloud appliance API."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import aiohttp

from .auth import AuthError, SubZeroAuth, Tokens
from .const import (
    API_BASE,
    CMD_GET,
    CMD_OPEN_CHANNEL,
    CMD_RESET_AIR_FILTER,
    CMD_SET,
    SUBSCRIPTION_KEY,
)

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 30


class SubZeroApiError(Exception):
    """The cloud API could not complete a request."""


class SubZeroConnectionError(SubZeroApiError):
    """The cloud API is unreachable."""


class SubZeroAuthError(SubZeroApiError):
    """The account is no longer authorised."""


class SubZeroCommandError(SubZeroApiError):
    """An appliance rejected a command."""


class Appliance:
    """An appliance registered to the account."""

    __slots__ = ("device_id", "name", "appliance_type", "temperature_unit")

    def __init__(
        self,
        device_id: str,
        name: str,
        appliance_type: str,
        temperature_unit: str | None,
    ) -> None:
        """Initialize the appliance record."""
        self.device_id = device_id
        self.name = name
        self.appliance_type = appliance_type
        self.temperature_unit = temperature_unit

    @property
    def type_parts(self) -> tuple[int, int, int] | None:
        """Return the (series, category, version) tuple for this appliance."""
        parts = self.appliance_type.split(".")
        if len(parts) != 3:
            return None
        try:
            return int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None


class SubZeroClient:
    """Talk to the appliance API using an account's tokens."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        auth: SubZeroAuth,
        tokens: Tokens,
        token_callback: Any = None,
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._auth = auth
        self._tokens = tokens
        self._token_callback = token_callback
        self._refresh_lock = asyncio.Lock()

    @property
    def user_id(self) -> str:
        """Return the account identifier used by the API."""
        return self._tokens.user_id

    @property
    def tokens(self) -> Tokens:
        """Return the current token bundle."""
        return self._tokens

    async def async_refresh_tokens(self) -> None:
        """Renew the access token if it is close to expiry."""
        async with self._refresh_lock:
            if not self._tokens.expired:
                return
            try:
                tokens = await self._auth.refresh(self._tokens.refresh_token)
            except AuthError as err:
                raise SubZeroAuthError(str(err)) from err
            if tokens.user_id != self._tokens.user_id:
                raise SubZeroAuthError(
                    "Sub-Zero refreshed a different account."
                )
            self._tokens = tokens
            if self._token_callback is not None:
                await self._token_callback(tokens)

    def _headers(self) -> dict[str, str]:
        """Build request headers for the appliance API."""
        return {
            "Authorization": f"Bearer {self._tokens.access_token}",
            "Ocp-Apim-Subscription-Key": SUBSCRIPTION_KEY,
            "Userid": self._tokens.user_id,
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        retry_on_auth: bool = True,
    ) -> Any:
        """Perform an authenticated API request."""
        await self.async_refresh_tokens()
        url = f"{API_BASE}{path}"
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers(),
                json=json_body,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                if response.status == 401 and retry_on_auth:
                    # The token may have been revoked early; force a renewal once.
                    self._tokens.expires_at = self._tokens.expires_at.replace(
                        year=1970
                    )
                    await self.async_refresh_tokens()
                    return await self._request(
                        method, path, json_body=json_body, retry_on_auth=False
                    )
                body = await response.text()
                if response.status >= 400:
                    raise SubZeroApiError(
                        f"Sub-Zero returned HTTP {response.status} for {path}: "
                        f"{body[:200]}"
                    )
        except asyncio.TimeoutError as err:
            raise SubZeroConnectionError(
                "Sub-Zero's cloud did not respond in time."
            ) from err
        except aiohttp.ClientError as err:
            raise SubZeroConnectionError(
                f"Could not reach Sub-Zero's cloud: {err}"
            ) from err

        if not body:
            return None
        try:
            return await _json_or_text(body)
        except ValueError as err:
            raise SubZeroApiError("Sub-Zero returned an invalid response.") from err

    async def async_get_appliances(self) -> list[Appliance]:
        """Return every appliance registered to the account."""
        payload = await self._request("GET", "/consumerapp/user/devices")
        if not isinstance(payload, dict) or not isinstance(
            payload.get("devices"), list
        ):
            raise SubZeroApiError("Sub-Zero did not return an appliance list.")
        appliances: list[Appliance] = []
        for device in payload["devices"]:
            if not isinstance(device, dict) or not device.get("id"):
                continue
            appliances.append(
                Appliance(
                    device_id=device["id"],
                    name=device.get("name") or "Sub-Zero appliance",
                    appliance_type=str(device.get("applianceId") or ""),
                    temperature_unit=device.get("temperatureUnitForAppliance"),
                )
            )
        return appliances

    async def async_execute(
        self, device_id: str, command: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Run a direct-method command against an appliance."""
        payload: dict[str, Any] = {"cmd": command}
        if params is not None:
            payload["params"] = params
        body = {"req_id": str(uuid.uuid4()), "pload": payload}
        path = f"/consumerapp/device/{device_id}/directmethod/executeAPICmd"
        result = await self._request("POST", path, json_body=body)
        if not isinstance(result, dict):
            raise SubZeroApiError("Sub-Zero returned an invalid command response.")
        return result

    async def async_get_state(self, device_id: str) -> dict[str, Any]:
        """Return the current property snapshot for an appliance."""
        result = await self.async_execute(device_id, CMD_GET)
        snapshot = _unwrap(result)
        if not isinstance(snapshot.get("appliance_model"), str):
            raise SubZeroApiError(
                "The appliance did not return a status snapshot."
            )
        return snapshot

    async def async_open_channel(self, device_id: str) -> None:
        """Ask an appliance to start pushing state updates."""
        result = await self.async_execute(device_id, CMD_OPEN_CHANNEL)
        if _rejected(result):
            raise SubZeroCommandError(
                "The appliance rejected opening its update channel."
            )

    async def async_set_property(
        self, device_id: str, key: str, value: Any
    ) -> None:
        """Write a single property to an appliance."""
        result = await self.async_execute(device_id, CMD_SET, {key: value})
        if _rejected(result):
            raise SubZeroCommandError(
                f"The appliance rejected the {key} setting."
            )

    async def async_reset_air_filter(self, device_id: str) -> None:
        """Reset an appliance's air filter counter."""
        result = await self.async_execute(device_id, CMD_RESET_AIR_FILTER)
        if _rejected(result):
            raise SubZeroCommandError(
                "The appliance rejected the air filter reset."
            )

    async def async_get_faults(self, device_id: str) -> list[dict[str, Any]]:
        """Return the active fault list for an appliance."""
        payload = await self._request(
            "GET", f"/fault-notifications/v1/notifications/device/{device_id}"
        )
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("notifications"), list):
            return payload["notifications"]
        return []


async def _json_or_text(body: str) -> Any:
    """Decode a response body, tolerating non-JSON success payloads."""
    import json

    try:
        return json.loads(body)
    except ValueError:
        return {"unparsed": body}


def _unwrap(result: dict[str, Any]) -> dict[str, Any]:
    """Return the property dictionary from a direct-method response.

    The cloud answers a ``get`` either with the properties directly or wrapped in
    a ``resp`` object, depending on the appliance firmware.
    """
    resp = result.get("resp")
    if isinstance(resp, dict):
        return resp
    return result


def _rejected(result: dict[str, Any]) -> bool:
    """Return True when an appliance reported a command failure."""
    for candidate in (result, _unwrap(result)):
        if not isinstance(candidate, dict):
            continue
        status = candidate.get("status")
        if isinstance(status, int) and status >= 400:
            return True
    return False
