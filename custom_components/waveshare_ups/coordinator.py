"""Polling coordinator for the Waveshare UPS."""

from dataclasses import dataclass, replace
from datetime import date, timedelta
import logging
from time import monotonic

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from smbus2 import SMBus

from .calibration import (
    CALIBRATION_IDLE,
    CALIBRATION_RUNNING,
    CALIBRATION_WAITING,
    RuntimeCalibration,
    expected_calibration_hours,
)
from .calculations import (
    battery_percentage,
    battery_age_days,
    is_high_voltage,
    output_condition,
    power_source,
    rounded_runtime,
    runtime_hours,
    smooth,
    stable_percentage,
    supply_voltage,
)
from .const import (
    CONF_AUTOMATIC_TESTING,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_CURRENT_THRESHOLD,
    CONF_BATTERY_REPLACEMENT_DATE,
    CONF_BATTERY_REPLACEMENT_DAYS,
    CONF_CYCLE_LIMIT,
    CONF_CRITICAL_BATTERY_LEVEL,
    CONF_DEEP_DISCHARGE_COUNT_LIMIT,
    CONF_DEEP_DISCHARGE_LEVEL,
    CONF_FULL_CHARGE_VOLTAGE,
    CONF_HAT_ADDRESS,
    CONF_HAT_BUS,
    CONF_HAT_TYPE,
    CONF_HIGH_VOLTAGE_HOURS_LIMIT,
    CONF_HIGH_VOLTAGE_THRESHOLD,
    CONF_RELAY_ACTIVE_LOW,
    CONF_RELAY_GPIO,
    CONF_RELAY_SOURCE_TIMEOUT,
    CONF_RELAY_TEST_TIMEOUT,
    CONF_RUNTIME_DEGRADATION_LEVEL,
    CONF_RUNTIME_LOAD_CURRENT,
    CONF_SELF_TEST_DURATION,
    CONF_SELF_TEST_EMERGENCY_VOLTAGE,
    CONF_SELF_TEST_FAILURE_LEVEL,
    CONF_SELF_TEST_MINIMUM_LEVEL,
    CONF_SELF_TEST_SETTLING_TIME,
    CONF_RUNTIME_CALIBRATION,
    CONF_UPDATE_INTERVAL,
    CONF_WARNING_BATTERY_LEVEL,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_CURRENT_THRESHOLD,
    DEFAULT_BATTERY_REPLACEMENT_DAYS,
    DEFAULT_CRITICAL_BATTERY_LEVEL,
    DEFAULT_CYCLE_LIMIT,
    DEFAULT_DEEP_DISCHARGE_COUNT_LIMIT,
    DEFAULT_DEEP_DISCHARGE_LEVEL,
    DEFAULT_FULL_CHARGE_VOLTAGE,
    DEFAULT_HAT_TYPE,
    DEFAULT_HIGH_VOLTAGE_HOURS_LIMIT,
    DEFAULT_HIGH_VOLTAGE_THRESHOLD,
    DEFAULT_RELAY_ACTIVE_LOW,
    DEFAULT_RELAY_GPIO,
    DEFAULT_RELAY_SOURCE_TIMEOUT,
    DEFAULT_RELAY_TEST_TIMEOUT,
    DEFAULT_RUNTIME_DEGRADATION_LEVEL,
    DEFAULT_RUNTIME_CALIBRATION,
    DEFAULT_RUNTIME_LOAD_CURRENT,
    DEFAULT_SELF_TEST_DURATION,
    DEFAULT_SELF_TEST_EMERGENCY_VOLTAGE,
    DEFAULT_SELF_TEST_FAILURE_LEVEL,
    DEFAULT_SELF_TEST_MINIMUM_LEVEL,
    DEFAULT_SELF_TEST_SETTLING_TIME,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_WARNING_BATTERY_LEVEL,
    DOMAIN,
)
from .health import (
    SELF_TEST_CANCELLED,
    SELF_TEST_FAILED,
    SELF_TEST_IDLE,
    SELF_TEST_INTERRUPTED,
    SELF_TEST_PASSED,
    SELF_TEST_RUNNING,
    SELF_TEST_WAITING,
    BatteryHealth,
    maintenance_due,
)
from .ina219 import INA219
from .models import ElectricalSample, get_profile
from .relay import RelayError, UtilityRelay

