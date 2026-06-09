"""Pure calculations for UPS state and estimates."""

from datetime import date

from .models import HardwareProfile


def battery_percentage(
    voltage: float,
    profile: HardwareProfile,
    full_charge_voltage: float | None = None,
) -> int:
    """Estimate state of charge from the configured voltage range."""
    charged_voltage = (
        full_charge_voltage
        if full_charge_voltage is not None and profile.charged_voltage is not None
        else profile.charged_voltage
    )
    if charged_voltage is not None and voltage >= charged_voltage:
        return 100

    if profile.discharge_curve:
        curve = _scale_upper_curve(
            profile.discharge_curve,
            profile.charged_voltage,
            charged_voltage,
        )
        percentage = _interpolate_curve(voltage, curve)
    else:
        span = profile.full_voltage - profile.empty_voltage
        percentage = (voltage - profile.empty_voltage) / span * 100
    maximum = 99.0 if charged_voltage is not None else 100.0
    return round(min(maximum, max(0.0, percentage)))


def _scale_upper_curve(
    curve: tuple[tuple[float, float], ...],
    original_full_voltage: float | None,
    configured_full_voltage: float | None,
) -> tuple[tuple[float, float], ...]:
    """Scale the upper charge curve smoothly to a configured full voltage."""
    if (
        original_full_voltage is None
        or configured_full_voltage is None
        or configured_full_voltage == original_full_voltage
    ):
        return curve

    anchor_voltage, _ = next(
        ((voltage, percentage) for voltage, percentage in curve if percentage >= 92),
        curve[-2],
    )
    original_span = original_full_voltage - anchor_voltage
    configured_span = configured_full_voltage - anchor_voltage
    if original_span <= 0 or configured_span <= 0:
        return curve

    return tuple(
        (
            anchor_voltage
            + (voltage - anchor_voltage) * configured_span / original_span,
            percentage,
        )
        if voltage > anchor_voltage
        else (voltage, percentage)
        for voltage, percentage in curve
    )


def _interpolate_curve(
    voltage: float,
    curve: tuple[tuple[float, float], ...],
) -> float:
    """Interpolate percentage between voltage points in a discharge curve."""
    if voltage <= curve[0][0]:
        return curve[0][1]
    for (lower_v, lower_pct), (upper_v, upper_pct) in zip(curve, curve[1:]):
        if voltage <= upper_v:
            position = (voltage - lower_v) / (upper_v - lower_v)
            return lower_pct + position * (upper_pct - lower_pct)
    return curve[-1][1]


def power_source(current_ma: float, threshold_ma: float) -> str:
    """Classify whether utility or battery is powering the load."""
    return "battery" if current_ma < threshold_ma else "utility"


def supply_voltage(bus_voltage: float, sense_voltage: float, source: str) -> float:
    """Return input supply voltage, or zero when utility power is absent."""
    if source == "battery":
        return 0.0
    return bus_voltage + sense_voltage


def is_high_voltage(
    voltage: float, configured_threshold: float, minimum: float
) -> bool:
    """Return whether voltage is strictly above the effective wear threshold."""
    return voltage > max(configured_threshold, minimum)


def stable_percentage(
    previous: float | None,
    measured: int,
    source: str,
    elapsed_seconds: float,
) -> float:
    """Hold utility readings steady and rate-limit discharge voltage sag."""
    if source == "utility" and previous is not None:
        return float(max(previous, measured))
    if previous is None:
        return float(measured)
    if source == "battery" and measured < previous:
        maximum_drop = elapsed_seconds / 120
        return max(float(measured), previous - maximum_drop)
    return min(previous, float(measured)) if source == "battery" else float(measured)


def runtime_hours(
    percentage: int,
    capacity_mah: float,
    current_ma: float,
    source: str,
    expected_load_ma: float,
    calibration_percentage: float,
) -> float | None:
    """Estimate runtime from remaining capacity and expected load."""
    load_ma = expected_load_ma
    if source == "battery":
        load_ma = max(abs(current_ma), expected_load_ma)
    if load_ma <= 0:
        return None
    estimated_hours = capacity_mah * percentage / 100 / load_ma
    return estimated_hours * calibration_percentage / 100


def battery_age_days(replacement_date: date | None, today: date) -> int | None:
    """Return whole days since battery replacement."""
    if replacement_date is None:
        return None
    return max(0, (today - replacement_date).days)


def smooth(previous: float | None, measured: float, factor: float = 0.15) -> float:
    """Apply exponential smoothing to a changing estimate."""
    if previous is None:
        return measured
    return previous + factor * (measured - previous)


def rounded_runtime(hours: float) -> float:
    """Round runtime to six-minute increments."""
    return round(round(hours / 0.1) * 0.1, 1)


def output_condition(
    source: str,
    percentage: int,
    voltage: float,
    warning_level: float,
    critical_level: float,
    critical_voltage: float,
    previous: str | None = None,
    critical_confirmed: bool = True,
    recovery_margin: float = 2,
    voltage_recovery_margin: float = 0.1,
) -> str:
    """Return the UPS output condition with recovery hysteresis."""
    if source == "utility":
        return "normal"
    if previous == "critical" and (
        percentage <= critical_level + recovery_margin
        or voltage <= critical_voltage + voltage_recovery_margin
    ):
        return "critical"
    critical_requested = percentage <= critical_level or voltage <= critical_voltage
    if critical_requested and critical_confirmed:
        return "critical"
    if critical_requested:
        return "warning"
    if previous == "warning" and percentage <= warning_level + recovery_margin:
        return "warning"
    if percentage <= warning_level:
        return "warning"
    return "normal"
