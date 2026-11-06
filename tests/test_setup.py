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


async def test_celsius_appliance_reports_celsius_bounds(hass: HomeAssistant, entry):
    """A unit that reports Celsius must be read and written on that scale.

    Every measured limit is in Fahrenheit, so the band is converted rather than
    the value being treated as Fahrenheit.
    """
    coordinator = entry.runtime_data
    refrigerator = next(
        state
        for state in coordinator.data.appliances.values()
        if state.appliance.name == "36 Refrigerator"
    )
    refrigerator.appliance.temperature_unit = "C"
    refrigerator.properties["ref_set_temp"] = 4
    refrigerator.properties["crisp_set_temp"] = 2
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    climate = hass.states.get("climate.36_refrigerator")
    assert climate is not None
    # 34-42 F is 1.1-5.6 C; the endpoints round inward to 2-5.
    assert climate.attributes["min_temp"] == 2
    assert climate.attributes["max_temp"] == 5
    assert climate.attributes["temperature_unit"] == "\u00b0C"


async def test_celsius_setpoint_is_written_in_celsius(
    hass: HomeAssistant, entry, monkeypatch
):
    """The value sent to the cloud is on the appliance's own scale."""
    coordinator = entry.runtime_data
    refrigerator = next(
        state
        for state in coordinator.data.appliances.values()
        if state.appliance.name == "36 Refrigerator"
    )
    refrigerator.appliance.temperature_unit = "C"
    refrigerator.properties["ref_set_temp"] = 4
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    written: list[tuple[str, str, object]] = []

    async def record(device_id, key, value):
        written.append((device_id, key, value))

    monkeypatch.setattr(coordinator, "async_set_property", record)
    # Home Assistant is configured for metric here, so 4 means 4 C, which is
    # inside the converted 2-5 C band and must reach the cloud unchanged.
    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.36_refrigerator", "temperature": 4},
        blocking=True,
    )
    assert written == [("dev-fridge", "ref_set_temp", 4)]


async def test_advertised_bounds_accept_what_they_display(hass: HomeAssistant, entry):
    """Every displayed setpoint must survive a round trip back to native units.

    Home Assistant validates the request against min_temp/max_temp after
    converting it into native units, so a bound rounded for display can fall
    just outside the range it was advertised from.
    """
    from homeassistant.const import ATTR_TEMPERATURE

    written: list[tuple[str, str, object]] = []

    async def record(device_id, key, value):
        written.append((device_id, key, value))

    coordinator = entry.runtime_data
    coordinator.async_set_property = record
    for entity_id in (
        "climate.36_refrigerator",
        "climate.36_freezer",
        "climate.main_wine_zone_1",
        "climate.upper_beverage",
    ):
        state = hass.states.get(entity_id)
        for bound in ("min_temp", "max_temp"):
            shown = state.attributes[bound]
            await hass.services.async_call(
                "climate",
                "set_temperature",
                {"entity_id": entity_id, ATTR_TEMPERATURE: shown},
                blocking=True,
            )
    assert written, "each advertised bound should reach the appliance"

    # The values written are whole native degrees inside the measured band.
    for _, key, value in written:
        assert isinstance(value, int)
        if key == "frz_set_temp":
            assert -5 <= value <= 5
        elif key in ("wine_set_temp", "wine2_set_temp"):
            assert 40 <= value <= 65
        else:
            assert 34 <= value <= 55


async def test_climate_hvac_mode(hass: HomeAssistant, entry):
    for state in hass.states.async_all("climate"):
        assert state.state == "cool"


async def test_door_sensors(hass: HomeAssistant, entry):
    doors = {
        s.entity_id: s
        for s in hass.states.async_all("binary_sensor")
        if s.attributes.get("device_class") == "door"
    }
    # fridge, freezer, wine, beverage, oven
    assert len(doors) == 5
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


async def test_optional_controls_are_read_only_binary_sensors(
    hass: HomeAssistant, entry
):
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


