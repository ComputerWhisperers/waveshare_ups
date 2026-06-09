"""Minimal INA219 driver based on the public Texas Instruments register map."""

from typing import Protocol

from .models import ElectricalSample, HardwareProfile

REG_CONFIGURATION = 0x00
REG_SENSE_VOLTAGE = 0x01
REG_BUS_VOLTAGE = 0x02
REG_POWER = 0x03
REG_CURRENT = 0x04
REG_CALIBRATION = 0x05


class SMBusLike(Protocol):
    """Subset of smbus2 used by the driver."""

    def read_i2c_block_data(
        self, i2c_addr: int, register: int, length: int
    ) -> list[int]:
        """Read bytes from a device register."""

    def write_i2c_block_data(
        self, i2c_addr: int, register: int, data: list[int]
    ) -> None:
        """Write bytes to a device register."""


class INA219:
    """Read voltage, current, and power from an INA219 monitor."""

    def __init__(
        self,
        bus: SMBusLike,
        address: int,
        profile: HardwareProfile,
    ) -> None:
        self._bus = bus
        self._address = address
        self._profile = profile

    def configure(self) -> None:
        """Apply the model-specific calibration and conversion settings."""
        self._write_register(REG_CALIBRATION, self._profile.calibration)
        self._write_register(REG_CONFIGURATION, self._profile.configuration)

    def read_sample(self) -> ElectricalSample:
        """Read one complete set of electrical measurements."""
        self._write_register(REG_CALIBRATION, self._profile.calibration)

        current_raw = self._read_signed(REG_CURRENT)
        bus_raw = self._read_unsigned(REG_BUS_VOLTAGE)
        power_raw = self._read_unsigned(REG_POWER)
        sense_raw = self._read_signed(REG_SENSE_VOLTAGE)

        current_ma = current_raw * self._profile.current_lsb_ma
        if self._profile.invert_current:
            current_ma = -current_ma

        return ElectricalSample(
            bus_voltage=(bus_raw >> 3) * 0.004,
            current_ma=current_ma,
            power_w=power_raw * self._profile.power_lsb_w,
            sense_voltage=sense_raw * 0.00001,
        )

    def _read_unsigned(self, register: int) -> int:
        data = self._bus.read_i2c_block_data(self._address, register, 2)
        if len(data) != 2:
            raise OSError(f"INA219 register 0x{register:02x} returned {len(data)} bytes")
        return (data[0] << 8) | data[1]

    def _read_signed(self, register: int) -> int:
        value = self._read_unsigned(register)
        return value - 0x10000 if value & 0x8000 else value

    def _write_register(self, register: int, value: int) -> None:
        self._bus.write_i2c_block_data(
            self._address,
            register,
            [(value >> 8) & 0xFF, value & 0xFF],
        )