_LOGGER = logging.getLogger(__name__)
CRITICAL_CONFIRMATION_SECONDS = 20
HIGH_VOLTAGE_CONFIRMATION_SECONDS = 15
HIGH_VOLTAGE_RECOVERY_MARGIN = 0.05
SELF_TEST_PERCENTAGE_CONFIRMATION_SECONDS = 5


@dataclass(frozen=True, slots=True)
class UPSData:
    """Complete state published by one coordinator refresh."""

    online: bool
    measured_battery_percentage: int | None = None
    battery_percentage: int | None = None
    runtime: float | None = None
    ups_state: str | None = None
    output: str | None = None
    current: float | None = None
    load_voltage: float | None = None
    supply_voltage: float | None = None
    current_sense_voltage: float | None = None
    power: float | None = None
    battery_state: bool | None = None
    last_battery_change: date | None = None
    battery_age: int | None = None
    calibration_status: str | None = None
    calibration_elapsed: float | None = None
    last_runtime_calibration: date | None = None
    last_calibration_status: str | None = None
    equivalent_cycles: float | None = None
    deep_discharge_count: int | None = None
    high_voltage_hours: float | None = None
    self_test_status: str | None = None
    last_self_test_status: str | None = None
    last_self_test_date: date | None = None
    initiate_shutdown: bool | None = None
    battery_maintenance: bool | None = None
    battery_fault: bool | None = None


