"""Shows whether the PDU answers."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PduConfigEntry
from .coordinator import PduCoordinator
from .entity import PduEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PduConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the connectivity sensor."""
    async_add_entities([PduConnectivity(entry.runtime_data.coordinator, entry)])


class PduConnectivity(PduEntity, BinarySensorEntity):
    """On while status.xml can be read."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "connected"

    def __init__(self, coordinator: PduCoordinator, entry: PduConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_connected"

    @property
    def available(self) -> bool:
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success
