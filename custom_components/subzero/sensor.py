"""Sensor entities for the Sub-Zero Group integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import FAMILY_DISHWASHER, FAMILY_HOOD, FAMILY_OVEN, appliance_family
from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity


@dataclass(frozen=True, kw_only=True)
class SubZeroSensorDescription(SensorEntityDescription):
    """Describe a Sub-Zero sensor."""


SENSORS: tuple[SubZeroSensorDescription, ...] = (
    SubZeroSensorDescription(
        key="ref_display_temp",
        name="Refrigerator temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    ),
    SubZeroSensorDescription(
        key="frz_display_temp",
        name="Freezer temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    ),
    SubZeroSensorDescription(
        key="wine_display_temp",
        name="Wine temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    ),
    SubZeroSensorDescription(
        key="wine2_display_temp",
        name="Wine zone 2 temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    ),
    SubZeroSensorDescription(
        key="air_filter_pct_remaining",
        name="Air filter remaining",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:air-filter",
    ),
    SubZeroSensorDescription(
        key="water_filter_pct_remaining",
        name="Water filter remaining",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water",
    ),
    SubZeroSensorDescription(
        key="ap_rssi",
        name="Wi-Fi signal",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SubZeroSensorDescription(
        key="uptime",
        name="Uptime",
        icon="mdi:clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    SubZeroSensorDescription(
        key="diagnostic_status",
        name="Diagnostic status",
        icon="mdi:stethoscope",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    # Ovens
    SubZeroSensorDescription(
        key="cav_temp",
        name="Oven temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    ),
    SubZeroSensorDescription(
        key="cav_probe_temp",
        name="Probe temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    ),
    # Dishwashers
    SubZeroSensorDescription(
        key="wash_cycle_end_time",
        name="Wash cycle ends",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    # Hoods
    SubZeroSensorDescription(
        key="fan_speed",
        name="Fan speed",
        icon="mdi:fan",
    ),
)

FILTER_SENSORS = frozenset(
    {"air_filter_pct_remaining", "water_filter_pct_remaining"}
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for each appliance's reported properties."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroSensor] = []
    for device_id, state in (coordinator.data.appliances.items() if coordinator.data else []):
        properties = state.properties
        family = appliance_family(properties)
        for description in SENSORS:
            if description.key not in properties:
                continue
            if description.key == "cav_temp" and family != FAMILY_OVEN:
                continue
            if description.key == "cav_probe_temp" and family != FAMILY_OVEN:
                continue
            if description.key == "wash_cycle_end_time" and family != FAMILY_DISHWASHER:
                continue
            if description.key == "fan_speed" and family != FAMILY_HOOD:
                continue
            entities.append(SubZeroSensor(coordinator, entry, device_id, description))
    async_add_entities(entities)


class SubZeroSensor(SubZeroEntity, SensorEntity):
    """A sensor reading a single appliance property."""

    entity_description: SubZeroSensorDescription

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry,
        device_id: str,
        description: SubZeroSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, entry, device_id, description, key=description.key)
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        """Return the property value, hiding sentinel readings."""
        value = self.properties.get(self.entity_description.key)
        if self.entity_description.key in FILTER_SENSORS and value in (None, 255):
            return None
        if value is None:
            return None
        return value
