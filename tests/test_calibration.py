"""Tests for persistent runtime calibration state."""

from datetime import datetime, timedelta, timezone

from conftest import load_module

calibration = load_module("calibration")


def test_expected_runtime_to_critical() -> None:
    assert calibration.expected_calibration_hours(3200, 1000, 10) == 2.88


def test_completed_test_learns_runtime_percentage() -> None:
    requested = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)
    started = requested + timedelta(minutes=5)
    finished = started + timedelta(hours=2.304)

    state = calibration.RuntimeCalibration().start(requested, 2.88)
    state = state.begin_discharge(started)
    state = state.complete(finished)

    assert state.status == "idle"
    assert state.last_status == "completed"
    assert state.elapsed_hours == 2.304
    assert state.learned_percentage == 80
    assert state.last_calibration_date == "2026-06-07"


def test_running_test_survives_storage_round_trip() -> None:
    started = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)
    state = calibration.RuntimeCalibration().start(started, 2.88)
    state = state.begin_discharge(started)

    restored = calibration.RuntimeCalibration.from_storage(state.as_storage())

    assert restored.status == "running"
    assert restored.current_elapsed(started + timedelta(minutes=90)) == 1.5


def test_waiting_time_supports_relay_source_timeout() -> None:
    requested = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)
    state = calibration.RuntimeCalibration().start(requested, 2.88)
    assert state.waiting_seconds(requested + timedelta(seconds=60)) == 60


def test_cancelled_test_retains_elapsed_time_without_learning() -> None:
    started = datetime(2026, 6, 7, 12, 0, tzinfo=timezone.utc)
    state = calibration.RuntimeCalibration().start(started, 2.88)
    state = state.begin_discharge(started)
    state = state.cancel(started + timedelta(minutes=30))

    assert state.status == "idle"
    assert state.last_status == "cancelled"
    assert state.elapsed_hours == 0.5
    assert state.learned_percentage is None


def test_calibration_percentage_is_bounded() -> None:
    assert calibration.calibration_percentage(0, 3) == 1
    assert calibration.calibration_percentage(3, 3) == 100
    assert calibration.calibration_percentage(9, 3) == 200


def test_legacy_result_status_migrates_to_idle() -> None:
    restored = calibration.RuntimeCalibration.from_storage(
        {"status": "completed", "learned_percentage": 82}
    )

    assert restored.status == "idle"
    assert restored.last_status == "completed"
    assert restored.learned_percentage == 82
