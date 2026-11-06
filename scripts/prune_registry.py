#!/usr/bin/env python3
"""Remove entity-registry rows this integration no longer publishes.

Home Assistant keeps a registry row for every entity it has ever seen, even
after the integration stops adding it. After an entity-model change those rows
linger as ``unavailable`` or as duplicates of a newly added entity.

A row cannot be identified from the state machine alone, because an entity the
integration still publishes but which is disabled by default never gets a state
either. Instead this script reads the live appliance snapshots from the
integration's own diagnostics, replays each platform's setup against them to
learn the exact ``(domain, unique_id)`` pairs the integration creates right now,
and removes every ``subzero`` registry row outside that set.

Run it with ``--dry-run`` first. It needs the test virtualenv, which has Home
Assistant installed and can import the integration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from typing import Any

import aiohttp

from _env import load

ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PLATFORMS = (
    "binary_sensor",
    "button",
    "climate",
    "number",
    "select",
    "sensor",
    "switch",
)


def env() -> dict[str, str]:
    """Read the repository .env."""
    return load()


class _Entry:
    """Minimal config entry shape the platform setup functions read."""

    def __init__(self, coordinator: Any) -> None:
        """Store the coordinator and the fields platforms might touch."""
        self.runtime_data = coordinator
        self.options: dict[str, Any] = {}
        self.data: dict[str, Any] = {}
        self.entry_id = "prune"
        self.title = "prune"
        self.version = 1


async def expected_entities(
    snapshots: dict[str, dict[str, Any]]
) -> set[tuple[str, str]]:
    """Return the (domain, unique_id) pairs the platforms would create."""
    from custom_components.subzero.api import Appliance
    from custom_components.subzero.coordinator import ApplianceState, SubZeroData

    states: dict[str, ApplianceState] = {}
    for device_id, properties in snapshots.items():
        appliance = Appliance(
            device_id=device_id,
            name=str(properties.get("appliance_name") or device_id),
            appliance_type=str(properties.get("appliance_type") or ""),
            temperature_unit="F",
        )
        states[device_id] = ApplianceState(
            appliance=appliance, properties=properties, online=True
        )

    coordinator = type("_Coordinator", (), {})()
    coordinator.data = SubZeroData(appliances=states)
    coordinator.appliances = {key: value.appliance for key, value in states.items()}
    entry = _Entry(coordinator)

    expected: set[tuple[str, str]] = set()
    for platform in PLATFORMS:
        module = __import__(f"custom_components.subzero.{platform}", fromlist=[platform])
        created: list[Any] = []

        def collect(entities, _created=created) -> None:
            """Collect the entities a platform would add.

            Home Assistant calls this as a plain callback, not a coroutine.
            """
            _created.extend(entities)

        await module.async_setup_entry(None, entry, collect)
        for entity in created:
            unique_id = entity.unique_id
            if unique_id:
                expected.add((platform, unique_id))
    return expected


async def prune(url: str, token: str, *, dry_run: bool) -> int:
    """Delete registry rows the integration no longer creates."""
    base = url.split("/api/websocket", 1)[0]
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url, max_msg_size=0) as ws:
            await ws.receive_json()
            await ws.send_json({"type": "auth", "access_token": token})
            auth = await ws.receive_json()
            if auth.get("type") != "auth_ok":
                print(f"authentication failed: {auth}", file=sys.stderr)
                return 1

            counter = 0

            async def command(payload: dict) -> dict:
                nonlocal counter
                counter += 1
                payload["id"] = counter
                await ws.send_json(payload)
                while True:
                    message = await ws.receive_json()
                    if message.get("id") == payload["id"]:
                        return message

            entries = (await command({"type": "config_entries/get"}))["result"]
            ours = [entry for entry in entries if entry["domain"] == "subzero"]
            if len(ours) != 1:
                print(f"expected one subzero entry, found {len(ours)}", file=sys.stderr)
                return 1
            entry_id = ours[0]["entry_id"]

            # Diagnostics are served over REST, not the "diagnostics/get"
            # websocket command (that one only reports which handlers exist).
            async with session.get(
                f"{base}/api/diagnostics/config_entry/{entry_id}",
                headers={"Authorization": f"Bearer {token}"},
            ) as response:
                if response.status != 200:
                    print(
                        "could not read diagnostics "
                        f"(HTTP {response.status}); is the entry loaded?",
                        file=sys.stderr,
                    )
                    return 1
                diagnostics = await response.json()
            appliances = diagnostics.get("data", {}).get("appliances")
            if not appliances:
                print("diagnostics carried no appliances", file=sys.stderr)
                return 1
            snapshots = {
                info["device_id"]: info["properties"] for info in appliances.values()
            }
            print(f"live appliances: {len(snapshots)}")

            expected = await expected_entities(snapshots)
            registry = (await command({"type": "config/entity_registry/list"}))["result"]
            ours_rows = [row for row in registry if row.get("platform") == "subzero"]
            stale = [
                row
                for row in ours_rows
                if (row["entity_id"].split(".", 1)[0], row["unique_id"]) not in expected
            ]

            print(f"subzero registry rows: {len(ours_rows)}")
            print(f"expected entities now: {len(expected)}")
            print(f"stale rows: {len(stale)}")

            removed = 0
            for row in sorted(stale, key=lambda item: item["entity_id"]):
                entity_id = row["entity_id"]
                if dry_run:
                    print(f"  would remove {entity_id}")
                    continue
                result = await command(
                    {"type": "config/entity_registry/remove", "entity_id": entity_id}
                )
                if result.get("success"):
                    removed += 1
                    print(f"  removed {entity_id}")
                else:
                    print(f"  failed {entity_id}: {json.dumps(result.get('error'))}")
            if not dry_run:
                print(f"\nremoved {removed} of {len(stale)}")
            return 0


def main() -> int:
    """Parse arguments and prune the registry."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    values = env()
    url = f"http://{values['HA_HOST']}:8123/api/websocket"
    return asyncio.run(prune(url, values["HA_TOKEN"], dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
