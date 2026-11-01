"""Polling of status.xml."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PduClient, PduError, PduStatus
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PduCoordinator(DataUpdateCoordinator[PduStatus]):
    """One coordinator per PDU: one status.xml request per interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: PduClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> PduStatus:
        try:
            return await self.client.get_status()
        except PduError as err:
            raise UpdateFailed(str(err)) from err