class WaveshareUPSCoordinator(DataUpdateCoordinator[UPSData]):
    """Read the board and calculate all Home Assistant states."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._entry = entry
        self._displayed_percentage: float | None = None
        self._smoothed_runtime: float | None = None
        self._last_percentage_update: float | None = None
        self._critical_candidate_since: float | None = None
        self._high_voltage_candidate_since: float | None = None
        self._self_test_percentage_candidate: int | None = None
        self._self_test_percentage_candidate_since: float | None = None
        self._calibration = RuntimeCalibration()
        self._health = BatteryHealth()
        self._relay: UtilityRelay | None = None
        self._relay_error = False
        self._calibration_store: Store[dict[str, object]] = Store(
            hass,
            1,
            f"{DOMAIN}.{entry.entry_id}.runtime_calibration",
        )
        self._health_store: Store[dict[str, object]] = Store(
            hass,
            1,
            f"{DOMAIN}.{entry.entry_id}.battery_health",
        )
        self._last_health_update: float | None = None
        self._last_health_save = monotonic()
        self._discharge_floor: int | None = None
        self._deep_discharge_counted = False
        self._health_dirty = False
        update_seconds = entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_seconds),
        )

    async def async_initialize(self) -> None:
        """Load persistent runtime calibration state."""
        stored = await self._calibration_store.async_load()
        self._calibration = RuntimeCalibration.from_storage(stored)
        self._health = BatteryHealth.from_storage(await self._health_store.async_load())
        if self.automatic_testing:
            await self._async_open_relay()
        if self._health.self_test_status != SELF_TEST_IDLE:
            self._health = self._health.finish_self_test(
                SELF_TEST_INTERRUPTED,
                dt_util.now().date(),
            )
            await self._async_save_health()

    async def async_shutdown(self) -> None:
        """Return utility power and release the optional GPIO relay."""
        await self._async_connect_utility()
        if self._health_dirty:
            await self._async_save_health()
        relay = self._relay
        if relay is not None:
            try:
                await self.hass.async_add_executor_job(relay.close)
            except RelayError as err:
                _LOGGER.error("Unable to release the utility relay: %s", err)
            self._relay = None

    async def _async_update_data(self) -> UPSData:
        try:
            sample = await self.hass.async_add_executor_job(self._read_hardware)
        except (FileNotFoundError, OSError) as err:
            _LOGGER.warning("Unable to communicate with the UPS: %s", err)
            await self._async_abort_automatic_tests()
            return self._offline_data()
        data = self._build_data(sample)
        data = await self._async_advance_calibration(data)
        data = await self._async_advance_self_test(data)
        await self._async_track_health(data)
        return self._with_persistent_data(data)

    def _battery_metadata(self) -> tuple[date | None, int | None]:
        """Return persisted replacement date and its current age."""
        stored_date = self._entry.options.get(CONF_BATTERY_REPLACEMENT_DATE)
        replacement_date = date.fromisoformat(stored_date) if stored_date else None
        return replacement_date, battery_age_days(
            replacement_date,
            dt_util.now().date(),
        )

    def _offline_data(self) -> UPSData:
        """Keep battery metadata available when hardware is offline."""
        replacement_date, age = self._battery_metadata()
        return self._with_persistent_data(
            UPSData(
                online=False,
                last_battery_change=replacement_date,
                battery_age=age,
            )
        )

    def _with_persistent_data(self, data: UPSData) -> UPSData:
        """Add persistent calibration, health, and automation values."""
        now = dt_util.utcnow()
        _, age = self._battery_metadata()
        options = self._entry.options
        calibration_value = int(
            options.get(
                CONF_RUNTIME_CALIBRATION,
                DEFAULT_RUNTIME_CALIBRATION,
            )
        )
        maintenance = maintenance_due(
            self._health,
            age,
            int(
                options.get(
                    CONF_BATTERY_REPLACEMENT_DAYS,
                    DEFAULT_BATTERY_REPLACEMENT_DAYS,
                )
            ),
            float(options.get(CONF_CYCLE_LIMIT, DEFAULT_CYCLE_LIMIT)),
            int(
                options.get(
                    CONF_DEEP_DISCHARGE_COUNT_LIMIT,
                    DEFAULT_DEEP_DISCHARGE_COUNT_LIMIT,
                )
            ),
            float(
                options.get(
                    CONF_HIGH_VOLTAGE_HOURS_LIMIT,
                    DEFAULT_HIGH_VOLTAGE_HOURS_LIMIT,
                )
            ),
            calibration_value,
            int(
                options.get(
                    CONF_RUNTIME_DEGRADATION_LEVEL,
                    DEFAULT_RUNTIME_DEGRADATION_LEVEL,
                )
            ),
        )
        initiate_shutdown = (
            data.online
            and data.ups_state == "battery"
            and data.output == "critical"
            and self._calibration.status == CALIBRATION_IDLE
            and self._health.self_test_status == SELF_TEST_IDLE
        )
        return replace(
            data,
            calibration_status=self._calibration.status,
            calibration_elapsed=self._calibration.current_elapsed(now),
            last_runtime_calibration=self._calibration.last_calibration_date_value,
            last_calibration_status=self._calibration.last_status,
            equivalent_cycles=round(self._health.equivalent_cycles, 2),
            deep_discharge_count=self._health.deep_discharge_count,
            high_voltage_hours=round(self._health.high_voltage_hours, 1),
            self_test_status=self._health.self_test_status,
            last_self_test_status=self._health.last_self_test_status,
            last_self_test_date=self._health.last_self_test_date_value,
            initiate_shutdown=initiate_shutdown,
            battery_maintenance=maintenance,
            battery_fault=self._health.battery_fault,
        )

    @property
    def automatic_testing(self) -> bool:
        """Return whether calibration and self-test may control GPIO."""
        options = self._entry.options
        value = options.get(CONF_AUTOMATIC_TESTING)
        if value is not None:
            return bool(value)
        return bool(
            options.get("relay_enabled", False)
            or options.get("calibration_mode") == "automatic"
        )

    async def async_start_runtime_calibration(self) -> None:
        """Start a test after checking that the UPS is fully charged."""
        data = self.data
        if not data or not data.online:
            raise HomeAssistantError("The UPS must be online to start calibration.")
        if data.ups_state != "utility":
            raise HomeAssistantError(
                "Connect utility power before starting calibration."
            )
        if data.battery_percentage != 100:
            raise HomeAssistantError(
                "Charge the batteries to 100% before starting calibration."
            )
        if self._calibration.status in {
            CALIBRATION_WAITING,
            CALIBRATION_RUNNING,
        }:
            raise HomeAssistantError("Runtime calibration is already active.")
        if self._health.self_test_status != SELF_TEST_IDLE:
            raise HomeAssistantError("A battery self-test is active.")

        options = self._entry.options
        expected_hours = expected_calibration_hours(
            float(options.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)),
            float(
                options.get(
                    CONF_RUNTIME_LOAD_CURRENT,
                    DEFAULT_RUNTIME_LOAD_CURRENT,
                )
            ),
            float(
                options.get(
                    CONF_CRITICAL_BATTERY_LEVEL,
                    DEFAULT_CRITICAL_BATTERY_LEVEL,
                )
            ),
        )
        self._calibration = self._calibration.start(
            dt_util.utcnow(),
            expected_hours,
        )
        await self._async_save_calibration()
        if self.automatic_testing:
            if self._relay is None or self._relay_error:
                self._calibration = self._calibration.cancel(dt_util.utcnow())
                await self._async_save_calibration()
                raise HomeAssistantError(
                    "The configured GPIO utility relay is unavailable."
                )
            try:
                await self.hass.async_add_executor_job(self._relay.disconnect_utility)
            except RelayError as err:
                self._relay_error = True
                self._calibration = self._calibration.cancel(dt_util.utcnow())
                await self._async_save_calibration()
                await self._async_connect_utility()
                raise HomeAssistantError(
                    f"Unable to disconnect utility power: {err}"
                ) from err
        self.async_set_updated_data(self._with_persistent_data(data))
        if self.automatic_testing:
            await self.async_request_refresh()

    async def async_cancel_runtime_calibration(self) -> None:
        """Cancel an active calibration test."""
        if self._calibration.status not in {
            CALIBRATION_WAITING,
            CALIBRATION_RUNNING,
        }:
            raise HomeAssistantError("No runtime calibration is active.")
        self._calibration = self._calibration.cancel(dt_util.utcnow())
        await self._async_connect_utility()
        await self._async_save_calibration()
        if self.data:
            self.async_set_updated_data(self._with_persistent_data(self.data))

    async def _async_advance_calibration(self, data: UPSData) -> UPSData:
        """Advance the calibration state from the latest UPS reading."""
        now = dt_util.utcnow()
        changed = False
        completed = False

        if (
            self._calibration.status == CALIBRATION_WAITING
            and data.ups_state == "battery"
        ):
            self._calibration = self._calibration.begin_discharge(now)
            changed = True
        elif (
            self._calibration.status == CALIBRATION_WAITING
            and self._relay is not None
            and self._calibration.waiting_seconds(now)
            >= float(
                self._entry.options.get(
                    CONF_RELAY_SOURCE_TIMEOUT,
                    DEFAULT_RELAY_SOURCE_TIMEOUT,
                )
            )
        ):
            _LOGGER.error(
                "Calibration cancelled because the UPS did not switch to battery"
            )
            self._calibration = self._calibration.cancel(now)
            await self._async_connect_utility()
            changed = True
        elif self._calibration.status == CALIBRATION_RUNNING:
            if data.output == "critical":
                await self._async_connect_utility()
                self._calibration = self._calibration.complete(
                    now,
                    dt_util.now().date(),
                )
                changed = True
                completed = True
            elif data.ups_state == "utility":
                self._calibration = self._calibration.cancel(now)
                await self._async_connect_utility()
                changed = True
            elif self._relay is not None and self._calibration.current_elapsed(
                now
            ) >= float(
                self._entry.options.get(
                    CONF_RELAY_TEST_TIMEOUT,
                    DEFAULT_RELAY_TEST_TIMEOUT,
                )
            ):
                _LOGGER.error(
                    "Calibration cancelled after reaching the maximum duration"
                )
                self._calibration = self._calibration.cancel(now)
                await self._async_connect_utility()
                changed = True

        if changed:
            await self._async_save_calibration()
        if completed and self._calibration.learned_percentage is not None:
            options = dict(self._entry.options)
            options[CONF_RUNTIME_CALIBRATION] = self._calibration.learned_percentage
            if self._health.runtime_baseline is None:
                self._health = replace(
                    self._health,
                    runtime_baseline=self._calibration.learned_percentage,
                )
                await self._async_save_health()
            self.hass.config_entries.async_update_entry(
                self._entry,
                options=options,
            )

        return data

    async def _async_save_calibration(self) -> None:
        """Persist the calibration test and latest result."""
        await self._calibration_store.async_save(self._calibration.as_storage())

    async def async_start_self_test(self) -> None:
        """Start a short relay-controlled battery self-test."""
        data = self.data
        if not self.automatic_testing:
            raise HomeAssistantError(
                "Enable Automatic Calibration and Self-Test in Configure first."
            )
        if self._relay is None or self._relay_error:
            raise HomeAssistantError(
                "The configured GPIO utility relay is unavailable."
            )
        if not data or not data.online:
            raise HomeAssistantError("The UPS must be online to start a self-test.")
        if data.ups_state != "utility":
            raise HomeAssistantError(
                "Connect utility power before starting a self-test."
            )
        minimum_level = int(
            self._entry.options.get(
                CONF_SELF_TEST_MINIMUM_LEVEL,
                DEFAULT_SELF_TEST_MINIMUM_LEVEL,
            )
        )
        if (
            data.measured_battery_percentage is None
            or data.measured_battery_percentage < minimum_level
        ):
            raise HomeAssistantError(
                f"Charge the batteries to at least {minimum_level}% first."
            )
        if self._calibration.status != CALIBRATION_IDLE:
            raise HomeAssistantError("Runtime calibration is active.")
        if self._health.self_test_status != SELF_TEST_IDLE:
            raise HomeAssistantError("A battery self-test is already active.")

        self._health = self._health.start_self_test(dt_util.utcnow())
        await self._async_save_health()
        try:
            await self.hass.async_add_executor_job(self._relay.disconnect_utility)
        except RelayError as err:
            self._relay_error = True
            self._health = self._health.finish_self_test(
                SELF_TEST_CANCELLED,
                dt_util.now().date(),
            )
            await self._async_save_health()
            await self._async_connect_utility()
            raise HomeAssistantError(
                f"Unable to disconnect utility power: {err}"
            ) from err
        self.async_set_updated_data(self._with_persistent_data(data))
        await self.async_request_refresh()

    async def async_cancel_self_test(self) -> None:
        """Cancel an active battery self-test and restore utility."""
        if self._health.self_test_status == SELF_TEST_IDLE:
            raise HomeAssistantError("No battery self-test is active.")
        self._health = self._health.finish_self_test(
            SELF_TEST_CANCELLED,
            dt_util.now().date(),
        )
        await self._async_connect_utility()
        await self._async_save_health()
        if self.data:
            self.async_set_updated_data(self._with_persistent_data(self.data))

    async def _async_advance_self_test(self, data: UPSData) -> UPSData:
        """Advance a relay-controlled self-test from the latest reading."""
        status = self._health.self_test_status
        if status == SELF_TEST_IDLE:
            return data

        now = dt_util.utcnow()
        options = self._entry.options
        changed = False
        result: str | None = None
        latch_fault = False

        if status == SELF_TEST_WAITING and data.ups_state == "battery":
            percentage = data.measured_battery_percentage
            if percentage is not None and data.load_voltage is not None:
                self._health = self._health.begin_self_test(
                    now,
                    percentage,
                    data.load_voltage,
                )
                changed = True
        elif status == SELF_TEST_WAITING and self._health.self_test_waiting_seconds(
            now
        ) >= float(
            options.get(
                CONF_RELAY_SOURCE_TIMEOUT,
                DEFAULT_RELAY_SOURCE_TIMEOUT,
            )
        ):
            result = SELF_TEST_CANCELLED
        elif status == SELF_TEST_RUNNING:
            elapsed = self._health.self_test_elapsed(now)
            settling = float(
                options.get(
                    CONF_SELF_TEST_SETTLING_TIME,
                    DEFAULT_SELF_TEST_SETTLING_TIME,
                )
            )
            if data.ups_state == "utility":
                result = SELF_TEST_INTERRUPTED
            elif elapsed >= settling:
                percentage_failed = (
                    data.measured_battery_percentage is not None
                    and data.measured_battery_percentage
                    <= float(
                        options.get(
                            CONF_SELF_TEST_FAILURE_LEVEL,
                            DEFAULT_SELF_TEST_FAILURE_LEVEL,
                        )
                    )
                )
                voltage_failed = (
                    data.load_voltage is not None
                    and data.load_voltage
                    <= float(
                        options.get(
                            CONF_SELF_TEST_EMERGENCY_VOLTAGE,
                            DEFAULT_SELF_TEST_EMERGENCY_VOLTAGE,
                        )
                    )
                )
                if percentage_failed or voltage_failed:
                    result = SELF_TEST_FAILED
                    latch_fault = True
                elif elapsed >= float(
                    options.get(
                        CONF_SELF_TEST_DURATION,
                        DEFAULT_SELF_TEST_DURATION,
                    )
                ):
                    result = SELF_TEST_PASSED

        if result is not None:
            self._health = self._health.finish_self_test(
                result,
                dt_util.now().date(),
                latch_fault=latch_fault,
            )
            await self._async_connect_utility()
            changed = True
        if changed:
            await self._async_save_health()
        return data

    async def _async_track_health(self, data: UPSData) -> None:
        """Accumulate battery-use counters and persist them periodically."""
        now = monotonic()
        elapsed = (
            now - self._last_health_update
            if self._last_health_update is not None
            else float(
                self._entry.options.get(
                    CONF_UPDATE_INTERVAL,
                    DEFAULT_UPDATE_INTERVAL,
                )
            )
        )
        self._last_health_update = now
        percentage = data.measured_battery_percentage
        health = self._health

        if data.ups_state == "battery" and percentage is not None:
            if self._discharge_floor is None:
                self._discharge_floor = percentage
            elif percentage < self._discharge_floor:
                health = replace(
                    health,
                    equivalent_cycles=health.equivalent_cycles
                    + (self._discharge_floor - percentage) / 100,
                )
                self._discharge_floor = percentage
            deep_level = int(
                self._entry.options.get(
                    CONF_DEEP_DISCHARGE_LEVEL,
                    DEFAULT_DEEP_DISCHARGE_LEVEL,
                )
            )
            if percentage <= deep_level and not self._deep_discharge_counted:
                health = replace(
                    health,
                    deep_discharge_count=health.deep_discharge_count + 1,
                )
                self._deep_discharge_counted = True
        elif data.ups_state == "utility":
            self._discharge_floor = None
            self._deep_discharge_counted = False
            threshold = float(
                self._entry.options.get(
                    CONF_HIGH_VOLTAGE_THRESHOLD,
                    DEFAULT_HIGH_VOLTAGE_THRESHOLD,
                )
            )
            if data.load_voltage is not None and is_high_voltage(
                data.load_voltage,
                threshold,
                DEFAULT_HIGH_VOLTAGE_THRESHOLD,
            ):
                health = replace(
                    health,
                    high_voltage_hours=health.high_voltage_hours + elapsed / 3600,
                )

        if health != self._health:
            self._health = health
            self._health_dirty = True
        if self._health_dirty and now - self._last_health_save >= 60:
            await self._async_save_health()

    async def _async_save_health(self) -> None:
        """Persist battery wear counters, warnings, and self-test results."""
        await self._health_store.async_save(self._health.as_storage())
        self._last_health_save = monotonic()
        self._health_dirty = False

    @property
    def battery_health_diagnostics(self) -> dict[str, object]:
        """Return persistent battery wear data for diagnostics."""
        return self._health.as_storage()

    async def async_battery_replaced(self) -> None:
        """Reset battery history and record a newly installed battery."""
        self._calibration = RuntimeCalibration()
        self._health = self._health.reset_for_replacement()
        self._discharge_floor = None
        self._deep_discharge_counted = False
        await self._async_save_calibration()
        await self._async_save_health()
        options = dict(self._entry.options)
        options[CONF_BATTERY_REPLACEMENT_DATE] = dt_util.now().date().isoformat()
        options[CONF_RUNTIME_CALIBRATION] = DEFAULT_RUNTIME_CALIBRATION
        self.hass.config_entries.async_update_entry(self._entry, options=options)

    async def _async_open_relay(self) -> None:
        """Open the configured GPIO line in its utility-connected state."""
        try:
            relay = await self.hass.async_add_executor_job(self._create_and_open_relay)
        except RelayError as err:
            self._relay_error = True
            _LOGGER.error("GPIO utility relay is unavailable: %s", err)
            return
        self._relay = relay
        self._relay_error = False

    def _create_and_open_relay(self) -> UtilityRelay:
        """Create and open the relay from the executor thread."""
        relay = UtilityRelay(
            int(self._entry.options.get(CONF_RELAY_GPIO, DEFAULT_RELAY_GPIO)),
            bool(
                self._entry.options.get(
                    CONF_RELAY_ACTIVE_LOW,
                    DEFAULT_RELAY_ACTIVE_LOW,
                )
            ),
        )
        relay.open()
        return relay

    async def _async_connect_utility(self) -> None:
        """Return the relay to the fail-safe utility-connected state."""
        relay = self._relay
        if relay is None:
            return
        try:
            await self.hass.async_add_executor_job(relay.connect_utility)
        except RelayError as err:
            self._relay_error = True
            _LOGGER.critical("Unable to reconnect utility power: %s", err)

    async def _async_abort_automatic_tests(self) -> None:
        """Restore utility and retain interrupted automated-test results."""
        changed = False
        if self._calibration.status in {
            CALIBRATION_WAITING,
            CALIBRATION_RUNNING,
        }:
            self._calibration = self._calibration.cancel(dt_util.utcnow())
            await self._async_save_calibration()
            changed = True
        if self._health.self_test_status != SELF_TEST_IDLE:
            self._health = self._health.finish_self_test(
                SELF_TEST_INTERRUPTED,
                dt_util.now().date(),
            )
            await self._async_save_health()
            changed = True
        if changed:
            await self._async_connect_utility()

    def _read_hardware(self) -> ElectricalSample:
        model = self._entry.options.get(CONF_HAT_TYPE, DEFAULT_HAT_TYPE)
        profile = get_profile(model)
        bus_number = int(self._entry.options[CONF_HAT_BUS])
        address = int(self._entry.options[CONF_HAT_ADDRESS], 0)

        with SMBus(bus_number) as bus:
            monitor = INA219(bus, address, profile)
            monitor.configure()
            return monitor.read_sample()

    def _build_data(self, sample: ElectricalSample) -> UPSData:
        options = self._entry.options
        profile = get_profile(options.get(CONF_HAT_TYPE, DEFAULT_HAT_TYPE))
        threshold = float(
            options.get(
                CONF_BATTERY_CURRENT_THRESHOLD,
                DEFAULT_BATTERY_CURRENT_THRESHOLD,
            )
        )
        source = power_source(sample.current_ma, threshold)
        measured_percentage = battery_percentage(
            sample.bus_voltage,
            profile,
            float(
                options.get(
                    CONF_FULL_CHARGE_VOLTAGE,
                    DEFAULT_FULL_CHARGE_VOLTAGE,
                )
            )
            if profile.charged_voltage is not None
            else None,
        )
        now = monotonic()
        elapsed_seconds = (
            now - self._last_percentage_update
            if self._last_percentage_update is not None
            else float(options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
        )
        if (
            self._health.self_test_status != SELF_TEST_IDLE
            and self._displayed_percentage is not None
        ):
            if measured_percentage == round(self._displayed_percentage):
                self._self_test_percentage_candidate = None
                self._self_test_percentage_candidate_since = None
                displayed_percentage = self._displayed_percentage
            else:
                same_direction = (
                    self._self_test_percentage_candidate is not None
                    and (
                        measured_percentage - self._displayed_percentage
                    )
                    * (
                        self._self_test_percentage_candidate
                        - self._displayed_percentage
                    )
                    > 0
                )
                if not same_direction:
                    self._self_test_percentage_candidate_since = now
                self._self_test_percentage_candidate = measured_percentage
                if (
                    self._self_test_percentage_candidate_since is not None
                    and now - self._self_test_percentage_candidate_since
                    >= SELF_TEST_PERCENTAGE_CONFIRMATION_SECONDS
                ):
                    displayed_percentage = float(measured_percentage)
                    self._self_test_percentage_candidate = None
                    self._self_test_percentage_candidate_since = None
                else:
                    displayed_percentage = self._displayed_percentage
        else:
            self._self_test_percentage_candidate = None
            self._self_test_percentage_candidate_since = None
            displayed_percentage = stable_percentage(
                self._displayed_percentage,
                measured_percentage,
                source,
                elapsed_seconds,
            )
        self._displayed_percentage = displayed_percentage
        self._last_percentage_update = now
        rounded_percentage = round(displayed_percentage)

        runtime = runtime_hours(
            rounded_percentage,
            float(options.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY)),
            sample.current_ma,
            source,
            float(
                options.get(
                    CONF_RUNTIME_LOAD_CURRENT,
                    DEFAULT_RUNTIME_LOAD_CURRENT,
                )
            ),
            float(
                options.get(
                    CONF_RUNTIME_CALIBRATION,
                    DEFAULT_RUNTIME_CALIBRATION,
                )
            ),
        )
        displayed_runtime = None
        if runtime is not None:
            self._smoothed_runtime = smooth(self._smoothed_runtime, runtime)
            displayed_runtime = rounded_runtime(self._smoothed_runtime)

        previous_output = self.data.output if self.data and self.data.online else None
        critical_requested = source == "battery" and (
            measured_percentage
            <= float(
                options.get(
                    CONF_CRITICAL_BATTERY_LEVEL,
                    DEFAULT_CRITICAL_BATTERY_LEVEL,
                )
            )
            or sample.bus_voltage <= profile.critical_voltage
        )
        if critical_requested:
            if self._critical_candidate_since is None:
                self._critical_candidate_since = now
        else:
            self._critical_candidate_since = None
        critical_confirmed = (
            previous_output == "critical"
            or sample.bus_voltage <= profile.empty_voltage
            or (
                self._critical_candidate_since is not None
                and now - self._critical_candidate_since
                >= CRITICAL_CONFIRMATION_SECONDS
            )
        )

        output = output_condition(
            source,
            measured_percentage,
            sample.bus_voltage,
            float(
                options.get(
                    CONF_WARNING_BATTERY_LEVEL,
                    DEFAULT_WARNING_BATTERY_LEVEL,
                )
            ),
            float(
                options.get(
                    CONF_CRITICAL_BATTERY_LEVEL,
                    DEFAULT_CRITICAL_BATTERY_LEVEL,
                )
            ),
            profile.critical_voltage,
            previous_output,
            critical_confirmed,
        )
        high_voltage_threshold = max(
            float(
                options.get(
                    CONF_HIGH_VOLTAGE_THRESHOLD,
                    DEFAULT_HIGH_VOLTAGE_THRESHOLD,
                )
            ),
            DEFAULT_HIGH_VOLTAGE_THRESHOLD,
        )
        if source != "utility":
            self._high_voltage_candidate_since = None
        elif previous_output == "high_voltage" and (
            sample.bus_voltage > high_voltage_threshold - HIGH_VOLTAGE_RECOVERY_MARGIN
        ):
            output = "high_voltage"
            self._high_voltage_candidate_since = None
        elif sample.bus_voltage > high_voltage_threshold:
            if self._high_voltage_candidate_since is None:
                self._high_voltage_candidate_since = now
            if (
                now - self._high_voltage_candidate_since
                >= HIGH_VOLTAGE_CONFIRMATION_SECONDS
            ):
                output = "high_voltage"
        else:
            self._high_voltage_candidate_since = None
        replacement_date, age = self._battery_metadata()

        return UPSData(
            online=True,
            measured_battery_percentage=measured_percentage,
            battery_percentage=rounded_percentage,
            runtime=displayed_runtime,
            ups_state=source,
            output=output,
            current=sample.current_ma,
            load_voltage=sample.bus_voltage,
            supply_voltage=supply_voltage(
                sample.bus_voltage,
                sample.sense_voltage,
                source,
            ),
            current_sense_voltage=sample.sense_voltage,
            power=sample.power_w,
            battery_state=sample.current_ma >= threshold,
            last_battery_change=replacement_date,
            battery_age=age,
        )
