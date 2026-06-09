"""Shared entity support for the Waveshare UPS integration."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import CONF_HAT_ADDRESS, CONF_HAT_BUS, CONF_HAT_TYPE, DOMAIN
from .coordinator import WaveshareUPSCoordinator


class WaveshareUPSEntity(CoordinatorEntity[WaveshareUPSCoordinator]):
    """Base class that preserves the integration's entity identity contract."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: WaveshareUPSCoordinator,
        entry: ConfigEntry,
        platform: str,
        key: str,
        suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        object_id = f"{slugify(entry.title)}_{suffix}"
        self._attr_unique_id = f"{entry.entry_id}::{platform}::{key}"
        self.entity_id = f"{platform}.{object_id}"
        self._suggested_object_id = object_id

    @property
    def suggested_object_id(self) -> str:
        """Return the complete object ID without area or device prefixes."""
        return self._suggested_object_id

    @property
    def device_info(self) -> DeviceInfo:
        """Describe the physical UPS board."""
        options = self._entry.options
        return DeviceInfo(
            identifiers={
                (
                    DOMAIN,
                    f"{options.get(CONF_HAT_BUS)}::{options.get(CONF_HAT_ADDRESS)}",
                )
            },
            manufacturer="Waveshare",
            model=f"Model {str(options.get(CONF_HAT_TYPE, '')).upper()}",
            name=self._entry.title,
        )
