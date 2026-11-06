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
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import ZONE_DOORS, temperature_range, zones
from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity

_LOGGER = logging.getLogger(__name__)

# Keyed by setpoint property: the reading that pairs with each zone.
ZONE_CURRENT_TEMP: dict[str, str] = {
    "ref_set_temp": "ref_display_temp",
    "ref2_set_temp": "ref2_display_temp",
    "frz_set_temp": "frz_display_temp",
    "wine_set_temp": "wine_display_temp",
    "wine2_set_temp": "wine2_display_temp",
    "crisp_set_temp": "crisp_display_temp",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entities for every reported zone."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroClimate] = []
    for device_id, state in (
        coordinator.data.appliances.items() if coordinator.data else []
    ):
        properties = state.properties
        reported = zones(properties)
        multiple = len(reported) > 1
        for setpoint_key, label in reported.items():
            entities.append(
                SubZeroClimate(
                    coordinator,
                    entry,
                    device_id,
                    setpoint_key,
                    label if multiple else None,
                )
            )
    async_add_entities(entities)


class SubZeroClimate(SubZeroEntity, ClimateEntity):
    """One temperature zone of a refrigeration appliance."""

    _attr_native_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_target_temperature_step = 1
    _attr_hvac_modes = [HVACMode.COOL, HVACMode.OFF]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _enable_turn_on_off_backwards_compat = False

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry,
        device_id: str,
        setpoint_key: str,
        label: str | None,
    ) -> None:
        """Initialize the zone."""
        super().__init__(coordinator, entry, device_id, key=setpoint_key)
        self._setpoint_key = setpoint_key
        self._attr_name = label
        self._attr_unique_id = f"{device_id}_{setpoint_key}"

    @property
    def min_temp(self) -> float:
        """Return the lowest accepted setpoint."""
        bounds = temperature_range(self._setpoint_key, self.properties)
        return float(bounds[0]) if bounds else 34.0

    @property
    def max_temp(self) -> float:
        """Return the highest accepted setpoint."""
        bounds = temperature_range(self._setpoint_key, self.properties)
        return float(bounds[1]) if bounds else 42.0

    @property
    def native_current_temperature(self) -> float | None:
        """Return the measured temperature, if the appliance reports one.

        Many units only report setpoints, not sensors; a missing reading is
        normal and is left as ``None`` rather than invented.
        """
        key = ZONE_CURRENT_TEMP.get(self._setpoint_key)
        value = self.properties.get(key) if key else None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        # Zero is the app's "no reading" sentinel on units without a sensor.
        return float(value) if value else None

    @property
    def native_target_temperature(self) -> float | None:
        """Return the configured setpoint."""
        value = self.properties.get(self._setpoint_key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return float(value)

    @property
    def hvac_mode(self) -> HVACMode:
        """Return the current mode."""
        return HVACMode.COOL if self.properties.get("unit_on", True) else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction | None:
        """Return the current activity, when the appliance reports enough to say.

        These units expose setpoints but no temperature sensor, so there is
        nothing to compare a reading against. Reporting "cooling" anyway would
        assert an activity nothing in the snapshot supports.
        """
        if self.hvac_mode is HVACMode.OFF:
            return HVACAction.OFF
        if self.native_current_temperature is None:
            return None
        door = ZONE_DOORS.get(self._setpoint_key)
        if door and self.properties.get(door):
            return HVACAction.IDLE
        current = self.native_current_temperature
        target = self.native_target_temperature
        if target is not None and current is not None and current <= target:
            return HVACAction.IDLE
        return HVACAction.COOLING

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the zone setpoint."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        value = int(round(temperature))
        if not self.min_temp <= value <= self.max_temp:
            raise ServiceValidationError(
                f"This appliance accepts setpoints between "
                f"{int(self.min_temp)} and {int(self.max_temp)} F."
            )
        await self.coordinator.async_set_property(
            self._device_id, self._setpoint_key, value
        )

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Turn the appliance on or off."""
        if hvac_mode not in self._attr_hvac_modes:
            raise ServiceValidationError("This appliance does not support that mode.")
        await self.coordinator.async_set_property(
            self._device_id, "unit_on", hvac_mode == HVACMode.COOL
        )
