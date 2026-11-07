# Sub-Zero Group for Home Assistant

A Home Assistant custom integration for Sub-Zero, Wolf, and Cove appliances. It
signs in to the same cloud account the Owner's App uses, and exposes appliances
as native Home Assistant entities rather than raw property dictionaries.

Push is the primary transport: the cloud notifies the integration as state
changes, and a periodic poll only recovers anything a dropped connection missed.

<p align="center">
  <a href="https://my.home-assistant.io/redirect/hacs_repository/?owner=asxzy&repository=ha-subzero&category=integration">
    <img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="Add this repository to HACS as a custom repository">
  </a>
</p>

## Supported appliances

Entity sets are derived from the properties an appliance actually reports, so a
model only gains the controls it really has.

| Family | Examples | Notes |
| --- | --- | --- |
| Refrigeration | `DEC3650R`, `DEC3650FI`, `DEU2450BG`, `DEU2450WDZ` | Zone setpoints, mode switches, door and temperature alerts, ice maker |
| Wine | `DEU2450WDZ` | Two zones with independent setpoints, temperature alerts, night mode |
| Oven | Wolf ovens | Cavity setpoints and modes, cook timers, probe status, remote start |
| Dishwasher | Cove dishwashers | Wash cycle start/cancel, status, cycle counters |
| Hood | Wolf hoods | Fan speed, light level and colour, filter counters, favourites |
| Cooktop | Wolf cooktops | Power, pan detection, brightness/volume, auto-lock |

Climate, sensor, binary sensor, switch, select, number, and button platforms are
all used. One-shot actions (starting a wash cycle, starting an oven) are buttons
rather than switches, because they have no persistent on/off state.

## Installation

Requires Home Assistant 2026.11 or newer.

1. Copy `custom_components/subzero` into your `config/custom_components`.
2. Restart Home Assistant.
3. Add the integration and sign in with your Sub-Zero Group account.

Alternatively, add this repository in HACS as a custom repository, or via the
Marketplace built into Home Assistant 2026.11 and newer. Either way, use the
button at the top of this page to add it in one step.

## Setup

The integration signs in with the email and password you use for the Owner's
App. The B2C sign-in is completed inside Home Assistant, so the app's custom
callback URL never needs to resolve.

Account credentials are stored by Home Assistant's config entry, and refreshed
tokens are rotated and persisted as the cloud issues them.

Two-factor accounts are not supported yet; the sign-in reports
`mfa_required` rather than failing obscurely.

## Services

| Service | Target | Description |
| --- | --- | --- |
| `subzero.reset_air_filter` | Device | Clear the air filter reminder on a refrigeration appliance |

Services use Home Assistant's standard `target: device:` selection, so they scope
naturally in scripts and automations.

## Options

| Option | Range | Default | Description |
| --- | --- | --- | --- |
| Status check interval | 15–600 s | 60 s | How often to poll. Push delivers changes as they happen, so this only recovers what a dropped connection missed. |

## How it works

- **Sign-in.** Azure AD B2C authorization code flow with PKCE, completed
  headlessly. The app's callback URL is registered on the app registration, so
  the code is read from the redirect's `Location` header instead of being
  delivered to a browser.
- **State.** Each appliance reports a flat property map. The integration derives
  which controls make sense from the properties present in that snapshot, rather
  than from a hard-coded per-model table.
- **Push.** A SignalR connection to the account's `connectedappliances` hub
  delivers changes in a couple of seconds. It reconnects on its own, and ping
  timing is driven by elapsed time rather than socket silence, because the server
  sends its own keepalives.
- **Writes.** A write is confirmed by the cloud rejecting anything it will not
  accept, so write failures surface as errors instead of silently doing nothing.

## Limitations

- Cloud only. There is no BLE or local-network path.
- Appliances that are offline report HTTP 404 and their entities go
  `unavailable`.
- Enum values were recovered by probing a live account. Values a model does not
  advertise are not published.

## Development

The test suite runs against recorded appliance snapshots, so no account is needed:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
```

Recorded snapshots live in `tests/fixtures`. They are synthetic and contain no
account identifiers.

`scripts/deploy.py` copies the integration to a Home Assistant host over SSH.
Copy `.env.example` to `.env` and fill in the host and SSH credentials; `.env` is
git-ignored.

## Disclaimer

This is an unofficial integration and is not affiliated with, endorsed by, or
supported by Sub-Zero Group, Inc. It talks to a cloud API that was reverse
engineered from the vendor's own app. That API is undocumented and can change
without notice, which may break the integration.

Use it at your own risk. In particular, do not rely on it for food safety: an
appliance that is offline, or a cloud outage, can leave Home Assistant showing
stale state.
