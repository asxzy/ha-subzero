#!/usr/bin/env python3
"""Deploy the Sub-Zero integration to the Home Assistant host.

Packs ``custom_components/subzero`` and unpacks it into the host's config
directory over SSH, then optionally restarts Home Assistant.

The Advanced SSH & Web Terminal addon runs on the HA host network and accepts
password authentication, but its SFTP subsystem is disabled, so the archive is
streamed as base64 through an ``exec`` channel instead of using ``scp``.

Requires ``paramiko`` (install with ``.venv-test/bin/pip install paramiko``).
"""

from __future__ import annotations

import argparse
import base64
import io
import pathlib
import sys
import tarfile

import paramiko

from _env import get

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE = ROOT / "custom_components" / "subzero"
REMOTE_CONFIG = "/config"
DOMAIN = "subzero"
DEFAULT_HOST = "192.168.1.253"
DEFAULT_USER = "hassio"


def connect(
    host: str, user: str, password: str, *, timeout: int = 30
) -> paramiko.SSHClient:
    """Open an SSH connection to the addon."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=22,
        username=user,
        password=password,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


def run(
    client: paramiko.SSHClient, command: str, *, timeout: int = 180
) -> tuple[int, str, str]:
    """Run a command and return (exit status, stdout, stderr)."""
    _, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    return stdout.channel.recv_exit_status(), out, err


def build_archive_b64() -> str:
    """Pack the integration into a base64-encoded gzipped tar."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(SOURCE.rglob("*")):
            relative = path.relative_to(SOURCE.parent)
            if "__pycache__" in relative.parts or path.suffix == ".pyc":
                continue
            archive.add(path, arcname=str(relative), recursive=False)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def deploy(*, host: str, user: str, password: str, restart: bool) -> int:
    """Upload the integration and optionally restart Home Assistant."""
    payload = build_archive_b64()
    print(f"uploading {len(payload)} base64 bytes...")
    client = connect(host, user, password)
    try:
        status, out, err = run(
            client,
            f"sudo rm -rf {REMOTE_CONFIG}/custom_components/{DOMAIN} && "
            f"echo '{payload}' | base64 -d | sudo tar -xzf - "
            f"-C {REMOTE_CONFIG}/custom_components --no-same-owner && "
            f"sudo chown -R root:root {REMOTE_CONFIG}/custom_components/{DOMAIN} && "
            f"ls {REMOTE_CONFIG}/custom_components/{DOMAIN}",
            timeout=240,
        )
        if out:
            print(out.strip())
        if status != 0:
            print(err.strip() or f"deploy failed (exit {status})", file=sys.stderr)
            return status

        if restart:
            print("restarting Home Assistant...")
            run(client, "ha core restart", timeout=60)
            print("restart requested")
    finally:
        client.close()
    return 0


def main() -> int:
    """Parse arguments and deploy."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=get("HA_SSH_HOST", DEFAULT_HOST))
    parser.add_argument("--user", default=get("HA_SSH_USER", DEFAULT_USER))
    parser.add_argument("--password", default=get("HA_SSH_PASSWORD"))
    parser.add_argument("--restart", action="store_true", help="Restart Home Assistant")
    args = parser.parse_args()
    if not SOURCE.is_dir():
        print(f"missing {SOURCE}", file=sys.stderr)
        return 1
    if not args.password:
        print(
            "no SSH password: set HA_SSH_PASSWORD in .env or pass --password",
            file=sys.stderr,
        )
        return 1
    return deploy(
        host=args.host,
        user=args.user,
        password=args.password,
        restart=args.restart,
    )


if __name__ == "__main__":
    raise SystemExit(main())
