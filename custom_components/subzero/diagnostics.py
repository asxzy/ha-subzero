"""Diagnostics support for the Sub-Zero Group integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PRIVATE_KEYS

# Account identifiers and appliance serials are not useful for support and can
# be used to impersonate an appliance registration.
REDACT_ACCOUNT = {"tokens", "username", "user_id", "access_token", "refresh_token"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    The raw appliance snapshot is included because it is the only way to see
    which properties a particular model reports, which is what most capability
    questions come down to.
    """
    coordinator = entry.runtime_data
    appliances: dict[str, Any] = {}
    for device_id, state in coordinator.data.appliances.items():
        properties = {
            key: value
            for key, value in state.properties.items()
            if key not in PRIVATE_KEYS
        }
        appliances[state.appliance.name] = {
            "device_id": device_id,
            "appliance_type": state.appliance.appliance_type,
            "temperature_unit": state.appliance.temperature_unit,
            "online": state.online,
            "properties": properties,
        }

    return {
        "entry": {
            "title": entry.title,
            "domain": DOMAIN,
            "version": entry.version,
            "options": dict(entry.options),
        },
        "poll_interval": (
            coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None
        ),
        # Push is the primary transport; this shows whether it is established,
        # which is the first thing to check when state looks stale.
        "push_connected": (
            coordinator.push.connected if coordinator.push is not None else False
        ),
        "push_last_error": (
            coordinator.push.last_error if coordinator.push is not None else None
        ),
        "push_attempts": (
            coordinator.push.attempts if coordinator.push is not None else 0
        ),
        "push_connected_at": (
            coordinator.push.connected_at if coordinator.push is not None else None
        ),
        "last_update_success": coordinator.last_update_success,
        "appliances": async_redact_data(appliances, {"appliance_serial"}),
        "account": async_redact_data(
            {"data": dict(entry.data)}, REDACT_ACCOUNT
        ),
    }
