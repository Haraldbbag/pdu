"""Base entity."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_FIRMWARE, CONF_MAC, DOMAIN
from .coordinator import PduCoordinator


class PduEntity(CoordinatorEntity[PduCoordinator]):
    """Common device data for all entities of one PDU."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PduCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        # The MAC is only shown, not used as identifier: cheap PDUs sometimes
        # ship with identical MACs, which would merge devices.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
            name=entry.title,
            manufacturer="Intellinet",
            model="IP PDU (8 Ausgänge)",
            sw_version=entry.data.get(CONF_FIRMWARE),
            hw_version=entry.data.get(CONF_MAC),
            configuration_url=f"http://{entry.data[CONF_HOST]}/",
        )
