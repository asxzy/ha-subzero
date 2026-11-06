"""Set up the Sub-Zero Group integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import (
    SubZeroApiError,
    SubZeroAuthError,
    SubZeroClient,
    SubZeroConnectionError,
)
from .auth import SubZeroAuth, Tokens
from .const import DEFAULT_SCAN_INTERVAL, PLATFORMS
from .coordinator import SubZeroCoordinator
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

SubZeroConfigEntry = ConfigEntry[SubZeroCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SubZeroConfigEntry) -> bool:
    """Set up Sub-Zero Group from a config entry."""
    session = aiohttp.ClientSession(
        cookie_jar=aiohttp.CookieJar(quote_cookie=False)
    )
    auth = SubZeroAuth(session)

    try:
        tokens = Tokens.from_dict(entry.data["tokens"])
    except (KeyError, ValueError) as err:
        await session.close()
        raise ConfigEntryAuthFailed("Stored Sub-Zero tokens are invalid.") from err

    async def save_tokens(tokens: Tokens) -> None:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "tokens": tokens.as_dict()}
        )

    client = SubZeroClient(session, auth, tokens, save_tokens)

    try:
        await client.async_refresh_tokens()
        appliances = await client.async_get_appliances()
    except SubZeroAuthError as err:
        await session.close()
        raise ConfigEntryAuthFailed(str(err)) from err
    except SubZeroConnectionError as err:
        await session.close()
        raise ConfigEntryNotReady(str(err)) from err
    except SubZeroApiError as err:
        await session.close()
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = SubZeroCoordinator(hass, entry, client, appliances)
    await coordinator.async_config_entry_first_refresh()

    interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    coordinator.update_interval = timedelta(seconds=interval)

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_options))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)

    entry.async_on_unload(session.close)
    return True


async def _async_update_options(
    hass: HomeAssistant, entry: SubZeroConfigEntry
) -> None:
    """Apply changed options without a full reload."""
    coordinator = entry.runtime_data
    interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)
    coordinator.update_interval = timedelta(seconds=interval)


async def async_unload_entry(hass: HomeAssistant, entry: SubZeroConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
