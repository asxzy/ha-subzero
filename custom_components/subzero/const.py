"""Constants for the Sub-Zero Group integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "subzero"
MANUFACTURER: Final = "Sub-Zero Group"

# Cloud endpoints recovered from the Owner's App (4.6.2) Dart snapshot.
API_BASE: Final = "https://prod.iot.subzero.com"

# API Management subscription key bundled with the Android app.
SUBSCRIPTION_KEY: Final = "e88bf0b60baf441583f822fa9ba9c895"

# Azure AD B2C custom policy used by the app.
B2C_ORIGIN: Final = "https://login.subzero-wolf.com"
B2C_TENANT: Final = "SubZeroB2CPrd.onmicrosoft.com"
B2C_POLICY: Final = "B2C_1A_SIGNUP_SIGNIN"
B2C_CLIENT_ID: Final = "6eefabd0-49a3-4b92-b329-81b9f638e940"
# Only this callback is registered on the app registration. Home Assistant cannot
# receive it, so the flow is completed in-process and the code is read from the
# 302 Location header instead of being delivered to a browser.
B2C_REDIRECT_URI: Final = "com.szg.szgdigitalproductexperience://oauth/redirect/"
B2C_SCOPE: Final = f"openid offline_access {B2C_CLIENT_ID}"

PLATFORMS: Final = [
    "binary_sensor",
    "button",
    "climate",
    "number",
    "select",
    "sensor",
    "switch",
]

# Appliance type tuples are "<series>.<category>.<version>" as reported by the
# cloud and mapped from model numbers in the app's Remote Config.
TYPE_SEPARATOR: Final = "."

# Polling interval. Push delivers changes immediately; polling recovers anything
# a dropped connection missed.
DEFAULT_SCAN_INTERVAL: Final = 60
MIN_SCAN_INTERVAL: Final = 15
MAX_SCAN_INTERVAL: Final = 600

# Direct method command names.
CMD_GET: Final = "get"
CMD_SET: Final = "set"
CMD_OPEN_CHANNEL: Final = "open_cloud_async"
CMD_RESET_AIR_FILTER: Final = "reset_air_filter"

# Push notification transport. The account-level endpoint name is spelled with
# the app's own capitalisation, so it is kept verbatim.
SIGNALR_NEGOTIATE_PATH: Final = "/signal-r/negotiateUser"
SIGNALR_HUB: Final = "connectedappliances"

# Push timing. The hub drops a connection that stays quiet for about a minute,
# and the connection token is valid for an hour; pinging well inside the first
# keeps the second the only reason to reconnect.
PUSH_PING_INTERVAL: Final = 15
PUSH_HANDSHAKE_TIMEOUT: Final = 20
PUSH_RECONNECT_MIN: Final = 5
PUSH_RECONNECT_MAX: Final = 300

# Appliance snapshot keys that are private and must never be written to
# diagnostics. Wi-Fi strength is deliberately not listed: it is published as a
# diagnostic sensor, so it is not sensitive here.
PRIVATE_KEYS: Final = frozenset(
    {
        "pin",
        "ap_ssid",
        "device_wlan_id",
        "ipv4_addr",
        "ap_chan",
        "ap_enc",
        "remote_svc_reg_token",
    }
)
