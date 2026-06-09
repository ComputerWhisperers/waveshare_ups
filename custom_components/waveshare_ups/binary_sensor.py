"""Binary sensor entities for the Waveshare UPS."""

from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import WaveshareUPSCoordinator
from .entity import WaveshareUPSEntity


@dataclass(frozen=True, kw_only=True)
class WaveshareBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor metadata with a stable entity-ID suffix."""

    object_id_suffix: str


BINARY_SENSORS = (
    WaveshareBinarySensorDescription(
        key="online",
        name="Status",
        translation_key="online",
        object_id_suffix="status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    WaveshareBinarySensorDescription(
        key="battery_state",
        name="Battery State",
        translation_key="battery_state",
        object_id_suffix="battery_state",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    WaveshareBinarySensorDescription(
        key="initiate_shutdown",
        name="Initiate Shutdown",
        translation_key="initiate_shutdown",
        object_id_suffix="initiate_shutdown",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    WaveshareBinarySensorDescription(
        key="battery_maintenance",
        name="Battery Maintenance",
        translation_key="battery_maintenance",
        object_id_suffix="battery_maintenance",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
    WaveshareBinarySensorDescription(
        key="battery_fault",
        name="Battery Fault",
        translation_key="battery_fault",
        object_id_suffix="battery_fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add Waveshare UPS binary sensors."""
    coordinator: WaveshareUPSCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        WaveshareUPSBinarySensor(coordinator, entry, description)
        for description in BINARY_SENSORS
    )


class WaveshareUPSBinarySensor(WaveshareUPSEntity, BinarySensorEntity):
    """Expose one boolean value from the coordinator snapshot."""

    def __init__(
        self,
        coordinator: WaveshareUPSCoordinator,
        entry: ConfigEntry,
        description: WaveshareBinarySensorDescription,
    ) -> None:
        WaveshareUPSEntity.__init__(
            self,
            coordinator,
            entry,
            "binary_sensor",
            description.key,
            description.object_id_suffix,
        )
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the latest binary state."""
        return getattr(self.coordinator.data, self.entity_description.key)

    @property
    def available(self) -> bool:
        """Keep connectivity visible when the UPS is offline."""
        metadata_sensor = self.entity_description.key in {
            "online",
            "battery_maintenance",
            "battery_fault",
        }
        return self.coordinator.last_update_success and (
            metadata_sensor or self.coordinator.data.online
        )
