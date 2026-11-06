"""SignalR push client for the Sub-Zero Group cloud.

The Owner's App receives state changes over an Azure SignalR hub rather than by
polling. The sequence, recovered from the app and confirmed against the live
service, is:

1. ``POST /signal-r/negotiateUser`` on the appliance API with the normal account
   headers. It answers with the hub address (``?hub=connectedappliances``) and a
   short-lived SignalR access token.
2. ``POST <hub>/negotiate?hub=connectedappliances&negotiateVersion=1``. The
   ``hub`` query parameter must be preserved exactly; dropping or reordering it
   is answered with ``400 "Invalid value of 'hub'."``.
3. Open the WebSocket at ``<hub>?id=<connectionToken>&hub=connectedappliances``
   and complete the JSON handshake.
4. Ask each appliance to open its cloud channel with the ``open_cloud_async``
   direct method. Nothing is pushed until this happens, and the registration is
   per WebSocket connection rather than per account, so it is repeated after
   every reconnect. Opening the channel also yields a full snapshot.

Frames arriving on the hub are ``ConnectedApplianceMessage`` invocations whose
single argument is JSON with a ``DeviceId`` and a ``Payload``; the payload in
turn carries an ``api.async_channel`` string that is itself JSON:

* ``{"type": 1, "pload": {...}}`` - the complete property snapshot, sent when a
  channel opens.
* ``{"type": 2, "pload": {"seq", "timestamp", "props", "msg_types"}}`` - a change
  set. Deltas carry a per-appliance sequence number and are delivered in order.

Keepalives are ``{"type": 6}``. The server drops a connection that stays quiet,
so a ping is sent well inside the observed timeout.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any, Final

import aiohttp
from yarl import URL

from homeassistant.util import dt as dt_util

from .api import SubZeroApiError, SubZeroClient
from .const import (
    PUSH_HANDSHAKE_TIMEOUT,
    PUSH_PING_INTERVAL,
    PUSH_RECONNECT_MAX,
    PUSH_RECONNECT_MIN,
)

_LOGGER = logging.getLogger(__name__)

_SEPARATOR: Final = "\x1e"
_HANDSHAKE: Final = json.dumps({"protocol": "json", "version": 1}) + _SEPARATOR
_PING: Final = json.dumps({"type": 6}) + _SEPARATOR

# SignalR message type ids, from the JSON hub protocol.
_TYPE_INVOCATION: Final = 1
_TYPE_CLOSE: Final = 7

# Channel message kinds, observed on the wire.
_CHANNEL_SNAPSHOT: Final = 1
_CHANNEL_DELTA: Final = 2

SnapshotHandler = Callable[[str, dict[str, Any]], None]
DeltaHandler = Callable[[str, dict[str, Any]], None]


class SubZeroPushError(SubZeroApiError):
    """The push channel could not be established."""


def handle_invocation(frame: str) -> tuple[str, dict[str, Any]] | None:
    """Decode one hub frame into ``(device_id, channel message)``.

    Returns ``None`` for anything that is not an appliance state message, which
    includes keepalives, acks and unrelated client methods.
    """
    try:
        message = json.loads(frame)
    except ValueError:
        return None
    if not isinstance(message, dict):
        return None
    if message.get("type") != _TYPE_INVOCATION:
        return None
    if message.get("target") != "ConnectedApplianceMessage":
        return None
    arguments = message.get("arguments")
    if not isinstance(arguments, list) or len(arguments) != 1:
        return None
    try:
        outer = json.loads(arguments[0])
        device_id = outer["DeviceId"]
        payload = json.loads(outer["Payload"])
        channel = json.loads(payload["api.async_channel"])
    except (ValueError, TypeError, KeyError):
        return None
    if not isinstance(device_id, str) or not isinstance(channel, dict):
        return None
    return device_id, channel


def channel_update(
    channel: dict[str, Any],
) -> tuple[str, dict[str, Any]] | None:
    """Return ``("snapshot"|"delta", properties)`` for a channel message."""
    kind = channel.get("type")
    payload = channel.get("pload")
    if not isinstance(payload, dict):
        return None
    if kind == _CHANNEL_SNAPSHOT:
        return "snapshot", payload
    if kind == _CHANNEL_DELTA:
        props = payload.get("props")
        if isinstance(props, dict):
            return "delta", props
        # A delta without properties only advances the sequence number.
        return None
    return None


class SubZeroPush:
    """Keep a SignalR connection open and stream appliance updates."""

    def __init__(
        self,
        client: SubZeroClient,
        appliance_ids: list[str],
        on_snapshot: SnapshotHandler,
        on_delta: DeltaHandler,
    ) -> None:
        """Initialize the push client."""
        self._client = client
        self._appliance_ids = appliance_ids
        self._on_snapshot = on_snapshot
        self._on_delta = on_delta
        self._stopping = False
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self.connected = False
        self.last_error: str | None = None
        # Diagnostics: a reconnect that keeps failing looks the same as a slow
        # start from the outside, so count attempts and report the last failure.
        self.attempts = 0
        self.connected_at: str | None = None

    async def run(self) -> None:
        """Connect and stream updates until cancelled."""
        await self._run()

    async def stop(self) -> None:
        """Stop reconnecting, close the socket and mark disconnected."""
        self._stopping = True
        self.connected = False
        ws = self._ws
        if ws is not None and not ws.closed:
            await ws.close()

    async def _run(self) -> None:
        """Reconnect with backoff until stopped."""
        delay = PUSH_RECONNECT_MIN
        while not self._stopping:
            self.attempts += 1
            try:
                await self._connect_once()
                # A clean return means the connection ended; reconnect promptly.
                delay = PUSH_RECONNECT_MIN
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - never let the task die
                self.last_error = f"{type(err).__name__}: {err}"
                _LOGGER.debug("Sub-Zero push connection ended: %s", err)
            finally:
                self.connected = False
            if self._stopping:
                break
            await asyncio.sleep(delay)
            delay = min(delay * 2, PUSH_RECONNECT_MAX)

    async def _negotiate(self) -> tuple[URL, dict[str, str], str]:
        """Return the hub URL, its headers and a connection token."""
        info = await self._client.async_negotiate_push()
        try:
            endpoint = URL(info["url"])
            access_token = info["accessToken"]
        except (KeyError, TypeError) as err:
            raise SubZeroPushError(
                "Sub-Zero returned an unexpected notification endpoint."
            ) from err
        if not isinstance(access_token, str) or not access_token:
            raise SubZeroPushError(
                "Sub-Zero returned an unexpected notification endpoint."
            )
        headers = {
            "Authorization": f"Bearer {access_token}",
            "X-Requested-With": "FlutterHttpClient",
        }
        # The hub must stay in the query string; replacing the query is rejected.
        negotiate_url = endpoint.with_path(
            endpoint.path.rstrip("/") + "/negotiate"
        ).with_query({**endpoint.query, "negotiateVersion": "1"})
        async with self._client.session.post(
            negotiate_url,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=PUSH_HANDSHAKE_TIMEOUT),
        ) as response:
            body = await response.text()
            if response.status >= 400:
                raise SubZeroPushError(
                    f"SignalR negotiate failed with HTTP {response.status}."
                )
        try:
            transport = json.loads(body)
            token = transport["connectionToken"]
        except (ValueError, KeyError, TypeError) as err:
            raise SubZeroPushError(
                "SignalR did not return a connection token."
            ) from err
        return endpoint, headers, token

    async def _connect_once(self) -> None:
        """Connect, open every appliance channel, and consume frames."""
        endpoint, headers, token = await self._negotiate()
        url = endpoint.with_scheme("wss").with_query(
            {"id": token, **endpoint.query}
        )
        async with self._client.session.ws_connect(
            url,
            headers=headers,
            heartbeat=None,
            max_msg_size=0,
        ) as ws:
            self._ws = ws
            try:
                await ws.send_str(_HANDSHAKE)
                first = await ws.receive(timeout=PUSH_HANDSHAKE_TIMEOUT)
                if first.type is not aiohttp.WSMsgType.TEXT or first.data.rstrip(
                    _SEPARATOR
                ) != "{}":
                    raise SubZeroPushError("SignalR handshake was refused.")
                self.connected = True
                self.connected_at = dt_util.utcnow().isoformat()
                self.last_error = None
                _LOGGER.debug("Sub-Zero push connected")
                await self._open_channels()
                await self._consume(ws)
            finally:
                self._ws = None

    async def _open_channels(self) -> None:
        """Ask each appliance to stream on this connection."""
        # The registration belongs to the connection, so it is repeated here
        # rather than once at setup.
        results = await asyncio.gather(
            *(
                self._client.async_open_channel(device_id)
                for device_id in self._appliance_ids
            ),
            return_exceptions=True,
        )
        for device_id, result in zip(self._appliance_ids, results, strict=True):
            if isinstance(result, BaseException):
                _LOGGER.debug(
                    "Could not open the update channel for %s: %s",
                    device_id,
                    result,
                )

    async def _consume(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        """Read frames until the connection closes, pinging on a timer.

        The ping is driven by elapsed time rather than by silence. The server
        sends its own keepalives, so waiting for a quiet socket would never
        ping and the connection would be dropped mid-use.
        """
        loop = asyncio.get_running_loop()
        last_ping = loop.time()
        while not ws.closed:
            try:
                message = await ws.receive(timeout=PUSH_PING_INTERVAL)
            except asyncio.TimeoutError:
                message = None
            if loop.time() - last_ping >= PUSH_PING_INTERVAL:
                if ws.closed:
                    return
                await ws.send_str(_PING)
                last_ping = loop.time()
            if message is None:
                continue
            if message.type is not aiohttp.WSMsgType.TEXT:
                if message.type is aiohttp.WSMsgType.ERROR:
                    _LOGGER.debug("Sub-Zero push socket error: %s", ws.exception())
                return
            body = message.data.rstrip(_SEPARATOR)
            if body == json.dumps({"type": _TYPE_CLOSE}):
                return
            invocation = handle_invocation(body)
            if invocation is None:
                continue
            device_id, channel = invocation
            update = channel_update(channel)
            if update is None:
                continue
            kind, properties = update
            if kind == "snapshot":
                self._on_snapshot(device_id, properties)
            else:
                self._on_delta(device_id, properties)
