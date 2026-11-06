"""Select entities for the Sub-Zero Group integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity


@dataclass(frozen=True, kw_only=True)
class SubZeroSelectDescription(SelectEntityDescription):
    """Describe a select over an integer property."""

    options_map: dict[str, int]


SELECTS: tuple[SubZeroSelectDescription, ...] = (
    SubZeroSelectDescription(
        key="crisp_temp_mode",
        name="Crisper mode",
        icon="mdi:food-apple",
        options_map={"Manual": 0, "Automatic": 1},
    ),
    SubZeroSelectDescription(
        key="humidity_control",
        name="Humidity control",
        icon="mdi:water-percent",
        options_map={"Normal": 1, "Enhanced": 2},
    ),
    SubZeroSelectDescription(
        key="night_mode",
        name="Night mode",
        icon="mdi:weather-night",
        options_map={"Disabled": 0, "Enabled": 1},
    ),
    SubZeroSelectDescription(
        key="accent_light_level",
        name="Accent light",
        icon="mdi:lightbulb-outline",
        options_map={"Off": 0, "Low": 110, "Medium": 120, "High": 130},
    ),
    SubZeroSelectDescription(
        key="door_ajar_timeout",
        name="Door alarm delay",
        icon="mdi:door-open",
        options_map={
            "1 minute": 1,
            "2 minutes": 2,
            "5 minutes": 5,
            "10 minutes": 10,
        },
    ),
    SubZeroSelectDescription(
        key="cav_cook_mode",
        name="Cook mode",
        icon="mdi:stove",
        options_map={
            "Off": 0,
            "Bake": 1,
            "Roast": 2,
            "Broil": 3,
            "Bake stone": 4,
            "Convection bake": 5,
            "Convection roast": 6,
            "Convection broil": 7,
            "Convection": 8,
            "Proof": 9,
            "Dehydrate": 10,
            "Self clean": 11,
            "Warm": 12,
        },
    ),
    SubZeroSelectDescription(
        key="wash_cycle",
        name="Wash cycle",
        icon="mdi:dishwasher",
        options_map={
            "Auto": 1,
            "Normal": 2,
            "Heavy": 3,
            "Quick": 4,
            "Pots and pans": 5,
            "Soak and scrub": 6,
            "Light": 7,
            "Crystal china": 8,
            "Rinse and hold": 9,
            "Plastics": 10,
            "Energy": 11,
            "Extra quiet": 12,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up select entities for reported integer properties."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroSelect] = []
    for device_id, state in (coordinator.data.appliances.items() if coordinator.data else []):
        properties = state.properties
        for description in SELECTS:
            value = properties.get(description.key)
            if not isinstance(value, int) or isinstance(value, bool):
                continue
            entities.append(
                SubZeroSelect(coordinator, entry, device_id, description)
            )
    async_add_entities(entities)


class SubZeroSelect(SubZeroEntity, SelectEntity):
    """A select mapped onto an integer property."""

    entity_description: SubZeroSelectDescription

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry,
        device_id: str,
        description: SubZeroSelectDescription,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator, entry, device_id, description, key=description.key)
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_options = list(description.options_map)

    @property
    def current_option(self) -> str | None:
        """Return the option matching the current value."""
        value = self.properties.get(self.entity_description.key)
        if not isinstance(value, int):
            return None
        for label, raw in self.entity_description.options_map.items():
            if raw == value:
                return label
        return None

    async def async_select_option(self, option: str) -> None:
        """Write the value behind an option."""
        raw = self.entity_description.options_map.get(option)
        if raw is None:
            return
        await self.coordinator.async_set_property(
            self._device_id, self.entity_description.key, raw
        )
