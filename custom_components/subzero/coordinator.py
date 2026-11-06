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

from .api import (
    Appliance,
    SubZeroApiError,
    SubZeroAuthError,
    SubZeroClient,
    SubZeroConnectionError,
)
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

# IoT Hub answers this code when an appliance has no live connection.
OFFLINE_ERROR_CODE = 404103


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
    ) -> None:
        """Initialize the coordinator."""
        self.client = client
        self.appliances = {appliance.device_id: appliance for appliance in appliances}
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> SubZeroData:
        """Fetch the state of every appliance."""
        states: dict[str, ApplianceState] = {}
        try:
            for device_id, appliance in self.appliances.items():
                previous = self.data.get(device_id) if self.data else None
                try:
                    properties = await self.client.async_get_state(device_id)
                except SubZeroApiError as err:
                    if _is_offline(err):
                        _LOGGER.debug(
                            "%s is offline: %s", appliance.name, err
                        )
                        states[device_id] = ApplianceState(
                            appliance=appliance,
                            properties=previous.properties if previous else {},
                            online=False,
                        )
                        continue
                    raise
                states[device_id] = ApplianceState(
                    appliance=appliance, properties=properties, online=True
                )
        except SubZeroAuthError as err:
            raise UpdateFailed(str(err)) from err
        except SubZeroConnectionError as err:
            raise UpdateFailed(str(err)) from err
        except SubZeroApiError as err:
            raise UpdateFailed(str(err)) from err
        return SubZeroData(appliances=states)

    async def async_set_property(
        self, device_id: str, key: str, value: Any
    ) -> None:
        """Write a property and refresh the affected appliance."""
        await self.client.async_set_property(device_id, key, value)
        await self.async_request_refresh()

    async def async_reset_air_filter(self, device_id: str) -> None:
        """Reset an appliance's air filter counter."""
        await self.client.async_reset_air_filter(device_id)
        await self.async_request_refresh()


def _is_offline(err: Exception) -> bool:
    """Return True when an error means the appliance is unreachable."""
    text = str(err)
    return str(OFFLINE_ERROR_CODE) in text or "isn't online" in text
