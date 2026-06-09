"""Waveshare UPS integration."""

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_HIGH_VOLTAGE_THRESHOLD,
    DEFAULT_HIGH_VOLTAGE_THRESHOLD,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import WaveshareUPSCoordinator

REMOVED_SENSOR_KEYS = (
    "equivalent_cycles",
    "deep_discharge_count",
    "high_voltage_hours",
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Waveshare UPS config entry."""
    if (
        float(
            entry.options.get(
                CONF_HIGH_VOLTAGE_THRESHOLD,
                DEFAULT_HIGH_VOLTAGE_THRESHOLD,
            )
        )
        < DEFAULT_HIGH_VOLTAGE_THRESHOLD
    ):
        options = dict(entry.options)
        options[CONF_HIGH_VOLTAGE_THRESHOLD] = DEFAULT_HIGH_VOLTAGE_THRESHOLD
        hass.config_entries.async_update_entry(entry, options=options)

    coordinator = WaveshareUPSCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    entity_registry = er.async_get(hass)
    for key in REMOVED_SENSOR_KEYS:
        unique_id = f"{entry.entry_id}::sensor::{key}"
        if entity_id := entity_registry.async_get_entity_id(
            SENSOR_DOMAIN,
            DOMAIN,
            unique_id,
        ):
            entity_registry.async_remove(entity_id)
    reset_unique_id = f"{entry.entry_id}::button::reset_configuration"
    if entity_id := entity_registry.async_get_entity_id(
        BUTTON_DOMAIN,
        DOMAIN,
        reset_unique_id,
    ):
        entity_registry.async_remove(entity_id)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Waveshare UPS config entry."""
    coordinator: WaveshareUPSCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_shutdown()
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    hass.data[DOMAIN].pop(entry.entry_id, None)
    if not hass.data[DOMAIN]:
        hass.data.pop(DOMAIN)
    return True


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
