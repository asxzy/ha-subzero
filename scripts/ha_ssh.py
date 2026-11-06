#!/usr/bin/env python3
"""Run a command on the Home Assistant host.

The Advanced SSH & Web Terminal addon runs on the HA host network and accepts
password authentication. Requires ``paramiko``.
"""

from __future__ import annotations

import argparse
import sys

import paramiko

from _env import get

DEFAULT_HOST = "homeassistant.local"
DEFAULT_USER = "hassio"


def run(
    command: str, *, host: str, user: str, password: str, timeout: int = 120
) -> int:
    """Run a command on the host and stream its output."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        host,
        port=22,
        username=user,
        password=password,
        timeout=30,
        banner_timeout=30,
        auth_timeout=30,
        allow_agent=False,
        look_for_keys=False,
    )
    try:
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        status = stdout.channel.recv_exit_status()
    finally:
        client.close()
    if out:
        sys.stdout.write(out)
    if err:
        sys.stderr.write(err)
    return status


def main() -> int:
    """Parse arguments and run the remote command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", help="Shell command to run on the HA host")
    parser.add_argument("--host", default=get("HA_SSH_HOST", DEFAULT_HOST))
    parser.add_argument("--user", default=get("HA_SSH_USER", DEFAULT_USER))
    parser.add_argument("--password", default=get("HA_SSH_PASSWORD"))
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if not args.password:
        print(
            "no SSH password: set HA_SSH_PASSWORD in .env or pass --password",
            file=sys.stderr,
        )
        return 1
    return run(
        args.command,
        host=args.host,
        user=args.user,
        password=args.password,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())
