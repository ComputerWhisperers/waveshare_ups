"""Tests for persistent battery health and self-test state."""

from datetime import date, datetime, timedelta, timezone

from conftest import load_module

health = load_module("health")


def test_self_test_returns_to_idle_and_retains_result() -> None:
    started = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)
    state = health.BatteryHealth().start_self_test(started)
    assert state.self_test_waiting_seconds(started + timedelta(seconds=20)) == 20

    state = state.begin_self_test(started + timedelta(seconds=20), 100, 12.48)
    assert state.self_test_elapsed(started + timedelta(seconds=80)) == 60

    state = state.finish_self_test(
        health.SELF_TEST_PASSED,
        date(2026, 6, 7),
    )
    assert state.self_test_status == health.SELF_TEST_IDLE
    assert state.last_self_test_status == health.SELF_TEST_PASSED
    assert state.last_self_test_date_value == date(2026, 6, 7)


def test_failed_self_test_latches_fault_and_suppresses_maintenance() -> None:
    state = health.BatteryHealth(
        equivalent_cycles=400,
    ).finish_self_test(
        health.SELF_TEST_FAILED,
        date(2026, 6, 7),
        latch_fault=True,
    )

    assert state.battery_fault is True
    assert (
        health.maintenance_due(
            state,
            battery_age_days=2000,
            replacement_days=1095,
            cycle_limit=300,
            deep_discharge_limit=20,
            high_voltage_hours_limit=17520,
            runtime_calibration=50,
            runtime_degradation_level=70,
        )
        is False
    )


def test_each_gradual_wear_limit_can_request_maintenance() -> None:
    assert health.maintenance_due(
        health.BatteryHealth(equivalent_cycles=300),
        None,
        1095,
        300,
        20,
        17520,
        100,
        70,
    )
    assert health.maintenance_due(
        health.BatteryHealth(deep_discharge_count=20),
        None,
        1095,
        300,
        20,
        17520,
        100,
        70,
    )
    assert health.maintenance_due(
        health.BatteryHealth(high_voltage_hours=17520),
        None,
        1095,
        300,
        20,
        17520,
        100,
        70,
    )
    assert health.maintenance_due(
        health.BatteryHealth(runtime_baseline=100),
        None,
        1095,
        300,
        20,
        17520,
        70,
        70,
    )


def test_battery_replacement_clears_all_health_history() -> None:
    state = health.BatteryHealth(
        equivalent_cycles=4.5,
        deep_discharge_count=3,
        high_voltage_hours=200,
        runtime_baseline=85,
        battery_fault=True,
        last_self_test_status=health.SELF_TEST_FAILED,
        last_self_test_date="2026-06-07",
    )

    assert state.reset_for_replacement() == health.BatteryHealth()
