"""Config flow for GMG Cloud integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .api import GMGCloudApi, GMGAuthError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class GMGCloudConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for GMG Cloud."""

    VERSION = 1

    async def async_step_import(
        self, import_config: dict[str, Any]
    ) -> FlowResult:
        """Handle import from YAML."""
        return await self.async_step_user(import_config)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL].lower()  # GMG uses lowercase emails
            password = user_input[CONF_PASSWORD]

            # Check if already configured
            await self.async_set_unique_id(email)
            self._abort_if_unique_id_configured()

            # Try to authenticate
            api = GMGCloudApi(email, password)
            try:
                if await api.async_authenticate():
                    # Get grills to verify account has grills
                    grills = await api.async_get_grills()
                    await api.async_close()
                    
                    if grills:
                        return self.async_create_entry(
                            title=f"GMG ({email})",
                            data={
                                CONF_EMAIL: email,
                                CONF_PASSWORD: password,
                            },
                        )
                    else:
                        errors["base"] = "no_grills"
                else:
                    errors["base"] = "invalid_auth"
            except GMGAuthError:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            finally:
                await api.async_close()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )


class GMGCloudOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init")
