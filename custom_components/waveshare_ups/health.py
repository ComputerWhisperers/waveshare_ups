"""Persistent battery maintenance and self-test state."""

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from typing import Any

SELF_TEST_CANCELLED = "cancelled"
SELF_TEST_FAILED = "failed"
SELF_TEST_IDLE = "idle"
SELF_TEST_INTERRUPTED = "interrupted"
SELF_TEST_PASSED = "passed"
SELF_TEST_RUNNING = "running"
SELF_TEST_WAITING = "waiting_for_battery"
SELF_TEST_STATUSES = (
    SELF_TEST_IDLE,
    SELF_TEST_WAITING,
    SELF_TEST_RUNNING,
)
SELF_TEST_RESULTS = (
    SELF_TEST_PASSED,
    SELF_TEST_FAILED,
    SELF_TEST_CANCELLED,
    SELF_TEST_INTERRUPTED,
)


@dataclass(frozen=True, slots=True)
class BatteryHealth:
    """Battery usage counters and self-test results retained across restarts."""

    equivalent_cycles: float = 0.0
    deep_discharge_count: int = 0
    high_voltage_hours: float = 0.0
    runtime_baseline: int | None = None
    battery_fault: bool = False
    self_test_status: str = SELF_TEST_IDLE
    self_test_started_at: str | None = None
    self_test_start_percentage: int | None = None
    self_test_start_voltage: float | None = None
    last_self_test_status: str | None = None
    last_self_test_date: str | None = None

    def as_storage(self) -> dict[str, Any]:
        """Return JSON-compatible storage data."""
        return asdict(self)

    @classmethod
    def from_storage(cls, stored: dict[str, Any] | None) -> "BatteryHealth":
        """Restore persisted health state."""
        if not stored:
            return cls()
        status = str(stored.get("self_test_status", SELF_TEST_IDLE))
        if status not in SELF_TEST_STATUSES:
            status = SELF_TEST_IDLE
        return cls(
            equivalent_cycles=float(stored.get("equivalent_cycles", 0.0)),
            deep_discharge_count=int(stored.get("deep_discharge_count", 0)),
            high_voltage_hours=float(stored.get("high_voltage_hours", 0.0)),
            runtime_baseline=_optional_int(stored.get("runtime_baseline")),
            battery_fault=bool(stored.get("battery_fault", False)),
            self_test_status=status,
            self_test_started_at=stored.get("self_test_started_at"),
            self_test_start_percentage=_optional_int(
                stored.get("self_test_start_percentage")
            ),
            self_test_start_voltage=_optional_float(
                stored.get("self_test_start_voltage")
            ),
            last_self_test_status=stored.get("last_self_test_status"),
            last_self_test_date=stored.get("last_self_test_date"),
        )

    def start_self_test(self, now: datetime) -> "BatteryHealth":
        """Arm a self-test before utility power is disconnected."""
        return replace(
            self,
            self_test_status=SELF_TEST_WAITING,
            self_test_started_at=now.isoformat(),
            self_test_start_percentage=None,
            self_test_start_voltage=None,
        )

    def begin_self_test(
        self,
        now: datetime,
        percentage: int,
        voltage: float,
    ) -> "BatteryHealth":
        """Start timing after the UPS changes to battery power."""
        return replace(
            self,
            self_test_status=SELF_TEST_RUNNING,
            self_test_started_at=now.isoformat(),
            self_test_start_percentage=percentage,
            self_test_start_voltage=voltage,
        )

    def finish_self_test(
        self,
        result: str,
        completed_date: date,
        *,
        latch_fault: bool = False,
    ) -> "BatteryHealth":
        """Return to idle and retain the latest test result."""
        return replace(
            self,
            battery_fault=self.battery_fault or latch_fault,
            self_test_status=SELF_TEST_IDLE,
            self_test_started_at=None,
            self_test_start_percentage=None,
            self_test_start_voltage=None,
            last_self_test_status=result,
            last_self_test_date=completed_date.isoformat(),
        )

    def self_test_elapsed(self, now: datetime) -> float:
        """Return elapsed self-test time in seconds."""
        if self.self_test_status != SELF_TEST_RUNNING or not self.self_test_started_at:
            return 0.0
        started = datetime.fromisoformat(self.self_test_started_at)
        return max(0.0, (now - started).total_seconds())

    def self_test_waiting_seconds(self, now: datetime) -> float:
        """Return time spent waiting for the UPS to switch to battery."""
        if self.self_test_status != SELF_TEST_WAITING or not self.self_test_started_at:
            return 0.0
        requested = datetime.fromisoformat(self.self_test_started_at)
        return max(0.0, (now - requested).total_seconds())

    def reset_for_replacement(self) -> "BatteryHealth":
        """Clear all counters and warnings for newly installed batteries."""
        return BatteryHealth()

    @property
    def last_self_test_date_value(self) -> date | None:
        """Return the latest self-test date."""
        if not self.last_self_test_date:
            return None
        return date.fromisoformat(self.last_self_test_date)


def maintenance_due(
    health: BatteryHealth,
    battery_age_days: int | None,
    replacement_days: int,
    cycle_limit: float,
    deep_discharge_limit: int,
    high_voltage_hours_limit: float,
    runtime_calibration: int,
    runtime_degradation_level: int,
) -> bool:
    """Return whether gradual battery wear warrants maintenance."""
    if health.battery_fault:
        return False
    age_due = battery_age_days is not None and battery_age_days >= replacement_days
    cycles_due = health.equivalent_cycles >= cycle_limit
    deep_due = health.deep_discharge_count >= deep_discharge_limit
    voltage_due = health.high_voltage_hours >= high_voltage_hours_limit
    runtime_due = (
        health.runtime_baseline is not None
        and runtime_calibration
        <= health.runtime_baseline * runtime_degradation_level / 100
    )
    return age_due or cycles_due or deep_due or voltage_due or runtime_due


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
