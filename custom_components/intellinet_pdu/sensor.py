"""Current, temperature, humidity and status of the PDU."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import PduConfigEntry
from .api import PduStatus
from .coordinator import PduCoordinator
from .entity import PduEntity


@dataclass(frozen=True, kw_only=True)
class PduSensorDescription(SensorEntityDescription):
    """Sensor with a value function."""

    value: Callable[[PduStatus], float | str | None]


SENSORS: tuple[PduSensorDescription, ...] = (
    PduSensorDescription(
        key="current",
        translation_key="current",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        suggested_display_precision=1,
        value=lambda s: s.current,
    ),
    PduSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value=lambda s: s.temperature,
    ),
    PduSensorDescription(
        key="humidity",
        translation_key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        value=lambda s: s.humidity,
    ),
    PduSensorDescription(
        key="status",
        translation_key="status",
        value=lambda s: s.status,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PduConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add the PDU sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(PduSensor(coordinator, entry, desc) for desc in SENSORS)


class PduSensor(PduEntity, SensorEntity):
    """A value from status.xml."""

    entity_description: PduSensorDescription

    def __init__(
        self,
        coordinator: PduCoordinator,
        entry: PduConfigEntry,
        description: PduSensorDescription,
    ) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._attr_unique_id = f"{entry.unique_id or entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> float | str | None:
        return self.entity_description.value(self.coordinator.data)
