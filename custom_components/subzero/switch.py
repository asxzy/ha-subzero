"""Switches for the Sub-Zero Group integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity


@dataclass(frozen=True, kw_only=True)
class SubZeroSwitchDescription(SwitchEntityDescription):
    """Describe a writable boolean property."""


SWITCHES: tuple[SubZeroSwitchDescription, ...] = (
    SubZeroSwitchDescription(key="unit_on", name="Power", icon="mdi:power"),
    SubZeroSwitchDescription(
        key="sabbath_on", name="Sabbath mode", icon="mdi:candle"
    ),
    SubZeroSwitchDescription(
        key="ice_maker_on", name="Ice maker", icon="mdi:ice-cream"
    ),
    SubZeroSwitchDescription(key="max_ice_on", name="Max ice", icon="mdi:snowflake"),
    SubZeroSwitchDescription(
        key="night_ice_on", name="Night ice", icon="mdi:weather-night"
    ),
    SubZeroSwitchDescription(
        key="internal_dispenser_enabled",
        name="Internal dispenser",
        icon="mdi:cup-water",
    ),
    SubZeroSwitchDescription(
        key="air_filter_on", name="Air filter reminder", icon="mdi:air-filter"
    ),
    SubZeroSwitchDescription(
        key="high_use_on", name="High use mode", icon="mdi:account-multiple"
    ),
    SubZeroSwitchDescription(
        key="short_vacation_on",
        name="Short vacation",
        icon="mdi:bag-suitcase",
    ),
    SubZeroSwitchDescription(
        key="long_vacation_on",
        name="Long vacation",
        icon="mdi:bag-suitcase-outline",
    ),
    SubZeroSwitchDescription(
        key="winterize_on", name="Winterize", icon="mdi:snowflake-alert"
    ),
    SubZeroSwitchDescription(
        key="wine_temp_alert_on",
        name="Wine temperature alert",
        icon="mdi:thermometer-alert",
    ),
    SubZeroSwitchDescription(
        key="smart_grid_on",
        name="Smart grid",
        icon="mdi:transmission-tower",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    # Ovens
    SubZeroSwitchDescription(key="cav_unit_on", name="Oven power", icon="mdi:power"),
    SubZeroSwitchDescription(
        key="cav_light_on", name="Oven light", icon="mdi:lightbulb"
    ),
    SubZeroSwitchDescription(
        key="cav2_unit_on", name="Lower oven power", icon="mdi:power"
    ),
    SubZeroSwitchDescription(
        key="cav2_light_on", name="Lower oven light", icon="mdi:lightbulb"
    ),
    # Dishwashers
    SubZeroSwitchDescription(
        key="heated_dry_on", name="Heated dry", icon="mdi:heat-wave"
    ),
    SubZeroSwitchDescription(
        key="extended_dry_on", name="Extended dry", icon="mdi:weather-windy"
    ),
    SubZeroSwitchDescription(
        key="high_temp_wash_on", name="High temperature wash", icon="mdi:thermometer-high"
    ),
    SubZeroSwitchDescription(
        key="sani_rinse_on", name="Sanitize rinse", icon="mdi:shield-check"
    ),
    SubZeroSwitchDescription(
        key="top_rack_only_on", name="Top rack only", icon="mdi:silverware-fork-knife"
    ),
    # Hoods
    SubZeroSwitchDescription(key="fan_on", name="Fan", icon="mdi:fan"),
    SubZeroSwitchDescription(key="light_on", name="Light", icon="mdi:lightbulb"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switches for reported boolean properties."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroSwitch] = []
    for device_id, state in (coordinator.data.appliances.items() if coordinator.data else []):
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
