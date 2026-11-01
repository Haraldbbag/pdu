"""Set up a PDU in the UI; outlet names and interval as options."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util import slugify

from .api import PduAuthError, PduClient, PduError
from .const import (
    CONF_FIRMWARE,
    CONF_FIRST_OUTLET,
    CONF_MAC,
    CONF_PREFIX,
    DEFAULT_PASSWORD,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_USERNAME,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    OUTLET_COUNT,
    outlet_name_key,
)

_LOGGER = logging.getLogger(__name__)


class PduConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add one PDU."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            client = PduClient(
                async_get_clientsession(self.hass),
                host,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.get_status()
                info = await client.get_device_info()
            except PduAuthError:
                errors["base"] = "invalid_auth"
            except PduError as err:
                _LOGGER.debug("PDU %s not reachable: %s", host, err)
                errors["base"] = "cannot_connect"
            else:
                # Host as ID: the PDUs have fixed IPs, the MACs may not be unique.
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                prefix = slugify(user_input.get(CONF_PREFIX) or "")
                return self.async_create_entry(
                    title=(user_input.get(CONF_NAME) or info.name or f"PDU {host}").strip(),
                    data={
                        CONF_HOST: host,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                        CONF_PREFIX: prefix,
                        CONF_FIRST_OUTLET: user_input[CONF_FIRST_OUTLET],
                        CONF_MAC: info.mac,
                        CONF_FIRMWARE: info.firmware,
                    },
                )

        user_input = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=user_input.get(CONF_HOST, "")): str,
                vol.Required(
                    CONF_USERNAME, default=user_input.get(CONF_USERNAME, DEFAULT_USERNAME)
                ): str,
                vol.Required(
                    CONF_PASSWORD, default=user_input.get(CONF_PASSWORD, DEFAULT_PASSWORD)
                ): str,
                vol.Optional(CONF_NAME, default=user_input.get(CONF_NAME, "")): str,
                vol.Optional(CONF_PREFIX, default=user_input.get(CONF_PREFIX, "")): str,
                vol.Required(
                    CONF_FIRST_OUTLET, default=user_input.get(CONF_FIRST_OUTLET, 1)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=999)),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PduOptionsFlow()


class PduOptionsFlow(OptionsFlow):
    """Outlet names (devices on the outlets) and polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            cleaned = {
                key: value.strip() if isinstance(value, str) else value
                for key, value in user_input.items()
            }
            return self.async_create_entry(data=cleaned)

        options = self.config_entry.options
        fields: dict[Any, Any] = {
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=300)),
        }
        for index in range(OUTLET_COUNT):
            key = outlet_name_key(index)
            fields[
                vol.Optional(key, description={"suggested_value": options.get(key, "")})
            ] = str
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
