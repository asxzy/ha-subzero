"""Capability rules for Sub-Zero Group appliances.

Capabilities are derived from two sources of evidence:

* the properties an appliance reports in its live cloud snapshot, which is
  authoritative for what a unit can display and control;
* the setpoint limits, which were measured by writing candidate values to real
  hardware and recording what the cloud accepted or rejected.

The appliance type is only used where a limit genuinely differs by model. The
cloud reports four segments (``17.17.4.0``); dropping the group prefix leaves
the three segments the Owner's App uses for its own model table and metadata
class names (``S17C4V0Metadata``).
"""

from __future__ import annotations

from typing import Any, Final

# Zone setpoint properties. Each behaves as one climate zone.
ZONE_SETPOINTS: Final[dict[str, str]] = {
    "ref_set_temp": "Refrigerator",
    "ref2_set_temp": "Refrigerator drawer",
    "frz_set_temp": "Freezer",
    "wine_set_temp": "Zone 1",
    "wine2_set_temp": "Zone 2",
    "crisp_set_temp": "Crisper",
}

# Door sensors per zone.
ZONE_DOORS: Final[dict[str, str]] = {
    "ref_set_temp": "ref_door_ajar",
    "ref2_set_temp": "ref2_door_ajar",
    "frz_set_temp": "frz_door_ajar",
    "wine_set_temp": "wine_door_ajar",
    "wine2_set_temp": "wine2_door_ajar",
    "crisp_set_temp": "ref_door_ajar",
}

# Appliance families, detected from the properties present in a snapshot.
FAMILY_OVEN: Final = "oven"
FAMILY_DISHWASHER: Final = "dishwasher"
FAMILY_HOOD: Final = "hood"
FAMILY_COOKTOP: Final = "cooktop"
FAMILY_REFRIGERATION: Final = "refrigeration"

_OVEN_MARKERS: Final = ("cav_set_temp", "cav_cook_mode", "cav_unit_on")
_DISHWASHER_MARKERS: Final = ("wash_cycle", "wash_status", "wash_cycle_on")
_HOOD_MARKERS: Final = ("fan_speed", "fan_on", "halo_max_percent")
_COOKTOP_MARKERS: Final = ("cooktop_on", "cooktop_lock_on", "cooktop_pan_detected")

# Properties an appliance reports but rejects on write. Exposing a control for
# one of these produces an entity that fails every time it is used, so they are
# published as read-only indicators instead.
READ_ONLY_PROPERTIES: Final[frozenset[str]] = frozenset(
    {
        "smart_grid_on",
        "pin_window_open",
        "service_required",
        "service_mode",
        "wine_temp_alert_on",
        "active_faults",
    }
)

# Booleans that change an operating mode. These get a switch rather than a
# binary sensor so the same value is not published twice.
MODE_SWITCHES: Final[dict[str, str]] = {
    "unit_on": "Power",
    "sabbath_on": "Sabbath mode",
    "ice_maker_on": "Ice maker",
    "max_ice_on": "Max ice",
    "night_ice_on": "Night ice",
    "ice_maker_clean_on": "Ice maker clean",
    "air_filter_on": "Air filter reminder",
    "high_use_on": "High use mode",
    "short_vacation_on": "Short vacation",
    "long_vacation_on": "Long vacation",
    "winterize_on": "Winterize",
    "internal_dispenser_enabled": "Internal dispenser",
    "cav_light_on": "Oven light",
    "cav2_light_on": "Lower oven light",
    "heated_dry_on": "Heated dry",
    "extended_dry_on": "Extended dry",
    "high_temp_wash_on": "High temperature wash",
    "sani_rinse_on": "Sanitize rinse",
    "top_rack_only_on": "Top rack only",
    # Hoods expose a fan and light as switches, with the level on separate
    # number entities.
    "fan_on": "Fan",
    "light_on": "Hood light",
    "color_on": "Hood light colour",
    "cooktop_on": "Cooktop power",
    "cooktop_lock_on": "Cooktop lock",
}


