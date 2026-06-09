"""Persistent runtime calibration state and pure calculations."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

CALIBRATION_CANCELLED = "cancelled"
CALIBRATION_COMPLETED = "completed"
CALIBRATION_IDLE = "idle"
CALIBRATION_RUNNING = "running"
CALIBRATION_WAITING = "waiting_for_battery"
CALIBRATION_STATUSES = (
    CALIBRATION_IDLE,
    CALIBRATION_WAITING,
    CALIBRATION_RUNNING,
)
CALIBRATION_RESULTS = (CALIBRATION_COMPLETED, CALIBRATION_CANCELLED)


@dataclass(frozen=True, slots=True)
class RuntimeCalibration:
    """State retained while measuring real battery runtime."""

    status: str = CALIBRATION_IDLE
    requested_at: str | None = None
    started_at: str | None = None
    expected_hours: float | None = None
    elapsed_hours: float = 0.0
    last_calibration_date: str | None = None
    last_actual_runtime: float | None = None
    learned_percentage: int | None = None
    last_status: str | None = None

    def as_storage(self) -> dict[str, Any]:
        """Return JSON-compatible storage data."""
        return asdict(self)

    @classmethod
    def from_storage(cls, stored: dict[str, Any] | None) -> "RuntimeCalibration":
        """Restore state, ignoring malformed or unknown status values."""
        if not stored:
            return cls()
        status = str(stored.get("status", CALIBRATION_IDLE))
        legacy_result = status if status in CALIBRATION_RESULTS else None
        if status not in CALIBRATION_STATUSES:
            status = CALIBRATION_IDLE
        return cls(
            status=status,
            requested_at=stored.get("requested_at"),
            started_at=stored.get("started_at"),
            expected_hours=_optional_float(stored.get("expected_hours")),
            elapsed_hours=float(stored.get("elapsed_hours", 0.0)),
            last_calibration_date=stored.get("last_calibration_date"),
            last_actual_runtime=_optional_float(stored.get("last_actual_runtime")),
            learned_percentage=_optional_int(stored.get("learned_percentage")),
            last_status=stored.get("last_status") or legacy_result,
        )

    def start(self, now: datetime, expected_hours: float) -> "RuntimeCalibration":
        """Create a test that is waiting for utility power to be removed."""
        return RuntimeCalibration(
            status=CALIBRATION_WAITING,
            requested_at=now.isoformat(),
            expected_hours=expected_hours,
            last_calibration_date=self.last_calibration_date,
            last_actual_runtime=self.last_actual_runtime,
            learned_percentage=self.learned_percentage,
            last_status=self.last_status,
        )

    def begin_discharge(self, now: datetime) -> "RuntimeCalibration":
        """Start timing after the UPS switches to battery power."""
        return RuntimeCalibration(
            status=CALIBRATION_RUNNING,
            requested_at=self.requested_at,
            started_at=now.isoformat(),
            expected_hours=self.expected_hours,
            last_calibration_date=self.last_calibration_date,
            last_actual_runtime=self.last_actual_runtime,
            learned_percentage=self.learned_percentage,
            last_status=self.last_status,
        )

    def cancel(self, now: datetime) -> "RuntimeCalibration":
        """Stop an incomplete test and retain its elapsed time."""
        return RuntimeCalibration(
            status=CALIBRATION_IDLE,
            requested_at=self.requested_at,
            started_at=self.started_at,
            expected_hours=self.expected_hours,
            elapsed_hours=self.current_elapsed(now),
            last_calibration_date=self.last_calibration_date,
            last_actual_runtime=self.last_actual_runtime,
            learned_percentage=self.learned_percentage,
            last_status=CALIBRATION_CANCELLED,
        )

    def complete(
        self,
        now: datetime,
        completion_date: date | None = None,
    ) -> "RuntimeCalibration":
        """Finish a test and calculate its learned runtime percentage."""
        elapsed = self.current_elapsed(now)
        learned = calibration_percentage(elapsed, self.expected_hours)
        return RuntimeCalibration(
            status=CALIBRATION_IDLE,
            requested_at=self.requested_at,
            started_at=self.started_at,
            expected_hours=self.expected_hours,
            elapsed_hours=elapsed,
            last_calibration_date=(completion_date or now.date()).isoformat(),
            last_actual_runtime=elapsed,
            learned_percentage=learned,
            last_status=CALIBRATION_COMPLETED,
        )

    def current_elapsed(self, now: datetime) -> float:
        """Return elapsed battery time, including time across restarts."""
        if self.status != CALIBRATION_RUNNING or not self.started_at:
            return self.elapsed_hours
        started = datetime.fromisoformat(self.started_at)
        return max(0.0, (now - started).total_seconds() / 3600)

    def waiting_seconds(self, now: datetime) -> float:
        """Return time spent waiting for the UPS to switch to battery."""
        if self.status != CALIBRATION_WAITING or not self.requested_at:
            return 0.0
        requested = datetime.fromisoformat(self.requested_at)
        return max(0.0, (now - requested).total_seconds())

    @property
    def last_calibration_date_value(self) -> date | None:
        """Return the stored completion date."""
        if not self.last_calibration_date:
            return None
        return date.fromisoformat(self.last_calibration_date)


def expected_calibration_hours(
    capacity_mah: float,
    load_ma: float,
    critical_percentage: float,
) -> float:
    """Estimate uncalibrated runtime from full charge to Critical."""
    usable_fraction = (100 - critical_percentage) / 100
    return capacity_mah * usable_fraction / load_ma


def calibration_percentage(
    actual_hours: float,
    expected_hours: float | None,
) -> int:
    """Convert measured runtime into the supported calibration range."""
    if not expected_hours or expected_hours <= 0:
        return 100
    return round(min(200.0, max(1.0, actual_hours / expected_hours * 100)))


def _optional_float(value: Any) -> float | None:
    """Convert a storage value to an optional float."""
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    """Convert a storage value to an optional integer."""
    return None if value is None else int(value)
