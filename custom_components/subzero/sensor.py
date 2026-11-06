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

    family: str | None = None


SENSORS: tuple[SubZeroSensorDescription, ...] = (
    SubZeroSensorDescription(
        key="ref_display_temp",
        name="Refrigerator temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
    ),
    SubZeroSensorDescription(
        key="ref2_display_temp",
        name="Refrigerator drawer temperature",
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
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement="s",
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
    SubZeroSensorDescription(
        key="cav_temp",
        name="Oven temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        family=FAMILY_OVEN,
    ),
    SubZeroSensorDescription(
        key="cav2_temp",
        name="Lower oven temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        family=FAMILY_OVEN,
    ),
    SubZeroSensorDescription(
        key="cav_probe_temp",
        name="Probe temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        family=FAMILY_OVEN,
    ),
    SubZeroSensorDescription(
        key="wash_cycle_end_time",
        name="Wash cycle ends",
        device_class=SensorDeviceClass.TIMESTAMP,
        family=FAMILY_DISHWASHER,
    ),
    SubZeroSensorDescription(
        key="wash_status",
        name="Wash status",
        icon="mdi:dishwasher",
        family=FAMILY_DISHWASHER,
    ),
    SubZeroSensorDescription(
        key="fan_speed",
        name="Fan speed",
        icon="mdi:fan",
        entity_category=EntityCategory.DIAGNOSTIC,
        family=FAMILY_HOOD,
    ),
)

# 255 is the app's "unset" sentinel. Zero is a real reading: it means the
# consumable is exhausted and the appliance is asking for a replacement.
FILTER_SENSORS = frozenset({"air_filter_pct_remaining", "water_filter_pct_remaining"})
SENTINEL_READINGS = frozenset({255})


def parse_uptime(value: Any) -> int | None:
    """Convert the appliance's ``hours:minutes:seconds`` uptime to seconds.

    After 100 hours the firmware truncates the string to eight characters, so
    trailing digits are dropped; the missing digits are zeros.
    """
    if not isinstance(value, str) or ":" not in value:
        return None
    hours, _, rest = value.partition(":")
    if len(value) == 8 and len(hours) > 2:
        rest += "00:00"[len(rest) :]
    try:
        minutes, seconds = (int(part) for part in rest.split(":"))
        total_hours = int(hours)
    except ValueError:
        return None
    if total_hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
        return None
    return total_hours * 3600 + minutes * 60 + seconds


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for each appliance's reported properties."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroSensor] = []
    for device_id, state in (
        coordinator.data.appliances.items() if coordinator.data else []
    ):
        properties = state.properties
        family = appliance_family(properties)
        for description in SENSORS:
            if description.key not in properties:
                continue
            if description.family is not None and description.family != family:
                continue
            entities.append(
                SubZeroSensor(coordinator, entry, device_id, description)
            )
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
        key = self.entity_description.key
        value = self.properties.get(key)
        if value is None:
            return None
        if key in FILTER_SENSORS and value in SENTINEL_READINGS:
            return None
        if key == "uptime":
            return parse_uptime(value)
        return value
