"""Tests for capability detection and temperature limits."""

import json
import pathlib

from custom_components.subzero.capabilities import (
    appliance_family,
    appliance_type_parts,
    temperature_range,
    zones,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def test_wine_reports_two_zones():
    props = load("wine.json")
    assert set(zones(props)) == {"wine_set_temp", "wine2_set_temp"}


def test_freezer_reports_freezer_zone_only():
    props = load("freezer.json")
    assert set(zones(props)) == {"frz_set_temp"}


def test_refrigerator_zone():
    props = load("fridge.json")
    assert set(zones(props)) == {"ref_set_temp"}


def test_crisper_zone_requires_manual_mode():
    props = dict(load("fridge.json"))
    props["crisp_temp_mode"] = 1
    props["crisp_set_temp"] = 40
    assert "crisp_set_temp" not in zones(props)
    props["crisp_temp_mode"] = 0
    assert "crisp_set_temp" in zones(props)


def test_family_detection():
    assert appliance_family(load("fridge.json")) == "refrigeration"
    assert appliance_family({"cav_set_temp": 350}) == "oven"
    assert appliance_family({"wash_cycle": 2}) == "dishwasher"
    assert appliance_family({"fan_speed": 2}) == "hood"


def test_appliance_type_parts_drops_group_prefix():
    # The cloud reports the app's three-segment mapping with a leading "17".
    assert appliance_type_parts({"appliance_type": "17.17.4.0"}) == (17, 4, 0)
    assert appliance_type_parts({"appliance_type": "17.13.3.1"}) == (13, 3, 1)
    assert appliance_type_parts({"appliance_type": "17.22.9.1"}) == (22, 9, 1)


def test_appliance_type_parts_accepts_three_segments():
    assert appliance_type_parts({"appliance_type": "17.4.0"}) == (17, 4, 0)


def test_appliance_type_parts_rejects_junk():
    assert appliance_type_parts({"appliance_type": "x.y"}) is None
    assert appliance_type_parts({}) is None


# Limits below were measured by writing candidate setpoints to live hardware
# and recording what the cloud accepted.
def test_freezer_range():
    assert temperature_range("frz_set_temp", {}) == (-5, 5)


def test_wine_range():
    assert temperature_range("wine_set_temp", {}) == (40, 65)
    assert temperature_range("wine2_set_temp", {}) == (40, 65)


def test_refrigerator_column_range():
    props = {"appliance_type": "17.17.4.0", "ref_set_temp": 42}
    assert temperature_range("ref_set_temp", props) == (34, 42)


def test_beverage_center_range():
    # Series 13 category 3 appliances are beverage centres and reach 55 F.
    props = {"appliance_type": "17.13.3.1", "ref_set_temp": 43}
    assert temperature_range("ref_set_temp", props) == (34, 55)


def test_crisper_tracks_refrigerator():
    """The crisper is ref +-2, clipped to the refrigerator's own limits.

    Measured: at 38 the cloud accepted 36-40. At 42 it accepted 40-42, because
    44 is past the refrigerator's upper bound rather than the crisper's.
    """
    props = {"appliance_type": "17.17.4.0", "ref_set_temp": 38}
    assert temperature_range("crisp_set_temp", props) == (36, 40)
    props["ref_set_temp"] = 42
    assert temperature_range("crisp_set_temp", props) == (40, 42)
