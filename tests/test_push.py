"""Tests for the SignalR push transport.

The wire format was captured from the live hub, so these tests replay real
frames: the outer ``ConnectedApplianceMessage`` invocation, the JSON payload
inside it, and the ``api.async_channel`` document inside that.
"""

from __future__ import annotations

import json

import pytest

from custom_components.subzero.push import channel_update, handle_invocation


def wrap(
    device_id: str,
    channel: dict | str,
    *,
    target: str = "ConnectedApplianceMessage",
):
    """Build a hub frame around a channel document, as the service does."""
    inner = channel if isinstance(channel, str) else json.dumps(channel)
    payload = {"api.async_channel": inner, "timezone_id_name": "Mountain Standard Time"}
    outer = {"DeviceId": device_id, "Payload": json.dumps(payload), "id": "abc"}
    message = {"type": 1, "target": target, "arguments": [json.dumps(outer)]}
    return json.dumps(message) + "\x1e"


SNAPSHOT = {
    "type": 1,
    "pload": {
        "unit_on": True,
        "frz_set_temp": 0,
        "frz_door_ajar": False,
        "appliance_model": "DEC3650FI",
    },
}

DELTA = {
    "type": 2,
    "pload": {
        "seq": 666,
        "timestamp": "2026-11-06T13:59:35.501-07:00",
        "props": {"night_ice_on": True},
        "msg_types": 2,
    },
}


def test_snapshot_frame_is_decoded():
    """A type-1 channel carries the whole snapshot."""
    got = handle_invocation(wrap("dev-1", SNAPSHOT).rstrip("\x1e"))
    assert got is not None
    device_id, channel = got
    assert device_id == "dev-1"
    assert channel_update(channel) == ("snapshot", SNAPSHOT["pload"])


def test_delta_frame_is_decoded():
    """A type-2 channel carries only the changed properties."""
    got = handle_invocation(wrap("dev-1", DELTA).rstrip("\x1e"))
    assert got is not None
    assert channel_update(got[1]) == ("delta", {"night_ice_on": True})


def test_trailing_separator_is_tolerated():
    """Frames end with the record separator; both forms must decode."""
    frame = wrap("dev-1", DELTA)
    assert frame.endswith("\x1e")
    assert handle_invocation(frame.rstrip("\x1e")) is not None


def test_delta_without_props_is_not_an_update():
    """A sequence-only delta must not be read as an empty change set."""
    channel = {"type": 2, "pload": {"seq": 700, "props": None}}
    assert channel_update(channel) is None


def test_unknown_channel_type_is_ignored():
    assert channel_update({"type": 99, "pload": {"props": {"a": 1}}}) is None


def test_unknown_target_is_ignored():
    """Only ConnectedApplianceMessage carries appliance state."""
    assert handle_invocation(wrap("dev-1", DELTA, target="SomeOtherMessage")) is None


def test_keepalive_and_ack_are_ignored():
    assert handle_invocation(json.dumps({"type": 6})) is None
    assert handle_invocation("{}") is None


def test_non_invocation_message_is_ignored():
    """A completion (type 3) is not an invocation and must be skipped."""
    frame = json.dumps({"type": 3, "invocationId": "1", "result": {}})
    assert handle_invocation(frame) is None


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        json.dumps({"type": 1, "target": "ConnectedApplianceMessage"}),
        json.dumps({"type": 1, "target": "ConnectedApplianceMessage", "arguments": []}),
        json.dumps(
            {"type": 1, "target": "ConnectedApplianceMessage", "arguments": ["{}"]}
        ),
        json.dumps(
            {
                "type": 1,
                "target": "ConnectedApplianceMessage",
                "arguments": [json.dumps({"DeviceId": "dev-1"})],
            }
        ),
    ],
)
def test_malformed_frames_do_not_raise(raw):
    """No frame shape from the wire may propagate an exception."""
    assert handle_invocation(raw) is None


# --- coordinator integration -------------------------------------------------


class _FakeCoordinator:
    """Stand-in exposing just the push callbacks under test."""

    def __init__(self, data):
        from custom_components.subzero.coordinator import SubZeroCoordinator

        self.data = data
        self.updates = 0
        # Bind the real methods so the tests exercise production code.
        self._push_snapshot = SubZeroCoordinator._push_snapshot.__get__(self)
        self._push_delta = SubZeroCoordinator._push_delta.__get__(self)

    def async_update_listeners(self):
        self.updates += 1


def _account(properties):
    from custom_components.subzero.api import Appliance
    from custom_components.subzero.coordinator import ApplianceState, SubZeroData

    appliance = Appliance("dev-1", "Unit", "17.17.5.0", "F")
    state = ApplianceState(appliance=appliance, properties=dict(properties))
    return SubZeroData(appliances={"dev-1": state}), state


def test_snapshot_replaces_the_cached_state():
    """A pushed snapshot is authoritative, including properties that disappear."""
    data, state = _account({"unit_on": True, "gone": 1})
    coordinator = _FakeCoordinator(data)

    coordinator._push_snapshot("dev-1", {"unit_on": False})

    assert state.properties == {"unit_on": False}
    assert coordinator.updates == 1


def test_delta_merges_into_the_cached_state():
    """A pushed change set only touches the properties it carries."""
    data, state = _account({"unit_on": True, "frz_set_temp": 0})
    coordinator = _FakeCoordinator(data)

    coordinator._push_delta("dev-1", {"frz_set_temp": 3})

    assert state.properties == {"unit_on": True, "frz_set_temp": 3}
    assert coordinator.updates == 1


def test_push_for_an_unknown_device_is_ignored():
    """Frames for an appliance outside the account must not create entries."""
    data, _ = _account({"unit_on": True})
    coordinator = _FakeCoordinator(data)

    coordinator._push_snapshot("other", {"unit_on": False})
    coordinator._push_delta("other", {"unit_on": False})

    assert list(data.appliances) == ["dev-1"]
    assert coordinator.updates == 0


def test_push_marks_a_quiet_appliance_online():
    """A frame proves the appliance is reachable again."""
    data, state = _account({"unit_on": True})
    state.online = False
    coordinator = _FakeCoordinator(data)

    coordinator._push_delta("dev-1", {"unit_on": False})

    assert state.online is True
