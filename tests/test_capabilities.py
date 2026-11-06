"""Tests for capability detection."""
import json, pathlib, sys
from custom_components.subzero.capabilities import appliance_family, zones

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
