"""Data coordinator for the Sub-Zero Group integration."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import Appliance, SubZeroAuthError, SubZeroClient
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .push import SubZeroPush

_LOGGER = logging.getLogger(__name__)

# IoT Hub answers this code when an appliance has no live connection.
OFFLINE_ERROR_CODE = 404103

# Appliances answer one request at a time, so keep the fan-out modest.
MAX_CONCURRENT_REQUESTS = 3


@dataclass(slots=True)
class ApplianceState:
    """The last known state of one appliance."""

    appliance: Appliance
    properties: dict[str, Any] = field(default_factory=dict)
    online: bool = True

    @property
    def device_id(self) -> str:
        """Return the cloud device identifier."""
        return self.appliance.device_id


@dataclass(slots=True)
class SubZeroData:
    """Coordinator payload for the whole account."""

    appliances: dict[str, ApplianceState]

    def get(self, device_id: str) -> ApplianceState | None:
        """Return the state for one appliance."""
        return self.appliances.get(device_id)


class SubZeroCoordinator(DataUpdateCoordinator[SubZeroData]):
    """Poll every appliance on the account."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SubZeroClient,
        appliances: list[Appliance],
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.appliances = {appliance.device_id: appliance for appliance in appliances}
        self.push: SubZeroPush | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )

    def start_push(self) -> None:
        """Stream appliance updates instead of relying on polling alone."""
        if self.push is not None:
            return
        self.push = SubZeroPush(
            self.client,
            list(self.appliances),
            on_snapshot=self._push_snapshot,
            on_delta=self._push_delta,
        )
        # A config entry background task is cancelled automatically on unload.
        self.config_entry.async_create_background_task(
            self.hass,
            self.push.run(),
            f"{DOMAIN} push",
            eager_start=True,
        )

    async def stop_push(self) -> None:
        """Close the push connection."""
        if self.push is not None:
            await self.push.stop()
            self.push = None
    def _push_snapshot(self, device_id: str, properties: dict[str, Any]) -> None:
        """Replace an appliance's snapshot from a pushed full state."""
        state = self.data.get(device_id) if self.data else None
        if state is None:
            return
        state.properties = properties
        state.online = True
        self.async_update_listeners()

    def _push_delta(self, device_id: str, properties: dict[str, Any]) -> None:
        """Merge a pushed change set into the cached snapshot."""
        state = self.data.get(device_id) if self.data else None
        if state is None:
            return
        state.properties.update(properties)
        state.online = True
        self.async_update_listeners()

    async def _async_update_data(self) -> SubZeroData:
        """Fetch the state of every appliance."""
        states: dict[str, ApplianceState] = {}
        try:
            results = await asyncio.gather(
                *(self._fetch(device_id) for device_id in self.appliances),
                return_exceptions=True,
            )
        except SubZeroAuthError as err:
            raise UpdateFailed(str(err)) from err

        device_ids = list(self.appliances)
        for device_id, result in zip(device_ids, results, strict=True):
            appliance = self.appliances[device_id]
            if isinstance(result, BaseException):
                if _is_offline(result):
                    _LOGGER.debug("%s is offline: %s", appliance.name, result)
                    previous = self.data.get(device_id) if self.data else None
                    states[device_id] = ApplianceState(
                        appliance=appliance,
                        properties=previous.properties if previous else {},
                        online=False,
                    )
                    continue
                if isinstance(result, SubZeroAuthError):
                    raise UpdateFailed(str(result)) from result
                raise UpdateFailed(str(result)) from result
            states[device_id] = ApplianceState(
                appliance=appliance, properties=result, online=True
            )
        return SubZeroData(appliances=states)

    async def _fetch(self, device_id: str) -> dict[str, Any]:
        """Read one appliance snapshot."""
        return await self.client.async_get_state(device_id)

    async def async_set_property(
        self, device_id: str, key: str, value: Any
    ) -> None:
        """Write a property, then reflect it locally and refresh."""
        await self.client.async_set_property(device_id, key, value)
        await self._async_apply(device_id, {key: value})

    async def async_set_properties(
        self, device_id: str, properties: dict[str, Any]
    ) -> None:
        """Write several properties in one command."""
        await self.client.async_set_properties(device_id, properties)
        await self._async_apply(device_id, properties)

    async def _async_apply(
        self, device_id: str, properties: dict[str, Any]
    ) -> None:
        """Apply a confirmed write to the cached snapshot and refine it.

        The cloud accepts the command but the appliance takes a moment to report
        the new value, and ``async_request_refresh`` is debounced for ten
        seconds. Updating the cache first makes the entity reflect the change
        immediately; the refresh that follows reconciles it with the appliance.
        """
        state = self.data.get(device_id) if self.data else None
        if state is not None:
            state.properties.update(properties)
            self.async_update_listeners()
        await self.async_refresh()

    async def async_reset_air_filter(self, device_id: str) -> None:
        """Reset an appliance's air filter counter."""
        await self.client.async_reset_air_filter(device_id)
        await self.async_refresh()


def _is_offline(err: BaseException) -> bool:
    """Return True when an error means the appliance is unreachable."""
    text = str(err)
    return str(OFFLINE_ERROR_CODE) in text or "isn't online" in text
