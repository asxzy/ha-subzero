"""Binary sensors for the Sub-Zero Group integration."""

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
        key="ice_maker_on",
        name="Ice maker",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:ice-cream",
    ),
    SubZeroBinaryDescription(
        key="max_ice_on",
        name="Max ice",
        icon="mdi:snowflake",
    ),
    SubZeroBinaryDescription(
        key="night_ice_on",
        name="Night ice",
        icon="mdi:weather-night",
    ),
    SubZeroBinaryDescription(
        key="sabbath_on",
        name="Sabbath mode",
        icon="mdi:candle",
    ),
    SubZeroBinaryDescription(
        key="high_use_on",
        name="High use mode",
        icon="mdi:account-multiple",
    ),
    SubZeroBinaryDescription(
        key="short_vacation_on",
        name="Short vacation",
        icon="mdi:bag-suitcase",
    ),
    SubZeroBinaryDescription(
        key="long_vacation_on",
        name="Long vacation",
        icon="mdi:bag-suitcase-outline",
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
        key="air_filter_on",
        name="Air filter",
        icon="mdi:air-filter",
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
    """Set up binary sensors for reported properties."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroBinarySensor] = []
    for device_id, state in (coordinator.data.appliances.items() if coordinator.data else []):
        properties = state.properties
        for description in BINARY_SENSORS:
            if description.key not in properties:
                continue
            if not isinstance(properties[description.key], bool):
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
