"""Dump the entities each appliance family produces, for manual review."""

from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from custom_components.subzero.api import Appliance  # noqa: E402
from custom_components.subzero.coordinator import (  # noqa: E402
    ApplianceState,
    SubZeroData,
)

FIXTURES = ROOT / "tests" / "fixtures"
PLATFORMS = (
    "binary_sensor",
    "button",
    "climate",
    "number",
    "select",
    "sensor",
    "switch",
)

APPLIANCES = [
    ("dev-wine", "Main Wine", "17.14.2.0", "wine.json"),
    ("dev-fridge", "36 Refrigerator", "17.17.4.0", "fridge.json"),
    ("dev-freezer", "36 Freezer", "17.17.5.0", "freezer.json"),
    ("dev-beverage", "Upper Beverage", "17.13.3.1", "beverage.json"),
    ("dev-oven", "Wolf Oven", "17.20.1.0", "oven.json"),
    ("dev-dishwasher", "Cove Dishwasher", "17.21.1.0", "dishwasher.json"),
    ("dev-hood", "Wolf Hood", "17.23.1.0", "hood.json"),
    ("dev-cooktop", "Wolf Cooktop", "17.25.1.0", "cooktop.json"),
]


class _Entry:
    def __init__(self, coordinator):
        self.runtime_data = coordinator
        self.options = {}
        self.data = {}
        self.entry_id = "dump"
        self.title = "dump"
        self.version = 1


async def main() -> None:
    import json

    states = {}
    for device_id, name, appliance_type, filename in APPLIANCES:
        properties = json.loads((FIXTURES / filename).read_text())
        states[device_id] = ApplianceState(
            appliance=Appliance(device_id, name, appliance_type, "F"),
            properties=properties,
            online=True,
        )
    coordinator = type("_Coordinator", (), {})()
    coordinator.data = SubZeroData(appliances=states)
    coordinator.appliances = {key: value.appliance for key, value in states.items()}
    entry = _Entry(coordinator)

    by_device: dict[str, list[str]] = {device_id: [] for device_id in states}
    for platform in PLATFORMS:
        module = __import__(f"custom_components.subzero.{platform}", fromlist=[platform])
        created: list = []

        def collect(entities, _created=created) -> None:
            _created.extend(entities)

        await module.async_setup_entry(None, entry, collect)
        for entity in created:
            name = getattr(getattr(entity, "entity_description", None), "name", None)
            by_device[entity._device_id].append(
                f"{platform}: {name or entity._setpoint_key}"
            )

    for device_id, name, _, _ in APPLIANCES:
        print(f"\n=== {name} ({device_id})")
        for line in sorted(by_device[device_id]):
            print(f"   {line}")


asyncio.run(main())
