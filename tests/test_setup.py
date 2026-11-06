"""Integration load and entity tests against recorded snapshots."""

from __future__ import annotations

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from custom_components.subzero.const import DOMAIN

from .conftest import SNAPSHOTS, tokens


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


async def test_wine_zone_setpoints(hass: HomeAssistant, entry):
    # A multi-zone appliance names its zones "Zone 1"/"Zone 2"; the device prefix
    # identifies which appliance they belong to.
    wine = [
        s
        for s in hass.states.async_all("climate")
        if s.entity_id.startswith("climate.main_wine")
    ]
    assert len(wine) == 2
    assert sorted(round(s.attributes["temperature"], 1) for s in wine) == [6.7, 12.8]


async def test_offline_appliance_degrades_to_unavailable(hass: HomeAssistant, entry):
    """An offline appliance must not break the integration."""
    from custom_components.subzero.api import SubZeroApiError

    coordinator = entry.runtime_data
    assert coordinator is not None
    # Beverage center reports offline through an IoT Hub 404.
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
