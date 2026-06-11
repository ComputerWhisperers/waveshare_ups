"""Tests for battery, source, runtime, and output calculations."""

from datetime import date

from conftest import load_module

models = load_module("models")
calculations = load_module("calculations")


def test_3s_charge_curve_and_full_threshold() -> None:
    profile = models.PROFILE_3S
    assert calculations.battery_percentage(12.0, profile) == 83
    assert calculations.battery_percentage(12.26, profile) == 91
    assert calculations.battery_percentage(12.36, profile) == 94
    assert calculations.battery_percentage(12.40, profile) == 96
    assert calculations.battery_percentage(12.44, profile) == 98
    assert calculations.battery_percentage(12.47, profile) == 99
    assert calculations.battery_percentage(12.479, profile) == 99
    assert calculations.battery_percentage(12.48, profile) == 99
    assert calculations.battery_percentage(12.49, profile) == 100
    assert calculations.battery_percentage(9.0, profile) == 0


def test_3s_upper_curve_scales_to_configured_full_voltage() -> None:
    profile = models.PROFILE_3S
    assert calculations.battery_percentage(12.47, profile, 12.47) == 100
    assert calculations.battery_percentage(12.46, profile, 12.47) == 99
    assert calculations.battery_percentage(12.47, profile, 12.52) == 98
    assert calculations.battery_percentage(12.49, profile, 12.52) == 99
    assert calculations.battery_percentage(12.51, profile, 12.52) == 99
    assert calculations.battery_percentage(12.52, profile, 12.52) == 100


def test_current_threshold_is_the_single_power_reference() -> None:
    threshold = -115
    assert calculations.power_source(-50, threshold) == "utility"
    assert calculations.power_source(-115, threshold) == "utility"
    assert calculations.power_source(-116, threshold) == "battery"


def test_percentage_updates_after_cumulative_tenth_volt_change() -> None:
    assert calculations.stable_percentage(100, 99, "battery", 12.50, 12.49) == (
        100,
        12.50,
    )
    assert calculations.stable_percentage(100, 98, "battery", 12.50, 12.44) == (
        100,
        12.50,
    )
    assert calculations.stable_percentage(100, 94, "battery", 12.50, 12.36) == (
        94,
        12.36,
    )
    assert calculations.stable_percentage(94, 95, "battery", 12.36, 12.46) == (
        94,
        12.46,
    )
    assert calculations.stable_percentage(94, 96, "utility", 12.36, 12.46) == (
        96,
        12.46,
    )
    assert calculations.stable_percentage(99, 100, "utility", 12.44, 12.49) == (
        100,
        12.49,
    )


def test_runtime_uses_expected_load_as_a_floor() -> None:
    assert calculations.runtime_hours(100, 3200, -31, "battery", 1000, 100) == 3.2
    assert calculations.runtime_hours(50, 3200, -1600, "battery", 1000, 100) == 1.0
    assert calculations.runtime_hours(100, 3200, 20, "utility", 1000, 100) == 3.2
    assert calculations.runtime_hours(100, 3200, -31, "battery", 1000, 80) == 2.56


def test_supply_voltage_is_zero_on_battery() -> None:
    assert calculations.supply_voltage(12.26, -0.003, "battery") == 0
    assert calculations.supply_voltage(12.49, 0.002, "utility") == 12.492


def test_high_voltage_time_requires_more_than_12_50_volts() -> None:
    assert not calculations.is_high_voltage(12.49, 12.4, 12.5)
    assert not calculations.is_high_voltage(12.50, 12.4, 12.5)
    assert calculations.is_high_voltage(12.51, 12.4, 12.5)
    assert not calculations.is_high_voltage(12.60, 12.75, 12.5)
    assert calculations.is_high_voltage(12.76, 12.75, 12.5)


def test_battery_age_uses_persisted_replacement_date() -> None:
    today = date(2026, 6, 7)
    assert calculations.battery_age_days(None, today) is None
    assert calculations.battery_age_days(date(2026, 5, 8), today) == 30
    assert calculations.battery_age_days(date(2026, 6, 8), today) == 0


def test_output_levels_apply_only_on_battery() -> None:
    assert calculations.output_condition("utility", 5, 9.1, 25, 10, 9.6) == "normal"
    assert calculations.output_condition("battery", 24, 11.5, 25, 10, 9.6) == "warning"
    assert calculations.output_condition("battery", 9, 11.0, 25, 10, 9.6) == "critical"
    assert calculations.output_condition("battery", 60, 9.5, 25, 10, 9.6) == "critical"


def test_output_hysteresis_prevents_threshold_chatter() -> None:
    assert (
        calculations.output_condition(
            "battery", 26, 11.5, 25, 10, 9.6, previous="warning"
        )
        == "warning"
    )
    assert (
        calculations.output_condition(
            "battery", 27, 11.5, 25, 10, 9.6, previous="warning"
        )
        == "warning"
    )
    assert (
        calculations.output_condition(
            "battery", 28, 11.5, 25, 10, 9.6, previous="warning"
        )
        == "normal"
    )
    assert (
        calculations.output_condition(
            "battery", 11, 9.65, 25, 10, 9.6, previous="critical"
        )
        == "critical"
    )
    assert (
        calculations.output_condition(
            "utility", 5, 9.1, 25, 10, 9.6, previous="critical"
        )
        == "normal"
    )


def test_critical_requires_confirmation() -> None:
    assert (
        calculations.output_condition(
            "battery",
            9,
            10.5,
            25,
            10,
            9.6,
            critical_confirmed=False,
        )
        == "warning"
    )
    assert (
        calculations.output_condition(
            "battery",
            9,
            10.5,
            25,
            10,
            9.6,
            critical_confirmed=True,
        )
        == "critical"
    )


def test_runtime_smoothing_and_display_step() -> None:
    assert calculations.smooth(None, 10) == 10
    assert calculations.smooth(10, 20) == 11.5
    assert calculations.rounded_runtime(2.74) == 2.7
    assert calculations.rounded_runtime(2.76) == 2.8
