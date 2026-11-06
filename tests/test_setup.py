"""Integration load and entity tests against recorded snapshots."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.subzero.const import DOMAIN

from .conftest import tokens


@pytest.fixture
async def entry(hass: HomeAssistant):
    """Set up the integration with a mock config entry."""
    from pytest_homeassistant.common import MockConfigEntry

    mock = MockConfigEntry(
        domain=DOMAIN,
        data={"tokens": tokens(), "username": "a@b.c"},
        unique_id="account-1",
    )
    mock.add_to_hass(hass)
    await hass.config_entries.async_setup(mock.entry_id)
    await hass.async_block_till_done()
    return mock


async def test_entry_loads(entry):
    assert entry.state is ConfigEntryState.LOADED


async def test_climate_zones(hass: HomeAssistant, entry):
    climates = hass.states.async_all("climate")
    # wine unit has 2 zones, fridge 1, freezer 1, beverage 1
    assert len(climates) == 5


async def test_climate_temperatures(hass: HomeAssistant, entry):
    states = {s.entity_id: s for s in hass.states.async_all("climate")}
    assert len(states) == 5
    # The cloud reports whole degrees Fahrenheit; Home Assistant converts the
    # reported value to the unit system configured for the instance (metric).
    targets = sorted(round(s.attributes["temperature"], 1) for s in states.values())
    assert targets == [-17.8, 5.6, 6.1, 6.7, 12.8]


async def test_climate_limits_come_from_appliance(hass: HomeAssistant, entry):
    """Each zone advertises the range its own model accepts."""
    wine = hass.states.get("climate.main_wine_zone_1")
    fridge = hass.states.get("climate.36_refrigerator")
    assert wine is not None and fridge is not None
    # 40-65 F wine, 34-42 F refrigerator column, converted to Celsius.
    assert round(wine.attributes["min_temp"], 1) == 4.4
    assert round(wine.attributes["max_temp"], 1) == 18.3
    assert round(fridge.attributes["min_temp"], 1) == 1.1
    assert round(fridge.attributes["max_temp"], 1) == 5.6


async def test_climate_hvac_mode(hass: HomeAssistant, entry):
    for state in hass.states.async_all("climate"):
        assert state.state == "cool"


async def test_door_sensors(hass: HomeAssistant, entry):
    doors = {
        s.entity_id: s
        for s in hass.states.async_all("binary_sensor")
        if s.attributes.get("device_class") == "door"
    }
    assert len(doors) == 4  # fridge, freezer, wine, beverage
    assert all(d.state == "off" for d in doors.values())


async def test_boolean_switches(hass: HomeAssistant, entry):
    switches = {s.entity_id for s in hass.states.async_all("switch")}
    assert switches, "expected at least one switch"
    assert all(s.state in ("on", "off") for s in hass.states.async_all("switch"))


async def test_read_only_properties_are_not_switches(hass: HomeAssistant, entry):
    """Properties the cloud rejects writes for must not be exposed as controls."""
    switches = {s.entity_id for s in hass.states.async_all("switch")}
    for name in ("smart_grid", "pairing_window", "wine_temperature_alert"):
        assert not any(name in entity_id for entity_id in switches), name


async def test_wine_zone_setpoints(hass: HomeAssistant, entry):
    # A multi-zone appliance names its zones "Zone 1"/"Zone 2".
    wine = [
        s
        for s in hass.states.async_all("climate")
        if s.entity_id.startswith("climate.main_wine")
    ]
    assert len(wine) == 2
    assert sorted(round(s.attributes["temperature"], 1) for s in wine) == [6.7, 12.8]


async def test_no_duplicate_controls(hass: HomeAssistant, entry):
    """A writable value must not also be published as a read-only binary sensor.

    The cloud reports the same property for both the control and the state, so
    an overlap would show the same value twice and let the two entities drift.
    """
    switches = {state.entity_id for state in hass.states.async_all("switch")}
    binaries = {state.entity_id for state in hass.states.async_all("binary_sensor")}
    overlaps = switches & {
        entity_id.replace("binary_sensor.", "switch.") for entity_id in binaries
    }
    assert not overlaps


async def test_uptime_is_a_diagnostic_entity(hass: HomeAssistant, entry):
    """Uptime ships disabled by default, so it has no state until enabled."""
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    row = registry.async_get("sensor.36_refrigerator_uptime")
    assert row is not None
    assert row.disabled_by is not None


async def test_optional_controls_are_read_only_binary_sensors(hass: HomeAssistant, entry):
    """States the cloud refuses to write are published as read-only sensors.

    Both ship disabled by default because they are diagnostics, so the registry
    row rather than the state machine is what proves they exist.
    """
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for name in ("smart_grid", "pairing_window"):
        row = registry.async_get(f"binary_sensor.36_freezer_{name}")
        assert row is not None, name
        assert row.domain == "binary_sensor"
        assert registry.async_get(f"switch.36_freezer_{name}") is None


async def test_accent_light_is_a_select(hass: HomeAssistant, entry):
    """The accent light is an enum (off/on and brightness steps), not a level."""
    state = hass.states.get("select.upper_beverage_accent_light")
    assert state is not None
    assert set(state.attributes["options"]) == {"Off", "On", "Low", "Medium", "High"}


async def test_door_open_delay_is_a_number(hass: HomeAssistant, entry):
    """The cloud accepts any integer minutes, so the delay is a number entity."""
    state = hass.states.get("number.36_freezer_door_open_delay")
    assert state is not None
    assert round(state.attributes["min"]) == 0
    assert round(state.attributes["max"]) == 30


async def test_reset_air_filter_service_is_registered(hass: HomeAssistant, entry):
    """The filter reset has no state to publish, so it is offered as a service."""
    assert hass.services.has_service(DOMAIN, "reset_air_filter")


async def test_reset_air_filter_needs_an_air_filter(hass: HomeAssistant, entry):
    """The service must reject appliances that do not report a filter."""
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import device_registry as dr

    coordinator = entry.runtime_data
    freezer = next(
        appliance
        for appliance in coordinator.appliances.values()
        if appliance.name == "36 Freezer"
    )
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, freezer.device_id), entry.entry_id
    )
    assert device is not None
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "reset_air_filter",
            {"device_id": device.id},
            blocking=True,
        )


async def test_reset_air_filter_requires_a_target(hass: HomeAssistant, entry):
    """Calling the service with no device selected is a validation error."""
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "reset_air_filter", {}, blocking=True)


def test_parse_uptime_handles_truncation():
    """The firmware truncates uptime to eight characters after 100 hours.

    A three-digit hour field plus a truncated seconds digit is padded with a
    zero, so ``685:39:5`` is 685 h 39 min 50 s rather than 5 s.
    """
    from custom_components.subzero.sensor import parse_uptime

    assert parse_uptime("685:39:5") == 685 * 3600 + 39 * 60 + 50
    assert parse_uptime("758:03:4") == 758 * 3600 + 3 * 60 + 40
    # A fully reported value is read literally.
    assert parse_uptime("12:34:56") == 12 * 3600 + 34 * 60 + 56
    assert parse_uptime("garbage") is None
    assert parse_uptime(None) is None


async def test_offline_appliance_degrades_to_unavailable(hass: HomeAssistant, entry):
    """An offline appliance must not break the integration."""
    coordinator = entry.runtime_data
    assert coordinator is not None
    assert "dev-beverage" in coordinator.appliances


async def test_unload(entry, hass: HomeAssistant):
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    # Home Assistant keeps registry-backed states after an unload and marks them
    # unavailable instead of deleting them.
    climates = hass.states.async_all("climate")
    assert climates
    assert all(state.state == STATE_UNAVAILABLE for state in climates)
