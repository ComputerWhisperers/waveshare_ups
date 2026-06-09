"""Fail-safe GPIO relay control for Raspberry Pi utility power."""

from pathlib import Path
from types import ModuleType


class RelayError(Exception):
    """Raised when the GPIO utility relay cannot be controlled."""


class UtilityRelay:
    """Own one GPIO line whose energized state disconnects utility power."""

    def __init__(
        self,
        gpio_line: int,
        active_low: bool,
        *,
        gpiod_module: ModuleType | None = None,
        device_paths: tuple[str, ...] | None = None,
    ) -> None:
        if gpio_line in {2, 3}:
            raise RelayError("GPIO2 and GPIO3 are reserved for UPS I2C.")

        if gpiod_module is None:
            import gpiod as gpiod_module

        self._gpiod = gpiod_module
        self._gpio_line = gpio_line
        self._active_low = active_low
        self._request = None
        self._connected = True
        paths = device_paths or tuple(f"/dev/gpiochip{index}" for index in range(8))
        self._device = find_pinctrl_gpiochip(gpiod_module, paths)

    @property
    def connected(self) -> bool:
        """Return whether the requested output state connects utility."""
        return self._connected

    @property
    def device(self) -> str:
        """Return the selected GPIO character device."""
        return self._device

    def open(self) -> None:
        """Request the line and initialize it to utility connected."""
        direction = self._gpiod.line.Direction.OUTPUT
        initial = self._physical_value(disconnected=False)
        try:
            self._request = self._gpiod.request_lines(
                self._device,
                consumer="waveshare-ups-utility-relay",
                config={
                    self._gpio_line: self._gpiod.LineSettings(
                        direction=direction,
                        output_value=initial,
                    )
                },
            )
        except (OSError, ValueError) as err:
            raise RelayError(
                f"Unable to request GPIO{self._gpio_line} on {self._device}: {err}"
            ) from err
        self._connected = True

    def connect_utility(self) -> None:
        """De-energize the relay so normally closed contacts connect utility."""
        self._set_disconnected(False)

    def disconnect_utility(self) -> None:
        """Energize the relay so normally closed contacts disconnect utility."""
        self._set_disconnected(True)

    def close(self) -> None:
        """Return utility power, then release the GPIO line."""
        request = self._request
        if request is None:
            return
        try:
            self.connect_utility()
        finally:
            try:
                request.release()
            except OSError as err:
                raise RelayError(f"Unable to release the utility relay: {err}") from err
            self._request = None

    def _set_disconnected(self, disconnected: bool) -> None:
        """Set the requested physical output level."""
        if self._request is None:
            raise RelayError("The GPIO relay line is not open.")
        try:
            self._request.set_value(
                self._gpio_line,
                self._physical_value(disconnected),
            )
        except OSError as err:
            raise RelayError(f"Unable to control the utility relay: {err}") from err
        self._connected = not disconnected

    def _physical_value(self, disconnected: bool):
        """Map relay energized state to its physical GPIO level."""
        high = disconnected != self._active_low
        return (
            self._gpiod.line.Value.ACTIVE if high else self._gpiod.line.Value.INACTIVE
        )


def find_pinctrl_gpiochip(
    gpiod_module: ModuleType,
    device_paths: tuple[str, ...],
) -> str:
    """Find the Raspberry Pi header controller on Pi 4 or Pi 5."""
    for device in device_paths:
        if not Path(device).exists() and not gpiod_module.is_gpiochip_device(device):
            continue
        try:
            with gpiod_module.Chip(device) as chip:
                info = chip.get_info()
        except OSError:
            continue
        if "pinctrl" in info.label.lower():
            return device
    raise RelayError("No Raspberry Pi pinctrl GPIO device was found.")