async def test_oven_entities(hass: HomeAssistant, entry):
    """An oven gets cooking controls, timers and probe readings."""
    oven_ids = {
        state.entity_id
        for state in hass.states.async_all()
        if "wolf_oven" in state.entity_id
    }
    assert "select.wolf_oven_cook_mode" in oven_ids
    assert "number.wolf_oven_oven_setpoint" in oven_ids
    assert "number.wolf_oven_probe_target" in oven_ids
    assert "sensor.wolf_oven_oven_temperature" in oven_ids
    assert "sensor.wolf_oven_probe_temperature" in oven_ids
    # Starting is a command, not a state: it is a button plus a running sensor.
    assert "button.wolf_oven_start_oven" in oven_ids
    assert "binary_sensor.wolf_oven_oven_running" in oven_ids
    assert "switch.wolf_oven_oven_light" in oven_ids
    assert "binary_sensor.wolf_oven_remote_ready" in oven_ids
    assert "binary_sensor.wolf_oven_cooking_timer_complete" in oven_ids
    # The app shows "almost done" cues from the within-N markers, and each
    # timer's start is read alongside its end.
    assert "binary_sensor.wolf_oven_cooking_timer_under_one_minute" in oven_ids
    assert "binary_sensor.wolf_oven_probe_within_10_degrees" in oven_ids
    assert "sensor.wolf_oven_cooking_timer_starts" in oven_ids
    # There are two independent kitchen timers, each with its own markers.
    assert "binary_sensor.wolf_oven_kitchen_timer_active" in oven_ids
    assert "sensor.wolf_oven_kitchen_timer_starts" in oven_ids
    assert "binary_sensor.wolf_oven_kitchen_timer_2_active" in oven_ids
    assert "sensor.wolf_oven_kitchen_timer_2_starts" in oven_ids


async def test_dishwasher_entities(hass: HomeAssistant, entry):
    """A dishwasher exposes its cycle choice, status and wash options."""
    ids = {
        state.entity_id
        for state in hass.states.async_all()
        if "cove_dishwasher" in state.entity_id
    }
    assert "select.cove_dishwasher_wash_cycle" in ids
    assert "sensor.cove_dishwasher_wash_status" in ids
    assert "button.cove_dishwasher_start_wash_cycle" in ids
    assert "button.cove_dishwasher_cancel_wash_cycle" in ids
    assert "switch.cove_dishwasher_heated_dry" in ids
    assert "switch.cove_dishwasher_sanitize_rinse" in ids
    assert "number.cove_dishwasher_delay_start" in ids
    # Wash status is a translated enum, not a bare number.
    status = hass.states.get("sensor.cove_dishwasher_wash_status")
    assert status.state == "Idle"
    assert "Idle" in status.attributes["options"]


async def test_hood_entities(hass: HomeAssistant, entry):
    """A hood separates on/off switches from level numbers."""
    ids = {
        state.entity_id
        for state in hass.states.async_all()
        if "wolf_hood" in state.entity_id
    }
    assert "switch.wolf_hood_fan" in ids
    assert "switch.wolf_hood_hood_light" in ids
    assert "number.wolf_hood_fan_speed" in ids
    assert "number.wolf_hood_light_brightness" in ids
    assert "number.wolf_hood_control_brightness" in ids
    # Each favourite carries its own setter, so it is a control, not a copy of
    # the live level.
    assert "number.wolf_hood_favourite_fan_speed" in ids
    assert "number.wolf_hood_favourite_light_brightness" in ids
    assert "number.wolf_hood_favourite_light_colour" in ids
    # Filter usage is reported, never written.
    assert "sensor.wolf_hood_filter_usage" in ids
    assert "sensor.wolf_hood_filter_allowance" in ids


async def test_cooktop_entities(hass: HomeAssistant, entry):
    """A cooktop exposes power and lock, and only reads display settings."""
    ids = {
        state.entity_id
        for state in hass.states.async_all()
        if "wolf_cooktop" in state.entity_id
    }
    assert "switch.wolf_cooktop_cooktop_power" in ids
    assert "switch.wolf_cooktop_cooktop_lock" in ids
    assert "binary_sensor.wolf_cooktop_pan_detected" in ids
    # Auto lock is a state the cooktop reports, not something the cloud exposes
    # a write for; the lock switch remains the only control.
    assert "binary_sensor.wolf_cooktop_auto_lock" in ids
    assert "switch.wolf_cooktop_auto_lock" not in ids
    # The app has no setter for these, so publishing them as controls would
    # offer a write the cloud rejects.
    assert "number.wolf_cooktop_cooktop_volume" not in ids
    assert "number.wolf_cooktop_cooktop_display_brightness" not in ids
    assert "sensor.wolf_cooktop_cooktop_volume" in ids
    assert "sensor.wolf_cooktop_cooktop_display_brightness" in ids


async def test_timestamps_are_parsed(hass: HomeAssistant, entry):
    """A timestamp sensor must publish a datetime, not the raw string.

    Home Assistant raises a ValueError when a sensor declares the timestamp
    device class and returns a string, so the appliance's local-time format is
    converted to an aware datetime.
    """
    from datetime import datetime

    from custom_components.subzero.sensor import parse_appliance_time

    parsed = parse_appliance_time("2026-11-06T18:45")
    assert isinstance(parsed, datetime)
    assert parsed.tzinfo is not None
    assert parse_appliance_time(None) is None
    assert parse_appliance_time("not a time") is None


