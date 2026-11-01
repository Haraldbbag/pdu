"""Intellinet IP PDU integration."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_USERNAME,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import PduClient, PduError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN, SERVICE_SET_OUTLETS
from .coordinator import PduCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

ATTR_STATE = "state"
SET_OUTLETS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTITY_ID): cv.entity_ids,
        vol.Required(ATTR_STATE): vol.In(["on", "off"]),
    }
)


@dataclass(slots=True)
class PduData:
    """Runtime data of one PDU."""

    client: PduClient
    coordinator: PduCoordinator


type PduConfigEntry = ConfigEntry[PduData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the set_outlets action."""

    async def set_outlets(call: ServiceCall) -> None:
        registry = er.async_get(hass)
        wanted: dict[str, list[int]] = defaultdict(list)
        for entity_id in call.data[ATTR_ENTITY_ID]:
            reg = registry.async_get(entity_id)
            if (
                reg is None
                or reg.platform != DOMAIN
                or reg.domain != Platform.SWITCH
                or "_outlet_" not in (reg.unique_id or "")
                or reg.config_entry_id is None
            ):
                raise ServiceValidationError(f"{entity_id} is not a PDU outlet")
            wanted[reg.config_entry_id].append(int(reg.unique_id.rsplit("_", 1)[1]))

        turn_on = call.data[ATTR_STATE] == "on"
        for entry_id, indexes in wanted.items():
            entry: PduConfigEntry | None = hass.config_entries.async_get_entry(entry_id)
            if entry is None or not hasattr(entry, "runtime_data"):
                raise HomeAssistantError(f"PDU {entry_id} is not loaded")
            try:
                await entry.runtime_data.client.set_outlets(indexes, turn_on)
            except PduError as err:
                raise HomeAssistantError(f"{entry.title}: {err}") from err
            await entry.runtime_data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN, SERVICE_SET_OUTLETS, set_outlets, schema=SET_OUTLETS_SCHEMA
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PduConfigEntry) -> bool:
    """Set up one PDU."""
    client = PduClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = PduCoordinator(
        hass,
        entry,
        client,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )
    await coordinator.async_config_entry_first_refresh()
    try:
        await client.get_delays()
    except PduError as err:
        _LOGGER.warning(
            "%s: could not read outlet delays, assuming %s s: %s",
            entry.title,
            client.on_delays[0],
            err,
        )
    entry.runtime_data = PduData(client=client, coordinator=coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: PduConfigEntry) -> None:
    """Reload after the options (names, interval) were changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PduConfigEntry) -> bool:
    """Unload one PDU."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