def appliance_family(properties: dict[str, Any]) -> str:
    """Return the appliance family for a property snapshot."""
    if any(key in properties for key in _OVEN_MARKERS):
        return FAMILY_OVEN
    if any(key in properties for key in _DISHWASHER_MARKERS):
        return FAMILY_DISHWASHER
    if any(key in properties for key in _HOOD_MARKERS):
        return FAMILY_HOOD
    if any(key in properties for key in _COOKTOP_MARKERS):
        return FAMILY_COOKTOP
    return FAMILY_REFRIGERATION


def appliance_type_parts(properties: dict[str, Any]) -> tuple[int, int, int] | None:
    """Return the (series, category, version) tuple for an appliance.

    The cloud reports a four-segment type such as ``17.17.4.0``. The Owner's App
    maps models to three segments (``DEC3650R/L`` -> ``17.4.0``), and the cloud
    value is that mapping with the leading ``17`` group prefix restored. Metadata
    classes in the app are named after the remaining three segments
    (``S17C4V0Metadata``), which confirms the alignment.
    """
    value = properties.get("appliance_type")
    if not isinstance(value, str):
        return None
    parts = value.split(".")
    if len(parts) == 4:
        # Drop the group prefix to get (series, category, version).
        parts = parts[1:]
    if len(parts) != 3 or not all(part.isascii() and part.isdecimal() for part in parts):
        return None
    return int(parts[0]), int(parts[1]), int(parts[2])


def zones(properties: dict[str, Any]) -> dict[str, str]:
    """Return the climate zones an appliance reports."""
    found: dict[str, str] = {}
    for key, label in ZONE_SETPOINTS.items():
        # The crisper setpoint is only meaningful in manual mode.
        if key == "crisp_set_temp" and properties.get("crisp_temp_mode") != 0:
            continue
        # A freezer that is running Max ice reports a frozen setpoint of zero
        # while it is driven by the ice routine; the zone is still real.
        if isinstance(properties.get(key), (int, float)) and not isinstance(
            properties.get(key), bool
        ):
            found[key] = label
    return found


def temperature_range(
    key: str, properties: dict[str, Any]
) -> tuple[int, int] | None:
    """Return the accepted setpoint range for a zone.

    Limits were measured against live appliances: each candidate value was
    written to the cloud and the accept/reject result recorded.
    """
    if key == "frz_set_temp":
        return -5, 5
    if key in ("wine_set_temp", "wine2_set_temp"):
        return 40, 65
    if key == "crisp_set_temp":
        # The crisper tracks the refrigerator setpoint within a narrow band.
        # Measured: with ref_set_temp=38 the cloud accepted 36-40; with 42 it
        # accepted 40-42, so the band is ref-2 .. ref.
        bounds = temperature_range("ref_set_temp", properties)
        refrigerator = properties.get("ref_set_temp")
        if bounds is None or not isinstance(refrigerator, (int, float)):
            return None
        lower = max(bounds[0], int(refrigerator) - 2)
        upper = min(bounds[1], int(refrigerator))
        return (lower, upper) if lower <= upper else None
    if key in ("ref_set_temp", "ref2_set_temp"):
        parts = appliance_type_parts(properties)
        if parts is not None:
            series, category, _version = parts
            # Beverage centres (13.3 / 13.6) reach 55 F; refrigeration columns and
            # wine columns stop at 42 F. Measured: 34-42 on 17.13.3.1 and
            # 34-55 on 17.17.4.0's neighbour 17.13.3.1, see tests.
            if series == 13 and category in (3, 6):
                return 34, 55
            if series in (1, 2, 22):
                return 34, 45
        return 34, 42
    return None


def supports(properties: dict[str, Any], key: str) -> bool:
    """Return True when a snapshot carries a property."""
    return key in properties and properties[key] is not None
