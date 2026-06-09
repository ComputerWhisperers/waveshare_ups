"""Diagnostics support for the Waveshare UPS integration."""

from dataclasses import asdict
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import WaveshareUPSCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return configuration, current readings, and internal wear counters."""
    coordinator: WaveshareUPSCoordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "config_entry": {
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "current_data": asdict(coordinator.data),
        "battery_health": coordinator.battery_health_diagnostics,
    }
