"""Services for Sub-Zero Group operations that have no natural entity.

Most appliance controls map onto an entity: a setpoint is a climate entity, a
mode is a switch. A few do not. Maintenance actions such as the air filter reset
are one-shot commands with no state to display, so they are services.
"""

from __future__ import annotations

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, target as target_helpers

from .capabilities import FAMILY_REFRIGERATION, appliance_family
from .const import DOMAIN
from .coordinator import SubZeroCoordinator

SERVICE_RESET_AIR_FILTER = "reset_air_filter"

RESET_AIR_FILTER_SCHEMA = vol.Schema({}, extra=vol.ALLOW_EXTRA)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's services once per Home Assistant instance."""
    if hass.services.has_service(DOMAIN, SERVICE_RESET_AIR_FILTER):
        return

    async def async_reset_air_filter(call: ServiceCall) -> None:
        """Reset the air filter reminder on the targeted appliances."""
        targets = list(_resolve_targets(hass, call))
        if not targets:
            raise ServiceValidationError(
                "Select at least one Sub-Zero Group refrigeration appliance."
            )
        # Validate every target before writing any of them, so a partly invalid
        # selection does not leave a subset reset.
        for _coordinator, _cloud_id, state in targets:
            _validate_air_filter(state)

        for coordinator, cloud_id, _state in targets:
            await coordinator.async_reset_air_filter(cloud_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_AIR_FILTER,
        async_reset_air_filter,
        schema=RESET_AIR_FILTER_SCHEMA,
    )


def _validate_air_filter(state) -> None:
    """Raise unless the appliance reports a resettable air filter."""
    if state is None or not state.online:
        raise ServiceValidationError("That appliance is offline.")
    if appliance_family(state.properties) != FAMILY_REFRIGERATION:
        raise ServiceValidationError(
            "Only refrigeration appliances have an air filter."
        )
    if "air_filter_pct_remaining" not in state.properties:
        raise ServiceValidationError(
            "That appliance does not report an air filter."
        )


def _resolve_targets(
    hass: HomeAssistant, call: ServiceCall
) -> list[tuple[SubZeroCoordinator, str, object]]:
    """Return (coordinator, cloud id, appliance state) for the call's targets."""
    referenced = target_helpers.async_extract_referenced_entity_ids(
        hass, target_helpers.TargetSelection(call.data), expand_group=False
    )
    device_ids = referenced.referenced_devices
    if not device_ids:
        raise ServiceValidationError("Target at least one appliance device.")

    registry = dr.async_get(hass)

    found: list[tuple[SubZeroCoordinator, str, object]] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        coordinator = getattr(entry, "runtime_data", None)
        if coordinator is None or coordinator.data is None:
            continue
        for cloud_id, state in coordinator.data.appliances.items():
            device = registry.async_get_device_by_identifier(
                (DOMAIN, cloud_id), entry.entry_id
            )
            if device is not None and device.id in device_ids:
                found.append((coordinator, cloud_id, state))
    return found
