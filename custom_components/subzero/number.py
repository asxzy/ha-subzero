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

from .capabilities import (
    FAMILY_DISHWASHER,
    FAMILY_HOOD,
    FAMILY_OVEN,
    appliance_family,
)
from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity


@dataclass(frozen=True, kw_only=True)
class SubZeroNumberDescription(NumberEntityDescription):
    """Describe a writable numeric property."""

    family: str | None = None


NUMBERS: tuple[SubZeroNumberDescription, ...] = (
    SubZeroNumberDescription(
        key="light_percent",
        family=FAMILY_HOOD,
        name="Light brightness",
        native_min_value=5,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        icon="mdi:lightbulb",
    ),
    SubZeroNumberDescription(
        key="fan_speed",
        family=FAMILY_HOOD,
        name="Fan speed",
        native_min_value=0,
        native_max_value=4,
        native_step=1,
        mode=NumberMode.SLIDER,
        icon="mdi:fan",
    ),
    SubZeroNumberDescription(
        key="color_level",
        family=FAMILY_HOOD,
        name="Light color",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        icon="mdi:palette",
    ),
    SubZeroNumberDescription(
        key="halo_max_percent",
        family=FAMILY_HOOD,
        name="Control brightness",
        native_min_value=0,
        native_max_value=30,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        icon="mdi:brightness-6",
    ),
    # The hood stores one favourite setting of each kind, which the app recalls
    # from a single button. They carry their own setters, so they are real
    # controls rather than a copy of the live level.
    SubZeroNumberDescription(
        key="fav_fan_speed",
        family=FAMILY_HOOD,
        name="Favourite fan speed",
        native_min_value=0,
        native_max_value=4,
        native_step=1,
        mode=NumberMode.SLIDER,
        icon="mdi:fan",
    ),
    SubZeroNumberDescription(
        key="fav_light_percent",
        family=FAMILY_HOOD,
        name="Favourite light brightness",
        native_min_value=5,
        native_max_value=100,
        native_step=1,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        icon="mdi:lightbulb",
    ),
    SubZeroNumberDescription(
        key="fav_color_level",
        family=FAMILY_HOOD,
        name="Favourite light colour",
        native_min_value=0,
        native_max_value=100,
        native_step=1,
        mode=NumberMode.SLIDER,
        icon="mdi:palette",
    ),
    SubZeroNumberDescription(
        key="cav_set_temp",
        family=FAMILY_OVEN,
        name="Oven setpoint",
        native_min_value=85,
        native_max_value=550,
        native_step=5,
        mode=NumberMode.BOX,
        icon="mdi:thermometer",
    ),
    SubZeroNumberDescription(
        key="cav2_set_temp",
        family=FAMILY_OVEN,
        name="Lower oven setpoint",
        native_min_value=85,
        native_max_value=550,
        native_step=5,
        mode=NumberMode.BOX,
        icon="mdi:thermometer",
    ),
    SubZeroNumberDescription(
        key="cav_probe_set_temp",
        family=FAMILY_OVEN,
        name="Probe target",
        native_min_value=120,
        native_max_value=210,
        native_step=5,
        mode=NumberMode.BOX,
        icon="mdi:thermometer-probe",
    ),
    SubZeroNumberDescription(
        key="cav2_probe_set_temp",
        family=FAMILY_OVEN,
        name="Lower oven probe target",
        native_min_value=120,
        native_max_value=210,
        native_step=5,
        mode=NumberMode.BOX,
        icon="mdi:thermometer-probe",
    ),
    SubZeroNumberDescription(
        key="door_ajar_timeout",
        name="Door open delay",
        # The property is a minute count; the app offers 1/2/5/10/15/30 but the
        # cloud accepts any integer, so this is a number rather than a select.
        native_min_value=0,
        native_max_value=30,
        native_step=1,
        native_unit_of_measurement="min",
        mode=NumberMode.BOX,
        icon="mdi:door-open",
    ),
    SubZeroNumberDescription(
        key="delay_start_timer_duration",
        family=FAMILY_DISHWASHER,
        name="Delay start",
        native_min_value=0,
        native_max_value=720,
        native_step=60,
        mode=NumberMode.BOX,
        icon="mdi:timer-outline",
    ),
    SubZeroNumberDescription(
        key="kitchen_timer_duration",
        family=FAMILY_OVEN,
        name="Kitchen timer",
        native_min_value=0,
        native_max_value=720,
        native_step=1,
        mode=NumberMode.BOX,
        icon="mdi:timer",
    ),
    SubZeroNumberDescription(
        key="kitchen_timer2_duration",
        family=FAMILY_OVEN,
        name="Kitchen timer 2",
        native_min_value=0,
        native_max_value=720,
        native_step=1,
        mode=NumberMode.BOX,
        icon="mdi:timer",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up number entities for reported numeric properties."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroNumber] = []
    for device_id, state in (
        coordinator.data.appliances.items() if coordinator.data else []
    ):
        properties = state.properties
        family = appliance_family(properties)
        for description in NUMBERS:
            if description.family is not None and description.family != family:
                continue
            value = properties.get(description.key)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            entities.append(
                SubZeroNumber(coordinator, entry, device_id, description)
            )
    async_add_entities(entities)


class SubZeroNumber(SubZeroEntity, NumberEntity):
    """A number bound to one writable numeric property."""

    entity_description: SubZeroNumberDescription

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry,
        device_id: str,
        description: SubZeroNumberDescription,
    ) -> None:
        """Initialize the number."""
        super().__init__(
            coordinator, entry, device_id, description, key=description.key
        )
        self._attr_unique_id = f"{device_id}_{description.key}"

    @property
    def native_value(self) -> float | None:
        """Return the current value."""
        value = self.properties.get(self.entity_description.key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        return float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write a new value."""
        await self.coordinator.async_set_property(
            self._device_id, self.entity_description.key, int(round(value))
        )
