"""Capability rules for Sub-Zero Group appliances.

Capabilities are derived from the properties an appliance actually reports in its
cloud snapshot. The app's model-to-type table is not used: the cloud reports a
four-segment ``appliance_type`` that does not match the app's three-segment table,
and the property set is the authoritative description of what a unit can do.
"""

from __future__ import annotations

from typing import Any, Final

# Zone setpoint properties. Each behaves as one climate zone.
ZONE_SETPOINTS: Final[dict[str, str]] = {
    "ref_set_temp": "Refrigerator",
    "frz_set_temp": "Freezer",
    "wine_set_temp": "Zone 1",
    "wine2_set_temp": "Zone 2",
    "crisp_set_temp": "Crisper",
}

# Door sensors per zone.
ZONE_DOORS: Final[dict[str, str]] = {
    "ref_door_ajar": "Refrigerator",
    "frz_door_ajar": "Freezer",
    "wine_door_ajar": "Wine",
}

# Appliance families, detected from the properties present in a snapshot.
FAMILY_OVEN: Final = "oven"
FAMILY_DISHWASHER: Final = "dishwasher"
FAMILY_HOOD: Final = "hood"
FAMILY_REFRIGERATION: Final = "refrigeration"

_OVEN_MARKERS: Final = ("cav_set_temp", "cav_cook_mode", "cav_unit_on")
_DISHWASHER_MARKERS: Final = ("wash_cycle", "wash_status", "wash_cycle_on")
_HOOD_MARKERS: Final = ("fan_speed", "fan_on")


def appliance_family(properties: dict[str, Any]) -> str:
    """Return the appliance family for a property snapshot."""
    if any(key in properties for key in _OVEN_MARKERS):
        return FAMILY_OVEN
    if any(key in properties for key in _DISHWASHER_MARKERS):
        return FAMILY_DISHWASHER
    if any(key in properties for key in _HOOD_MARKERS):
        return FAMILY_HOOD
    return FAMILY_REFRIGERATION


def zones(properties: dict[str, Any]) -> dict[str, str]:
    """Return the climate zones an appliance reports."""
    found = {}
    for key, label in ZONE_SETPOINTS.items():
        # The crisper setpoint is only meaningful in manual mode.
        if key == "crisp_set_temp" and properties.get("crisp_temp_mode") != 0:
            continue
        if isinstance(properties.get(key), int):
            found[key] = label
    return found


def supports(properties: dict[str, Any], key: str) -> bool:
    """Return True when a snapshot carries a property."""
    return key in properties and properties[key] is not None
