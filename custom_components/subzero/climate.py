"""Climate entities for Sub-Zero Group refrigeration and wine appliances."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import zones
from .const import DOMAIN
from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity

_LOGGER = logging.getLogger(__name__)

# The cloud reports whole degrees Fahrenheit regardless of the unit the app shows.
MIN_TEMP_F = -5
MAX_TEMP_F = 70

ZONE_CURRENT_TEMP: dict[str, str] = {
    "ref_set_temp": "ref_display_temp",
    "frz_set_temp": "frz_display_temp",
    "wine_set_temp": "wine_display_temp",
    "wine2_set_temp": "wine2_display_temp",
    "crisp_set_temp": "crisp_display_temp",
}

ZONE_DOOR: dict[str, str] = {
    "ref_set_temp": "ref_door_ajar",
    "frz_set_temp": "frz_door_ajar",
    "wine_set_temp": "wine_door_ajar",
    "wine2_set_temp": "wine_door_ajar",
    "crisp_set_temp": "ref_door_ajar",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities for every reported zone."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroClimate] = []
    for device_id, state in (coordinator.data.appliances.items() if coordinator.data else []):
        properties = state.properties
        reported = zones(properties)
        multiple = len(reported) > 1
        for index, (setpoint_key, label) in enumerate(reported.items()):
            entities.append(
                SubZeroClimate(
                    coordinator,
                    entry,
                    device_id,
                    setpoint_key,
                    label,
                    index=index,
                    multiple=multiple,
                )
            )
    async_add_entities(entities)


class SubZeroClimate(SubZeroEntity, ClimateEntity):
    """One temperature zone of a refrigeration appliance."""

    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_target_temperature_step = 1
    _attr_min_temp = MIN_TEMP_F
    _attr_max_temp = MAX_TEMP_F
    _attr_hvac_modes = [HVACMode.COOL, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _enable_turn_on_off_backwards_compat = False

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry,
        device_id: str,
        setpoint_key: str,
        label: str,
        *,
        index: int = 0,
        multiple: bool = False,
    ) -> None:
        """Initialize the zone."""
        super().__init__(coordinator, entry, device_id, key=setpoint_key)
        self._setpoint_key = setpoint_key
        # A single-zone appliance needs no zone label; the device name is enough.
        self._attr_name = label if multiple else None
        self._attr_unique_id = f"{device_id}_{setpoint_key}"

    @property
    def current_temperature(self) -> float | None:
        """Return the measured temperature, if the appliance reports one."""
        reported = self.properties.get(ZONE_CURRENT_TEMP.get(self._setpoint_key, ""))
        if reported is None or reported == 0:
            return None
        return float(reported)

    @property
    def target_temperature(self) -> float | None:
        """Return the configured setpoint."""
        value = self.properties.get(self._setpoint_key)
        return float(value) if isinstance(value, int) else None

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current mode."""
        return HVACMode.COOL if self.properties.get("unit_on", True) else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        """Return the current activity."""
        if self.hvac_mode is HVACMode.OFF:
            return HVACAction.OFF
        if self.properties.get(ZONE_DOOR.get(self._setpoint_key, "")):
            return HVACAction.IDLE
        return HVACAction.COOLING

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the zone setpoint."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        await self.coordinator.async_set_property(
            self._device_id, self._setpoint_key, int(round(temperature))
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn the appliance on or off."""
        await self.coordinator.async_set_property(
            self._device_id, "unit_on", hvac_mode == HVACMode.COOL
        )
