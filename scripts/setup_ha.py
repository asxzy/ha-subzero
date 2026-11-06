#!/usr/bin/env python3
"""Set up the Sub-Zero integration on Home Assistant through its config flow.

Drives ``POST /api/config/config_entries/flow`` with the account credentials
from ``.env`` and reports the resulting entities.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time

from _env import load

ROOT = pathlib.Path(__file__).resolve().parent.parent


def env() -> dict[str, str]:
    """Read the repository .env."""
    return load()


def api(host: str, token: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    """Call the Home Assistant REST API."""
    args = [
        "curl",
        "-sS",
        "-m",
        "90",
        "-w",
        "\n%{http_code}",
        "-H",
        f"Authorization: Bearer {token}",
        "-H",
        "Content-Type: application/json",
    ]
    if body is not None:
        args += ["-X", "POST", "-d", json.dumps(body)]
    args.append(f"http://{host}:8123{path}")
    raw = subprocess.run(args, capture_output=True, text=True).stdout
    payload, _, status = raw.rpartition("\n")
    try:
        return int(status or 0), json.loads(payload or "{}")
    except ValueError:
        return int(status or 0), {"raw": payload}


def main() -> int:
    """Run the config flow and report what was created."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", type=int, default=90, help="Seconds to allow sign-in")
    args = parser.parse_args()

    values = env()
    host = values["HA_HOST"]
    token = values["HA_TOKEN"]

    status, handlers = api(host, token, "/api/config/config_entries/flow_handlers")
    print(f"flow handlers: HTTP {status}, subzero present: {'subzero' in handlers}")

    print("starting config flow...")
    status, flow = api(host, token, "/api/config/config_entries/flow", {"handler": "subzero"})
    if status != 200:
        print(f"could not start flow: HTTP {status} {flow}", file=sys.stderr)
        return 1
    flow_id = flow["flow_id"]
    print(f"  flow {flow_id} at step {flow.get('step_id')}")

    print("submitting credentials (signs in to Sub-Zero)...")
    status, result = api(
        host,
        token,
        f"/api/config/config_entries/flow/{flow_id}",
        {
            "username": values["USERNAME"],
            "password": values["PASSWORD"],
        },
    )
    print(f"  HTTP {status}: {json.dumps(result)[:400]}")

    if result.get("type") != "create_entry":
        errors = result.get("errors") or {}
        print(f"flow did not finish: {errors or result.get('reason')}", file=sys.stderr)
        return 1

    print(f"created entry: {result.get('title')!r}")

    # The entity registry is websocket-only, so entities are identified by the
    # appliance_type attribute every Sub-Zero entity publishes.
    print("waiting for entities...")
    deadline = time.time() + args.wait
    states: list[dict] = []
    while time.time() < deadline:
        status, payload = api(host, token, "/api/states")
        states = [
            state
            for state in (payload if isinstance(payload, list) else [])
            if "appliance_type" in (state.get("attributes") or {})
        ]
        if states:
            break
        time.sleep(5)

    by_domain: dict[str, int] = {}
    for state in states:
        domain = state["entity_id"].split(".", 1)[0]
        by_domain[domain] = by_domain.get(domain, 0) + 1
    print(f"entities: {len(states)}")
    for domain in sorted(by_domain):
        print(f"  {domain:14} {by_domain[domain]}")
    return 0 if states else 1


if __name__ == "__main__":
    raise SystemExit(main())
