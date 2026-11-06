"""Load the repository's ``.env`` for the helper scripts.

The file is read rather than sourced because several of its keys (notably
``USERNAME``) collide with shell special parameters and are silently ignored by
``source``. Values may be quoted; the quotes are stripped.
"""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load() -> dict[str, str]:
    """Return the .env values as a mapping."""
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def get(key: str, default: str | None = None) -> str | None:
    """Look a key up in the environment first, then in .env."""
    if (value := os.environ.get(key)) is not None:
        return value
    return load().get(key, default)
