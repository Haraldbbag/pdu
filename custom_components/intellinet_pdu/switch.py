"""One switch per outlet."""

from __future__ import annotations

import time
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PduConfigEntry
from .api import PduError
from .const import (
    CONF_FIRST_OUTLET,
    CONF_PREFIX,
    OUTLET_COUNT,
    PENDING_SECONDS,
    outlet_name_key,
)
from .coordinator import PduCoordinator
from .entity import PduEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PduConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the 8 outlet switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        PduOutletSwitch(coordinator, entry, index) for index in range(OUTLET_COUNT)
    )


class PduOutletSwitch(PduEntity, SwitchEntity):
    """One outlet of the PDU."""

    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(
        self, coordinator: PduCoordinator, entry: PduConfigEntry, index: int
    ) -> None:
        super().__init__(coordinator, entry)
        self._index = index
        number = entry.data.get(CONF_FIRST_OUTLET, 1) + index
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_outlet_{index}"
        # Name from the options ("Geräte zuordnen"), otherwise numbered.
        self._attr_name = entry.options.get(outlet_name_key(index)) or f"Dose {number:02d}"
        self._attr_extra_state_attributes = {"outlet": number, "pdu_outlet": index + 1}
        if prefix := entry.data.get(CONF_PREFIX):
            # Only a wish for the first creation; existing IDs are never changed.
            self.entity_id = f"switch.pdu_{prefix}_{number:02d}"
        self._pending: tuple[bool, float] | None = None

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.outlets[self._index] is not None

    @property
    def is_on(self) -> bool | None:
        actual = self.coordinator.data.outlets[self._index]
        if self._pending is not None:
            wanted, until = self._pending
            if actual != wanted and time.monotonic() < until:
                return wanted
            self._pending = None
        return actual

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._switch(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._switch(False)

    async def _switch(self, turn_on: bool) -> None:
        try:
            await self.coordinator.client.set_outlets([self._index], turn_on)
        except PduError as err:
            raise HomeAssistantError(f"{self._entry.title}: {err}") from err
        self._pending = (turn_on, time.monotonic() + PENDING_SECONDS)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()