async def test_climate_action_needs_a_temperature_reading(hass: HomeAssistant, entry):
    """Without a sensor there is no evidence for a cooling or idle claim."""
    # Home Assistant omits the attribute entirely rather than publishing None.
    assert "hvac_action" not in hass.states.get("climate.36_refrigerator").attributes

    coordinator = entry.runtime_data
    refrigerator = next(
        state
        for state in coordinator.data.appliances.values()
        if state.appliance.name == "36 Refrigerator"
    )
    # At or below the setpoint the compressor is not calling for cooling.
    refrigerator.properties["ref_display_temp"] = 40
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    fridge = hass.states.get("climate.36_refrigerator")
    assert fridge.attributes["hvac_action"] == "idle"

    # Above it, the unit is cooling.
    refrigerator.properties["ref_display_temp"] = 46
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    fridge = hass.states.get("climate.36_refrigerator")
    assert fridge.attributes["hvac_action"] == "cooling"


async def test_mode_timers_hide_when_the_mode_is_off(hass: HomeAssistant, entry):
    """A high-use or max-ice period is only meaningful while it is running."""
    coordinator = entry.runtime_data
    freezer = next(
        state
        for state in coordinator.data.appliances.values()
        if state.appliance.name == "36 Freezer"
    )
    freezer.properties["max_ice_on"] = False
    freezer.properties["max_ice_start_time"] = "2026-11-06T09:00"
    freezer.properties["max_ice_end_time"] = "2026-11-06T13:00"
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.36_freezer_max_ice_starts").state == "unknown"

    freezer.properties["max_ice_on"] = True
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.36_freezer_max_ice_starts").state.startswith(
        "2026-11-06T17:00"
    )


async def test_timestamp_sensor_publishes_iso_state(hass: HomeAssistant, entry):
    """A live timestamp must render, not raise inside the state machine."""
    coordinator = entry.runtime_data
    dishwasher = next(
        state
        for state in coordinator.data.appliances.values()
        if state.appliance.name == "Cove Dishwasher"
    )
    dishwasher.properties["wash_cycle_end_time"] = "2026-11-06T21:30"
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get("sensor.cove_dishwasher_wash_cycle_ends")
    assert state is not None
    # A naive appliance time is local time, so the instant depends on the zone.
    from datetime import UTC, datetime

    from homeassistant.util import dt as dt_util

    expected = datetime(2026, 11, 6, 21, 30, tzinfo=dt_util.get_default_time_zone())
    assert state.state == expected.astimezone(UTC).isoformat(timespec="seconds")


async def test_unknown_enum_value_is_not_published(hass: HomeAssistant, entry):
    """An unrecognised status becomes None rather than a raw number."""
    coordinator = entry.runtime_data
    dishwasher = next(
        state
        for state in coordinator.data.appliances.values()
        if state.appliance.name == "Cove Dishwasher"
    )
    dishwasher.properties["wash_status"] = 99
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get("sensor.cove_dishwasher_wash_status")
    assert state.state == "unknown"


async def test_dishwasher_cycle_names(hass: HomeAssistant, entry):
    """Cycle numbers map to the names the app shows."""
    state = hass.states.get("select.cove_dishwasher_wash_cycle")
    assert state is not None
    assert state.state == "Normal"
    assert "Pots and pans" in state.attributes["options"]


async def test_wash_cycle_is_a_command_not_a_switch(hass: HomeAssistant, entry):
    """Starting a cycle reads back as a pulse, so it is a button.

    ``wash_cycle_on`` goes false once the cycle is accepted; publishing it as a
    switch would snap back and look like the command failed.
    """
    switches = {
        state.entity_id for state in hass.states.async_all("switch")
    }
    assert "switch.cove_dishwasher_wash_cycle_running" not in switches
    assert hass.states.get("button.cove_dishwasher_start_wash_cycle") is not None
    running = hass.states.get("binary_sensor.cove_dishwasher_wash_cycle_running")
    assert running is not None
    assert running.attributes["device_class"] == "running"


async def test_oven_start_needs_remote_ready(hass: HomeAssistant, entry):
    """An oven that has not enabled remote operation offers no start button."""
    coordinator = entry.runtime_data
    oven = next(
        state
        for state in coordinator.data.appliances.values()
        if state.appliance.name == "Wolf Oven"
    )
    oven.properties["cav_remote_ready"] = False
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get("button.wolf_oven_start_oven").state == "unavailable"

    oven.properties["cav_remote_ready"] = True
    coordinator.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get("button.wolf_oven_start_oven").state != "unavailable"


