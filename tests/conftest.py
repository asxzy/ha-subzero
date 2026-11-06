"""Shared test fixtures."""

from __future__ import annotations

import copy
import json
import pathlib
import sys
from datetime import UTC, datetime, timedelta

import pytest

pytest_plugins = ["pytest_homeassistant"]

# Allow importing the integration package directly for unit tests.
_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

FIXTURES = pathlib.Path(__file__).parent / "fixtures"

APPLIANCES = [
    ("dev-wine", "Main Wine", "17.14.2.0", "F", "wine.json"),
    ("dev-fridge", "36 Refrigerator", "17.17.4.0", "F", "fridge.json"),
    ("dev-freezer", "36 Freezer", "17.17.5.0", "F", "freezer.json"),
    ("dev-beverage", "Upper Beverage", "17.13.3.1", "F", "beverage.json"),
    ("dev-oven", "Wolf Oven", "17.20.1.0", "F", "oven.json"),
    ("dev-dishwasher", "Cove Dishwasher", "17.21.1.0", "F", "dishwasher.json"),
    ("dev-hood", "Wolf Hood", "17.23.1.0", "F", "hood.json"),
    ("dev-cooktop", "Wolf Cooktop", "17.25.1.0", "F", "cooktop.json"),
]


def load(name: str) -> dict:
    """Load a recorded appliance snapshot."""
    return json.loads((FIXTURES / name).read_text())


SNAPSHOTS = {device_id: load(filename) for device_id, _, _, _, filename in APPLIANCES}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading this custom integration in every test."""
    yield


@pytest.fixture(autouse=True)
def patch_cloud(monkeypatch):
    """Replace the cloud client with recorded snapshots."""
    from custom_components.subzero.api import Appliance, SubZeroClient

    async def fake_appliances(self):
        return [
            Appliance(device_id, name, appliance_type, unit)
            for device_id, name, appliance_type, unit, _ in APPLIANCES
        ]

    async def fake_state(self, device_id):
        # Return a copy: tests mutate snapshots to exercise other readings, and
        # the module-level fixtures must not carry that into the next test.
        return copy.deepcopy(SNAPSHOTS[device_id])

    async def fake_noop(self, *args, **kwargs):
        return None

    monkeypatch.setattr(SubZeroClient, "async_get_appliances", fake_appliances)
    monkeypatch.setattr(SubZeroClient, "async_get_state", fake_state)
    monkeypatch.setattr(SubZeroClient, "async_refresh_tokens", fake_noop)
    monkeypatch.setattr(SubZeroClient, "async_set_property", fake_noop)
    monkeypatch.setattr(SubZeroClient, "async_set_properties", fake_noop)


def tokens() -> dict:
    """Return a stored token bundle for a mock entry."""
    from custom_components.subzero.auth import Tokens

    return Tokens(
        access_token="access",
        id_token="id",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        user_id="account-1",
    ).as_dict()
