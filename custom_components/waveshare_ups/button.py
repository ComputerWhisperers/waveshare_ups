"""Button entities for the Waveshare UPS."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import WaveshareUPSCoordinator
from .entity import WaveshareUPSEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add UPS action buttons."""
    coordinator: WaveshareUPSCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = [
        WaveshareBatteryReplacedButton(coordinator, entry),
        WaveshareStartCalibrationButton(coordinator, entry),
        WaveshareCancelCalibrationButton(coordinator, entry),
    ]
    if coordinator.automatic_testing:
        entities.extend(
            [
                WaveshareStartSelfTestButton(coordinator, entry),
                WaveshareCancelSelfTestButton(coordinator, entry),
            ]
        )
    async_add_entities(entities)


class WaveshareBatteryReplacedButton(WaveshareUPSEntity, ButtonEntity):
    """Record today as the battery replacement date."""

    _attr_name = "Battery Replaced"
    _attr_translation_key = "battery_replaced"
    _attr_icon = "mdi:battery-sync"

    def __init__(
        self,
        coordinator: WaveshareUPSCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            "button",
            "battery_replaced",
            "battery_replaced",
        )

    async def async_press(self) -> None:
        """Persist today as the replacement date."""
        await self.coordinator.async_battery_replaced()


class WaveshareStartCalibrationButton(WaveshareUPSEntity, ButtonEntity):
    """Start a full-charge runtime calibration test."""

    _attr_name = "Start Runtime Calibration"
    _attr_translation_key = "start_runtime_calibration"
    _attr_icon = "mdi:battery-clock"

    def __init__(
        self,
        coordinator: WaveshareUPSCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            "button",
            "start_runtime_calibration",
            "start_runtime_calibration",
        )

    async def async_press(self) -> None:
        """Validate and arm a runtime calibration test."""
        await self.coordinator.async_start_runtime_calibration()


class WaveshareCancelCalibrationButton(WaveshareUPSEntity, ButtonEntity):
    """Cancel an active runtime calibration test."""

    _attr_name = "Cancel Runtime Calibration"
    _attr_translation_key = "cancel_runtime_calibration"
    _attr_icon = "mdi:cancel"

    def __init__(
        self,
        coordinator: WaveshareUPSCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            "button",
            "cancel_runtime_calibration",
            "cancel_runtime_calibration",
        )

    async def async_press(self) -> None:
        """Cancel the current calibration test."""
        await self.coordinator.async_cancel_runtime_calibration()


class WaveshareStartSelfTestButton(WaveshareUPSEntity, ButtonEntity):
    """Start a short relay-controlled battery self-test."""

    _attr_name = "Start Self-Test"
    _attr_translation_key = "start_self_test"
    _attr_icon = "mdi:battery-check"

    def __init__(
        self,
        coordinator: WaveshareUPSCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            "button",
            "start_self_test",
            "start_self_test",
        )

    @property
    def available(self) -> bool:
        """Return whether automatic relay testing is enabled."""
        return super().available and self.coordinator.automatic_testing

    async def async_press(self) -> None:
        """Validate and start a battery self-test."""
        await self.coordinator.async_start_self_test()


class WaveshareCancelSelfTestButton(WaveshareUPSEntity, ButtonEntity):
    """Cancel an active battery self-test."""

    _attr_name = "Cancel Self-Test"
    _attr_translation_key = "cancel_self_test"
    _attr_icon = "mdi:battery-remove"

    def __init__(
        self,
        coordinator: WaveshareUPSCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            "button",
            "cancel_self_test",
            "cancel_self_test",
        )

    @property
    def available(self) -> bool:
        """Return whether automatic relay testing is enabled."""
        return super().available and self.coordinator.automatic_testing

    async def async_press(self) -> None:
        """Cancel the current battery self-test."""
        await self.coordinator.async_cancel_self_test()
