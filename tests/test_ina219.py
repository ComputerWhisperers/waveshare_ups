"""Tests for the independent INA219 register driver."""

from conftest import load_module

models = load_module("models")
ina219 = load_module("ina219")


class FakeBus:
    """Record register writes and return configured register values."""

    def __init__(self, registers: dict[int, int]) -> None:
        self.registers = registers
        self.writes: list[tuple[int, int, list[int]]] = []

    def read_i2c_block_data(
        self, address: int, register: int, length: int
    ) -> list[int]:
        value = self.registers[register]
        return [(value >> 8) & 0xFF, value & 0xFF]

    def write_i2c_block_data(
        self, address: int, register: int, data: list[int]
    ) -> None:
        self.writes.append((address, register, data))


def test_3s_register_conversion() -> None:
    bus = FakeBus(
        {
            ina219.REG_CURRENT: 0xFF38,
            ina219.REG_BUS_VOLTAGE: 0x61A8,
            ina219.REG_POWER: 1476,
            ina219.REG_SENSE_VOLTAGE: 0xFFEC,
        }
    )
    monitor = ina219.INA219(bus, 0x43, models.PROFILE_3S)
    monitor.configure()
    sample = monitor.read_sample()

    assert sample.bus_voltage == 12.5
    assert round(sample.current_ma, 2) == -30.48
    assert round(sample.power_w, 3) == 4.499
    assert sample.sense_voltage == -0.0002
    assert bus.writes[0] == (0x43, ina219.REG_CALIBRATION, [0x68, 0xF4])
    assert bus.writes[1] == (0x43, ina219.REG_CONFIGURATION, [0x0E, 0xEF])


def test_model_d_reverses_current_direction() -> None:
    bus = FakeBus(
        {
            ina219.REG_CURRENT: 100,
            ina219.REG_BUS_VOLTAGE: 0,
            ina219.REG_POWER: 0,
            ina219.REG_SENSE_VOLTAGE: 0,
        }
    )
    sample = ina219.INA219(bus, 0x43, models.PROFILE_D).read_sample()
    assert sample.current_ma == -15.24


def test_signed_register_uses_twos_complement() -> None:
    bus = FakeBus({ina219.REG_CURRENT: 0xFFFF})
    monitor = ina219.INA219(bus, 0x43, models.PROFILE_3S)
    assert monitor._read_signed(ina219.REG_CURRENT) == -1
