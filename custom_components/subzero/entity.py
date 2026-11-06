"""Shared entity plumbing for the Sub-Zero Group integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import ApplianceState, SubZeroCoordinator


class SubZeroEntity(CoordinatorEntity[SubZeroCoordinator]):
    """Base class for entities tied to one appliance."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry: ConfigEntry,
        device_id: str,
        description: EntityDescription | None = None,
        *,
        key: str | None = None,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._device_id = device_id
        self._entry = entry
        self._property_key = key
        if description is not None:
            self.entity_description = description

    @property
    def _state(self) -> ApplianceState | None:
        """Return the current appliance state."""
        return self.coordinator.data.get(self._device_id) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        """Return False when the appliance is offline or the update failed."""
        state = self._state
        return bool(super().available and state is not None and state.online)

    @property
    def appliance(self):
        """Return the appliance metadata."""
        state = self._state
        if state is not None:
            return state.appliance
        return self.coordinator.appliances[self._device_id]

    @property
    def properties(self) -> dict[str, Any]:
        """Return the appliance property dictionary."""
        state = self._state
        return state.properties if state is not None else {}

    @property
    def device_info(self) -> DeviceInfo:
        """Describe the appliance in the device registry."""
        appliance = self.appliance
        properties = self.properties
        version = properties.get("version")
        firmware = None
        if isinstance(version, dict):
            firmware = version.get("fw") or version.get("rtapp")
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            name=appliance.name,
            manufacturer=MANUFACTURER,
            model=properties.get("appliance_model") or appliance.appliance_type,
            serial_number=properties.get("appliance_serial"),
            sw_version=str(firmware) if firmware else None,
        )

    @property
    def native_value(self) -> Any:
        """Return the current property value."""
        if self._property_key is None:
            return None
        return self.properties.get(self._property_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the appliance type alongside each value."""
        appliance = self.appliance
        return {"appliance_type": appliance.appliance_type}
