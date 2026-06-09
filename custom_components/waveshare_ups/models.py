"""Hardware profiles and data models for Waveshare UPS boards."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HardwareProfile:
    """INA219 calibration and battery characteristics for a UPS model."""

    calibration: int
    configuration: int
    current_lsb_ma: float
    power_lsb_w: float
    invert_current: bool
    empty_voltage: float
    full_voltage: float
    critical_voltage: float
    charged_voltage: float | None = None
    discharge_curve: tuple[tuple[float, float], ...] = ()


@dataclass(frozen=True, slots=True)
class ElectricalSample:
    """Measurements read directly from the INA219."""

    bus_voltage: float
    current_ma: float
    power_w: float
    sense_voltage: float


# Configuration words follow the INA219 register map:
# continuous shunt+bus conversion, 12-bit/32-sample ADC averaging.
PROFILE_AB = HardwareProfile(
    calibration=4096,
    configuration=0x3EEF,
    current_lsb_ma=0.1,
    power_lsb_w=0.002,
    invert_current=False,
    empty_voltage=6.0,
    full_voltage=8.4,
    critical_voltage=6.4,
)

PROFILE_D = HardwareProfile(
    calibration=26868,
    configuration=0x0EEF,
    current_lsb_ma=0.1524,
    power_lsb_w=0.003048,
    invert_current=True,
    empty_voltage=3.0,
    full_voltage=4.2,
    critical_voltage=3.2,
)

PROFILE_3S = HardwareProfile(
    calibration=26868,
    configuration=0x0EEF,
    current_lsb_ma=0.1524,
    power_lsb_w=0.003048,
    invert_current=False,
    empty_voltage=9.0,
    full_voltage=12.6,
    critical_voltage=9.6,
    charged_voltage=12.49,
    discharge_curve=(
        (9.0, 0),
        (9.6, 5),
        (10.5, 15),
        (11.1, 30),
        (11.4, 45),
        (11.7, 65),
        (11.9, 78),
        (12.0, 83),
        (12.1, 86),
        (12.3, 92),
        (12.36, 94),
        (12.40, 96),
        (12.44, 98),
        (12.47, 99),
        (12.48, 99),
        (12.49, 100),
    ),
)

HARDWARE_PROFILES = {
    "a": PROFILE_AB,
    "b": PROFILE_AB,
    "d": PROFILE_D,
    "3s": PROFILE_3S,
}


def get_profile(model: str) -> HardwareProfile:
    """Return the hardware profile for a configured model."""
    return HARDWARE_PROFILES.get(model.lower(), PROFILE_AB)
