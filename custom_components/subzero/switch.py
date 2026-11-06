"""Switches for the Sub-Zero Group integration.

Only properties that the cloud accepts a write for are published here; the
writable set was verified by writing each property back to its current value
and recording whether the appliance accepted or rejected the command.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import MODE_SWITCHES
from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity


@dataclass(frozen=True, kw_only=True)
class SubZeroSwitchDescription(SwitchEntityDescription):
    """Describe a writable boolean property."""


SWITCHES: tuple[SubZeroSwitchDescription, ...] = tuple(
    SubZeroSwitchDescription(key=key, name=name)
    for key, name in (
        ("unit_on", "Power"),
        ("sabbath_on", "Sabbath mode"),
        ("ice_maker_on", "Ice maker"),
        ("max_ice_on", "Max ice"),
        ("night_ice_on", "Night ice"),
        ("internal_dispenser_enabled", "Internal dispenser"),
        ("air_filter_on", "Air filter reminder"),
        ("high_use_on", "High use mode"),
        ("short_vacation_on", "Short vacation"),
        ("long_vacation_on", "Long vacation"),
        ("winterize_on", "Winterize"),
        ("cav_unit_on", "Oven power"),
        ("cav_light_on", "Oven light"),
        ("cav2_unit_on", "Lower oven power"),
        ("cav2_light_on", "Lower oven light"),
        ("heated_dry_on", "Heated dry"),
        ("extended_dry_on", "Extended dry"),
        ("high_temp_wash_on", "High temperature wash"),
        ("sani_rinse_on", "Sanitize rinse"),
        ("top_rack_only_on", "Top rack only"),
        ("wash_cycle_on", "Wash cycle running"),
        ("fan_on", "Fan"),
        ("light_on", "Light"),
    )
)

ICONS: dict[str, str] = {
    "unit_on": "mdi:power",
    "sabbath_on": "mdi:candle",
    "ice_maker_on": "mdi:ice-cream",
    "max_ice_on": "mdi:snowflake",
    "night_ice_on": "mdi:weather-night",
    "internal_dispenser_enabled": "mdi:cup-water",
    "air_filter_on": "mdi:air-filter",
    "high_use_on": "mdi:account-multiple",
    "short_vacation_on": "mdi:bag-suitcase",
    "long_vacation_on": "mdi:bag-suitcase-outline",
    "winterize_on": "mdi:snowflake-alert",
    "cav_light_on": "mdi:lightbulb",
    "cav2_light_on": "mdi:lightbulb",
    "heated_dry_on": "mdi:heat-wave",
    "extended_dry_on": "mdi:weather-windy",
    "high_temp_wash_on": "mdi:thermometer-high",
    "sani_rinse_on": "mdi:shield-check",
    "top_rack_only_on": "mdi:silverware-fork-knife",
    "wash_cycle_on": "mdi:dishwasher",
    "fan_on": "mdi:fan",
    "light_on": "mdi:lightbulb",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches for verified writable boolean properties."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroSwitch] = []
    for device_id, state in (
        coordinator.data.appliances.items() if coordinator.data else []
    ):
        properties = state.properties
        for description in SWITCHES:
            value = properties.get(description.key)
            if not isinstance(value, bool):
                continue
            entities.append(
                SubZeroSwitch(coordinator, entry, device_id, description)
            )
    async_add_entities(entities)


class SubZeroSwitch(SubZeroEntity, SwitchEntity):
    """A switch bound to one writable boolean property."""

    entity_description: SubZeroSwitchDescription

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry,
        device_id: str,
        description: SubZeroSwitchDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, entry, device_id, description, key=description.key)
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_icon = ICONS.get(description.key)

    @property
    def is_on(self) -> bool | None:
        """Return the property value."""
        value = self.properties.get(self.entity_description.key)
        return value if isinstance(value, bool) else None

    async def async_turn_on(self, **kwargs) -> None:
        """Write True to the property."""
        await self.coordinator.async_set_property(
            self._device_id, self.entity_description.key, True
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Write False to the property."""
        await self.coordinator.async_set_property(
            self._device_id, self.entity_description.key, False
        )
