"""Binary sensors for the Sub-Zero Group integration.

These cover read-only state: door contacts, fault flags, and indicators whose
properties the cloud rejects writes for. Anything writable is a switch instead,
so no value is published twice.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import MODE_SWITCHES
from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity


@dataclass(frozen=True, kw_only=True)
class SubZeroBinaryDescription(BinarySensorEntityDescription):
    """Describe a Sub-Zero binary sensor."""


BINARY_SENSORS: tuple[SubZeroBinaryDescription, ...] = (
    SubZeroBinaryDescription(
        key="ref_door_ajar",
        name="Refrigerator door",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    SubZeroBinaryDescription(
        key="ref2_door_ajar",
        name="Refrigerator drawer",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    SubZeroBinaryDescription(
        key="frz_door_ajar",
        name="Freezer door",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    SubZeroBinaryDescription(
        key="wine_door_ajar",
        name="Wine door",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    SubZeroBinaryDescription(
        key="wine2_door_ajar",
        name="Wine door 2",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    SubZeroBinaryDescription(
        key="cav_door_ajar",
        name="Oven door",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    SubZeroBinaryDescription(
        key="ice_door_ajar",
        name="Ice maker door",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    SubZeroBinaryDescription(
        key="service_required",
        name="Service required",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    SubZeroBinaryDescription(
        key="wine_temp_alert_on",
        name="Wine temperature alert",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    SubZeroBinaryDescription(
        key="failsafe_on",
        name="Ice maker failsafe",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    SubZeroBinaryDescription(
        key="clean_soon_on",
        name="Ice maker cleaning due soon",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    SubZeroBinaryDescription(
        key="clean_now_on",
        name="Ice maker cleaning due",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    SubZeroBinaryDescription(
        key="cav_at_set_temp", name="Preheated", icon="mdi:thermometer-check"
    ),
    SubZeroBinaryDescription(
        key="cav_remote_ready", name="Remote ready", icon="mdi:remote"
    ),
    SubZeroBinaryDescription(
        key="cav_probe_on", name="Probe in use", icon="mdi:thermometer"
    ),
    SubZeroBinaryDescription(
        key="cav_probe_at_set_temp",
        name="Probe target reached",
        icon="mdi:thermometer-check",
    ),
    SubZeroBinaryDescription(
        key="cav_gourmet_mode_on", name="Gourmet mode", icon="mdi:chef-hat"
    ),
    SubZeroBinaryDescription(
        key="cav_cook_timer_complete",
        name="Cooking timer complete",
        icon="mdi:timer-check-outline",
    ),
    SubZeroBinaryDescription(
        key="kitchen_timer_active", name="Kitchen timer active", icon="mdi:timer-outline"
    ),
    SubZeroBinaryDescription(
        key="kitchen_timer_complete",
        name="Kitchen timer complete",
        icon="mdi:timer-check-outline",
    ),
    SubZeroBinaryDescription(
        key="delay_active", name="Ice delay active", icon="mdi:timer-sand"
    ),
    SubZeroBinaryDescription(
        key="delay_recurring", name="Ice delay repeats daily", icon="mdi:repeat"
    ),
    SubZeroBinaryDescription(
        key="water_filter_inserted",
        name="Water filter inserted",
        icon="mdi:water-check",
    ),
    SubZeroBinaryDescription(
        key="pin_window_open",
        name="Pairing window",
        icon="mdi:bluetooth-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SubZeroBinaryDescription(
        key="smart_grid_on",
        name="Smart grid",
        icon="mdi:transmission-tower",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors for read-only boolean properties."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroBinarySensor] = []
    for device_id, state in (
        coordinator.data.appliances.items() if coordinator.data else []
    ):
        properties = state.properties
        for description in BINARY_SENSORS:
            if description.key in MODE_SWITCHES:
                continue
            if not isinstance(properties.get(description.key), bool):
                continue
            entities.append(
                SubZeroBinarySensor(coordinator, entry, device_id, description)
            )
    async_add_entities(entities)


class SubZeroBinarySensor(SubZeroEntity, BinarySensorEntity):
    """A binary sensor reading a single boolean property."""

    entity_description: SubZeroBinaryDescription

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry,
        device_id: str,
        description: SubZeroBinaryDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, entry, device_id, description, key=description.key)
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def is_on(self) -> bool | None:
        """Return the property value."""
        value = self.properties.get(self.entity_description.key)
        return value if isinstance(value, bool) else None