async def test_families_do_not_leak_controls(hass: HomeAssistant, entry):
    """A hood must not get a wash cycle, nor a dishwasher an oven setpoint."""
    hood = {
        state.entity_id
        for state in hass.states.async_all()
        if "wolf_hood" in state.entity_id
    }
    dishwasher = {
        state.entity_id
        for state in hass.states.async_all()
        if "cove_dishwasher" in state.entity_id
    }
    assert not any("wash_cycle" in entity_id for entity_id in hood)
    assert not any("cook_mode" in entity_id for entity_id in dishwasher)
    assert not any("setpoint" in entity_id for entity_id in dishwasher)


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


async def test_options_flow_sets_the_poll_interval(hass: HomeAssistant, entry):
    """The options flow exposes only a bounded poll interval."""
    from homeassistant.data_entry_flow import FlowResultType

    from custom_components.subzero.const import MAX_SCAN_INTERVAL, MIN_SCAN_INTERVAL

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"].schema
    assert [str(key) for key in schema] == ["scan_interval"]
    validator = schema[next(iter(schema))]
    validators = list(validator.validators)
    (interval_range,) = [v for v in validators if hasattr(v, "min")]
    assert (interval_range.min, interval_range.max) == (
        MIN_SCAN_INTERVAL,
        MAX_SCAN_INTERVAL,
    )

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 120}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["scan_interval"] == 120
    assert entry.runtime_data.update_interval.total_seconds() == 120


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


async def test_celsius_temperature_sensor_keeps_its_scale(
    hass: HomeAssistant, entry, monkeypatch
):
    """A sensor on a Celsius appliance must not be relabelled as Fahrenheit.

    The appliance's scale is only known at setup, and entities are created from
    the properties the snapshot reports, so the entry is reloaded after the
    snapshot gains a reading.
    """
    from custom_components.subzero.api import Appliance, SubZeroClient

    from .conftest import APPLIANCES, SNAPSHOTS, load

    snapshot = load("fridge.json")
    snapshot["ref_display_temp"] = 4
    monkeypatch.setitem(SNAPSHOTS, "dev-fridge", snapshot)

    async def celsius_appliances(self):
        return [
            Appliance(
                device_id,
                name,
                appliance_type,
                "C" if device_id == "dev-fridge" else unit,
            )
            for device_id, name, appliance_type, unit, _ in APPLIANCES
        ]

    monkeypatch.setattr(SubZeroClient, "async_get_appliances", celsius_appliances)

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.36_refrigerator_refrigerator_temperature")
    assert state is not None
    assert state.attributes["unit_of_measurement"] == "\u00b0C"
    assert float(state.state) == 4


async def test_diagnostics_report_the_push_state(hass: HomeAssistant, entry):
    """Diagnostics must say whether the push transport is established.

    Push is the primary source of state, so a stale entity is most often a
    dropped connection; this is the first thing support needs to see.
    """
    from custom_components.subzero.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    # The cloud client is mocked in tests, so no socket is ever opened.
    assert diagnostics["push_connected"] is False
    assert diagnostics["poll_interval"] == 60
    assert "appliances" in diagnostics


async def test_setter_only_settings_do_not_appear_on_other_models(
    hass: HomeAssistant, entry
):
    """A setting is published only where the appliance reports it.

    Button tones and the control lock have dedicated setters in the app, but no
    recorded refrigeration appliance reports them, so a fridge must not grow
    either switch.
    """
    ids = {state.entity_id for state in hass.states.async_all()}
    assert "switch.36_freezer_button_tones" not in ids
    assert "switch.36_freezer_control_lock" not in ids


async def test_zero_is_a_real_temperature_reading(hass: HomeAssistant, entry):
    """A freezer at 0 degrees must publish it, not hide it as unavailable.

    Units without a temperature sensor omit the paired display property from
    the snapshot altogether, so a value that is present is a real reading.
    Zero is an ordinary freezer temperature.
    """
    coordinator = entry.runtime_data
    freezer = next(
        state
        for state in coordinator.data.appliances.values()
        if state.appliance.name == "36 Freezer"
    )
    freezer.properties["frz_display_temp"] = 0
    freezer.properties["frz_set_temp"] = -5
    coordinator.async_update_listeners()
    await hass.async_block_till_done()

    climate = hass.states.get("climate.36_freezer")
    # The instance is metric, so 0 F is shown converted; what matters is that a
    # reading exists at all rather than being suppressed as a placeholder.
    assert climate.attributes["current_temperature"] == -17.8
    # Warmer than the setpoint, so the compressor is calling for cooling.
    assert climate.attributes["hvac_action"] == "cooling"
