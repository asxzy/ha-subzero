"""Buttons for Sub-Zero Group one-shot commands.

Some appliance actions are not state: a wash cycle is started and cancelled
rather than toggled, and an oven is started with a setpoint and cooking mode in
the same command. Publishing those as switches would misrepresent the property,
because it reads back as False a moment after it is written.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import (
    FAMILY_DISHWASHER,
    FAMILY_OVEN,
    appliance_family,
)
from .coordinator import SubZeroCoordinator
from .entity import SubZeroEntity

# The app gates a remote start on a readiness flag the appliance sets once the
# user has enabled remote operation on the unit itself.
OVEN_PREFIXES = ("cav", "cav2")


@dataclass(frozen=True, kw_only=True)
class SubZeroButtonDescription(ButtonEntityDescription):
    """Describe a one-shot command."""

    family: str | None = None
    # The property whose truth makes the command possible.
    requires: str | None = None


BUTTONS: tuple[SubZeroButtonDescription, ...] = (
    SubZeroButtonDescription(
        key="wash_cycle_on",
        name="Start wash cycle",
        icon="mdi:play-circle",
        family=FAMILY_DISHWASHER,
        requires="wash_cycle",
    ),
    SubZeroButtonDescription(
        key="cancel_wash_cycle",
        name="Cancel wash cycle",
        icon="mdi:stop-circle",
        family=FAMILY_DISHWASHER,
        requires="wash_cycle",
    ),
    SubZeroButtonDescription(
        key="cav_unit_on",
        name="Start oven",
        icon="mdi:play-circle",
        family=FAMILY_OVEN,
        requires="cav_remote_ready",
    ),
    SubZeroButtonDescription(
        key="cav2_unit_on",
        name="Start lower oven",
        icon="mdi:play-circle",
        family=FAMILY_OVEN,
        requires="cav2_remote_ready",
    ),
    SubZeroButtonDescription(
        key="reset_air_filter",
        name="Reset air filter",
        icon="mdi:air-filter",
        entity_category=EntityCategory.CONFIG,
        requires="air_filter_pct_remaining",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one-shot command buttons."""
    coordinator: SubZeroCoordinator = entry.runtime_data
    entities: list[SubZeroButton] = []
    for device_id, state in (
        coordinator.data.appliances.items() if coordinator.data else []
    ):
        properties = state.properties
        family = appliance_family(properties)
        for description in BUTTONS:
            if description.family is not None and description.family != family:
                continue
            if description.requires is None:
                continue
            if description.requires not in properties:
                continue
            entities.append(
                SubZeroButton(coordinator, entry, device_id, description)
            )
    async_add_entities(entities)


class SubZeroButton(SubZeroEntity, ButtonEntity):
    """A button that sends one command to the appliance."""

    entity_description: SubZeroButtonDescription

    def __init__(
        self,
        coordinator: SubZeroCoordinator,
        entry,
        device_id: str,
        description: SubZeroButtonDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, entry, device_id, description, key=description.key)
        self._attr_unique_id = f"{device_id}_{description.key}"

    async def async_press(self) -> None:
        """Send the command."""
        key = self.entity_description.key
        if key == "cancel_wash_cycle":
            if self.properties.get("wash_cycle_on") is not True and not (
                self.properties.get("wash_status") in (1, 2, 3, 7)
            ):
                raise ServiceValidationError("There is no wash cycle to cancel.")
            await self.coordinator.async_set_property(
                self._device_id, "wash_cycle_on", False
            )
            return
        if key == "wash_cycle_on":
            await self.coordinator.async_set_property(
                self._device_id, "wash_cycle_on", True
            )
            return
        if key == "reset_air_filter":
            await self.coordinator.async_reset_air_filter(self._device_id)
            return
        # An oven start needs its cooking mode and setpoint in the same command;
        # writing power alone leaves the oven without a mode to run.
        prefix = key.removesuffix("_unit_on")
        if self.properties.get(key) is True:
            await self.coordinator.async_set_property(self._device_id, key, True)
            return
        mode = self.properties.get(f"{prefix}_cook_mode")
        temperature = self.properties.get(f"{prefix}_set_temp")
        command = {key: True}
        if mode is not None:
            command[f"{prefix}_cook_mode"] = mode
        if temperature is not None:
            command[f"{prefix}_set_temp"] = temperature
        await self.coordinator.async_set_properties(self._device_id, command)

    @property
    def available(self) -> bool:
        """Return False when the appliance will refuse the command.

        Ovens only accept a remote start once the user has enabled it on the
        unit; publishing an always-enabled button would fail on every press.
        """
        if not super().available:
            return False
        required = self.entity_description.requires
        if required is not None and required.endswith("_remote_ready"):
            return self.properties.get(required) is True
        if self.entity_description.key == "cancel_wash_cycle":
            return self.properties.get("wash_cycle_on") is True or (
                self.properties.get("wash_status") in (1, 2, 3, 7)
            )
        if self.entity_description.key == "wash_cycle_on":
            return self.properties.get("wash_cycle_on") is not True
        return True
