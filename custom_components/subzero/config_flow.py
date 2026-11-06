"""Config flow for the Sub-Zero Group integration."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .api import SubZeroApiError, SubZeroClient, SubZeroConnectionError
from .auth import (
    AuthError,
    AuthFlowChanged,
    InvalidCredentials,
    MfaRequired,
    SubZeroAuth,
)
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
    }
)


class SubZeroConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Sub-Zero Group config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect account credentials."""
        errors: dict[str, str] = {}
        if user_input is not None:
            session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(quote_cookie=False)
            )
            try:
                auth = SubZeroAuth(session)
                tokens = await auth.login(
                    user_input["username"], user_input["password"]
                )
                client = SubZeroClient(session, auth, tokens)
                appliances = await client.async_get_appliances()
            except InvalidCredentials:
                errors["base"] = "invalid_auth"
            except MfaRequired:
                errors["base"] = "mfa_required"
            except AuthFlowChanged:
                errors["base"] = "unknown"
            except AuthError:
                errors["base"] = "invalid_auth"
            except SubZeroConnectionError:
                errors["base"] = "cannot_connect"
            except SubZeroApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surfaced to the user as a form error
                _LOGGER.exception("Unexpected error during Sub-Zero setup")
                errors["base"] = "unknown"
            else:
                if not appliances:
                    errors["base"] = "no_appliances"
                else:
                    await self.async_set_unique_id(tokens.user_id.lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=user_input["username"],
                        data={
                            "tokens": tokens.as_dict(),
                            "username": user_input["username"],
                        },
                    )
            finally:
                await session.close()

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Start a reauthentication flow."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for credentials again after the tokens stop working."""
        errors: dict[str, str] = {}
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        if user_input is not None and entry is not None:
            session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(quote_cookie=False)
            )
            try:
                auth = SubZeroAuth(session)
                tokens = await auth.login(
                    user_input["username"], user_input["password"]
                )
            except InvalidCredentials:
                errors["base"] = "invalid_auth"
            except MfaRequired:
                errors["base"] = "mfa_required"
            except AuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during Sub-Zero reauth")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={
                        **entry.data,
                        "tokens": tokens.as_dict(),
                        "username": user_input["username"],
                    },
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            finally:
                await session.close()

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Return the options flow."""
        return SubZeroOptionsFlow()


class SubZeroOptionsFlow(OptionsFlow):
    """Tune the poll interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            "scan_interval", DEFAULT_SCAN_INTERVAL
        )
        schema = vol.Schema(
            {
                vol.Optional("scan_interval", default=current): vol.All(
                    int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                )
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            description_placeholders={},
        )
