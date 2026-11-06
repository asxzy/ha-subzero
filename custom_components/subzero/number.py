"""Number entities for the Sub-Zero Group integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity


@dataclass(frozen=True, kw_only=True)
class SubZeroNumberDescription(NumberEntityDescription):
    """Describe a writable integer property."""


NUMBERS: tuple[SubZeroNumberDescription, ...] = (
    SubZeroNumberDescription(
        key="light_percent",
        name="Light brightness",
        native_min_value=5,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        icon="mdi:lightbulb",
    ),
    SubZeroNumberDescription(
        key="accent_light_level",
        name="Accent light level",
        native_min_value=0,
        native_max_value=130,
        native_step=10,
        mode=NumberMode.SLIDER,
        icon="mdi:lightbulb-outline",
    ),
    SubZeroNumberDescription(
        key="fan_speed",
        name="Fan speed",
        native_min_value=0,
        native_max_value=4,
        native_step=1,
        mode=NumberMode.SLIDER,
        icon="mdi:fan",
    ),
    SubZeroNumberDescription(
        key="cav_set_temp",
        name="Oven setpoint",
        native_min_value=85,
        native_max_value=550,
        native_step=5,
        mode=NumberMode.BOX,
        icon="mdi:thermometer",
    ),
    SubZeroNumberDescription(
        key="cav_probe_set_temp",
        name="Probe target",
        native_min_value=120,
        native_max_value=210,
        native_step=5,
        mode=NumberMode.BOX,
        icon="mdi:thermometer-probe",
    ),
    SubZeroNumberDescription(
        key="delay_start_timer_duration",
        name="Delay start",
        native_min_value=0,
        native_max_value=720,
        native_step=60,
        mode=NumberMode.BOX,
        icon="mdi:timer-outline",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for reported integer properties."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroNumber] = []
    for device_id, state in (coordinator.data.appliances.items() if coordinator.data else []):
        properties = state.properties
        for description in NUMBERS:
            value = properties.get(description.key)
            if not isinstance(value, int) or isinstance(value, bool):
                continue
            entities.append(
                SubZeroNumber(coordinator, entry, device_id, description)
            )
    async_add_entities(entities)


class SubZeroNumber(SubZeroEntity, NumberEntity):
    """A number bound to one writable integer property."""

    entity_description: SubZeroNumberDescription

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry,
        device_id: str,
        description: SubZeroNumberDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(coordinator, entry, device_id, description, key=description.key)
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        value = self.properties.get(self.entity_description.key)
        return float(value) if isinstance(value, int) else None

    async def async_set_native_value(self, value: float) -> None:
        """Write a new value."""
        await self.coordinator.async_set_property(
            self._device_id, self.entity_description.key, int(round(value))
        )
