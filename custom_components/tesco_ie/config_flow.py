"""Config flow for Tesco Ireland integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_RATE_LIMIT_READ,
    CONF_RATE_LIMIT_WRITE,
    CONF_TIMEOUT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_RATE_LIMIT_READ,
    DEFAULT_RATE_LIMIT_WRITE,
    DEFAULT_TIMEOUT,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .tesco_api import TescoAPI, TescoAuthError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class TescoIEConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tesco Ireland."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> TescoIEOptionsFlowHandler:
        """Get the options flow for this handler."""
        return TescoIEOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            api = TescoAPI(email, password)
            try:
                await api.async_login()
            except TescoAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(email)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Tesco IE ({email})",
                    data=user_input,
                )
            finally:
                # Always close the session after validation
                await api.async_close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class TescoIEOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Tesco Ireland integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=self.config_entry.options.get(
                            CONF_TIMEOUT, DEFAULT_TIMEOUT
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=120)),
                    vol.Optional(
                        CONF_RATE_LIMIT_READ,
                        default=self.config_entry.options.get(
                            CONF_RATE_LIMIT_READ, DEFAULT_RATE_LIMIT_READ
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10.0)),
                    vol.Optional(
                        CONF_RATE_LIMIT_WRITE,
                        default=self.config_entry.options.get(
                            CONF_RATE_LIMIT_WRITE, DEFAULT_RATE_LIMIT_WRITE
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=10.0)),
                }
            ),
        )
