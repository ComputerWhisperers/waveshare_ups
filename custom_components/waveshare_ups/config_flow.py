"""Configuration flow for the Waveshare UPS integration."""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import PERCENTAGE, UnitOfElectricCurrent, UnitOfTime
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.helpers import selector
from smbus2 import SMBus

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
    CONF_NAME,
    CONF_RELAY_ACTIVE_LOW,
    CONF_RELAY_GPIO,
    CONF_RELAY_SOURCE_TIMEOUT,
    CONF_RELAY_TEST_TIMEOUT,
    CONF_RUNTIME_DEGRADATION_LEVEL,
    CONF_RUNTIME_CALIBRATION,
    CONF_RUNTIME_LOAD_CURRENT,
    CONF_SELF_TEST_DURATION,
    CONF_SELF_TEST_EMERGENCY_VOLTAGE,
    CONF_SELF_TEST_FAILURE_LEVEL,
    CONF_SELF_TEST_MINIMUM_LEVEL,
    CONF_SELF_TEST_SETTLING_TIME,
    CONF_UPDATE_INTERVAL,
    CONF_WARNING_BATTERY_LEVEL,
    DEFAULT_AUTOMATIC_TESTING,
    DEFAULT_BATTERY_CAPACITY,
    DEFAULT_BATTERY_CURRENT_THRESHOLD,
    DEFAULT_BATTERY_REPLACEMENT_DAYS,
    DEFAULT_CYCLE_LIMIT,
    DEFAULT_CRITICAL_BATTERY_LEVEL,
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
    SUPPORTED_MODELS,
)
from .options import reset_options

INA219_ADDRESSES = range(0x40, 0x50)
I2C_BUSES = (1, 0)


def _valid_levels(values: dict[str, Any]) -> bool:
    critical = values.get(CONF_CRITICAL_BATTERY_LEVEL, DEFAULT_CRITICAL_BATTERY_LEVEL)
    warning = values.get(CONF_WARNING_BATTERY_LEVEL, DEFAULT_WARNING_BATTERY_LEVEL)
    return 0 <= critical < warning <= 100


def _valid_relay(values: dict[str, Any]) -> bool:
    """Reject GPIO lines reserved for the UPS I2C connection."""
    if not values.get(CONF_AUTOMATIC_TESTING, DEFAULT_AUTOMATIC_TESTING):
        return True
    return int(values.get(CONF_RELAY_GPIO, DEFAULT_RELAY_GPIO)) not in {2, 3}


def _valid_self_test(values: dict[str, Any]) -> bool:
    """Require a usable self-test window and meaningful failure level."""
    duration = int(values.get(CONF_SELF_TEST_DURATION, DEFAULT_SELF_TEST_DURATION))
    settling = int(
        values.get(CONF_SELF_TEST_SETTLING_TIME, DEFAULT_SELF_TEST_SETTLING_TIME)
    )
    minimum = int(
        values.get(CONF_SELF_TEST_MINIMUM_LEVEL, DEFAULT_SELF_TEST_MINIMUM_LEVEL)
    )
    failure = int(
        values.get(CONF_SELF_TEST_FAILURE_LEVEL, DEFAULT_SELF_TEST_FAILURE_LEVEL)
    )
    return settling < duration and failure < minimum


def _valid_address(values: dict[str, Any]) -> bool:
    """Require a valid INA219 I2C address."""
    try:
        address = int(str(values[CONF_HAT_ADDRESS]), 0)
    except (KeyError, TypeError, ValueError):
        return False
    return address in INA219_ADDRESSES


def _model_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(SUPPORTED_MODELS),
            mode=selector.SelectSelectorMode.DROPDOWN,
            translation_key="hat_type",
        )
    )


def _common_schema(
    defaults: dict[str, Any],
    detected_addresses: list[str] | None = None,
) -> dict[Any, Any]:
    fields = {
        vol.Required(
            CONF_HAT_ADDRESS,
            default=defaults.get(
                CONF_HAT_ADDRESS,
                detected_addresses[0] if detected_addresses else "0x43",
            ),
        ): (
            selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=detected_addresses,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            if detected_addresses
            else selector.TextSelector()
        ),
        vol.Required(
            CONF_HAT_TYPE,
            default=defaults.get(CONF_HAT_TYPE, DEFAULT_HAT_TYPE),
        ): _model_selector(),
        vol.Required(
            CONF_BATTERY_CAPACITY,
            default=defaults.get(CONF_BATTERY_CAPACITY, DEFAULT_BATTERY_CAPACITY),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="mAh",
            )
        ),
        vol.Required(
            CONF_BATTERY_CURRENT_THRESHOLD,
            default=defaults.get(
                CONF_BATTERY_CURRENT_THRESHOLD,
                DEFAULT_BATTERY_CURRENT_THRESHOLD,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
            )
        ),
        vol.Required(
            CONF_FULL_CHARGE_VOLTAGE,
            default=defaults.get(
                CONF_FULL_CHARGE_VOLTAGE,
                DEFAULT_FULL_CHARGE_VOLTAGE,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=12.4,
                max=12.6,
                step=0.01,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="V",
            )
        ),
        vol.Required(
            CONF_WARNING_BATTERY_LEVEL,
            default=defaults.get(
                CONF_WARNING_BATTERY_LEVEL, DEFAULT_WARNING_BATTERY_LEVEL
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=100,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Required(
            CONF_CRITICAL_BATTERY_LEVEL,
            default=defaults.get(
                CONF_CRITICAL_BATTERY_LEVEL, DEFAULT_CRITICAL_BATTERY_LEVEL
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=99,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Required(
            CONF_RUNTIME_LOAD_CURRENT,
            default=defaults.get(
                CONF_RUNTIME_LOAD_CURRENT, DEFAULT_RUNTIME_LOAD_CURRENT
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
            )
        ),
        vol.Required(
            CONF_RUNTIME_CALIBRATION,
            default=defaults.get(CONF_RUNTIME_CALIBRATION, DEFAULT_RUNTIME_CALIBRATION),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=200,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Required(
            CONF_AUTOMATIC_TESTING,
            default=defaults.get(
                CONF_AUTOMATIC_TESTING,
                DEFAULT_AUTOMATIC_TESTING,
            ),
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_RELAY_GPIO,
            default=defaults.get(CONF_RELAY_GPIO, DEFAULT_RELAY_GPIO),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=27,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_RELAY_ACTIVE_LOW,
            default=defaults.get(
                CONF_RELAY_ACTIVE_LOW,
                DEFAULT_RELAY_ACTIVE_LOW,
            ),
        ): selector.BooleanSelector(),
        vol.Required(
            CONF_RELAY_SOURCE_TIMEOUT,
            default=defaults.get(
                CONF_RELAY_SOURCE_TIMEOUT,
                DEFAULT_RELAY_SOURCE_TIMEOUT,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=10,
                max=600,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfTime.SECONDS,
            )
        ),
        vol.Required(
            CONF_RELAY_TEST_TIMEOUT,
            default=defaults.get(
                CONF_RELAY_TEST_TIMEOUT,
                DEFAULT_RELAY_TEST_TIMEOUT,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=48,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfTime.HOURS,
            )
        ),
        vol.Required(
            CONF_BATTERY_REPLACEMENT_DAYS,
            default=defaults.get(
                CONF_BATTERY_REPLACEMENT_DAYS,
                DEFAULT_BATTERY_REPLACEMENT_DAYS,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=30,
                max=3650,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfTime.DAYS,
            )
        ),
        vol.Required(
            CONF_CYCLE_LIMIT,
            default=defaults.get(CONF_CYCLE_LIMIT, DEFAULT_CYCLE_LIMIT),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=5000,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_DEEP_DISCHARGE_LEVEL,
            default=defaults.get(
                CONF_DEEP_DISCHARGE_LEVEL,
                DEFAULT_DEEP_DISCHARGE_LEVEL,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=99,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Required(
            CONF_DEEP_DISCHARGE_COUNT_LIMIT,
            default=defaults.get(
                CONF_DEEP_DISCHARGE_COUNT_LIMIT,
                DEFAULT_DEEP_DISCHARGE_COUNT_LIMIT,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=1000,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(
            CONF_HIGH_VOLTAGE_THRESHOLD,
            default=defaults.get(
                CONF_HIGH_VOLTAGE_THRESHOLD,
                DEFAULT_HIGH_VOLTAGE_THRESHOLD,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=DEFAULT_HIGH_VOLTAGE_THRESHOLD,
                max=20,
                step=0.01,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="V",
            )
        ),
        vol.Required(
            CONF_HIGH_VOLTAGE_HOURS_LIMIT,
            default=defaults.get(
                CONF_HIGH_VOLTAGE_HOURS_LIMIT,
                DEFAULT_HIGH_VOLTAGE_HOURS_LIMIT,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=100000,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfTime.HOURS,
            )
        ),
        vol.Required(
            CONF_RUNTIME_DEGRADATION_LEVEL,
            default=defaults.get(
                CONF_RUNTIME_DEGRADATION_LEVEL,
                DEFAULT_RUNTIME_DEGRADATION_LEVEL,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=100,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Required(
            CONF_SELF_TEST_DURATION,
            default=defaults.get(
                CONF_SELF_TEST_DURATION,
                DEFAULT_SELF_TEST_DURATION,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=10,
                max=3600,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfTime.SECONDS,
            )
        ),
        vol.Required(
            CONF_SELF_TEST_MINIMUM_LEVEL,
            default=defaults.get(
                CONF_SELF_TEST_MINIMUM_LEVEL,
                DEFAULT_SELF_TEST_MINIMUM_LEVEL,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=100,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Required(
            CONF_SELF_TEST_SETTLING_TIME,
            default=defaults.get(
                CONF_SELF_TEST_SETTLING_TIME,
                DEFAULT_SELF_TEST_SETTLING_TIME,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=300,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfTime.SECONDS,
            )
        ),
        vol.Required(
            CONF_SELF_TEST_FAILURE_LEVEL,
            default=defaults.get(
                CONF_SELF_TEST_FAILURE_LEVEL,
                DEFAULT_SELF_TEST_FAILURE_LEVEL,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=99,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=PERCENTAGE,
            )
        ),
        vol.Required(
            CONF_SELF_TEST_EMERGENCY_VOLTAGE,
            default=defaults.get(
                CONF_SELF_TEST_EMERGENCY_VOLTAGE,
                DEFAULT_SELF_TEST_EMERGENCY_VOLTAGE,
            ),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=20,
                step=0.01,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement="V",
            )
        ),
        vol.Required(
            CONF_UPDATE_INTERVAL,
            default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=2,
                step=1,
                mode=selector.NumberSelectorMode.BOX,
                unit_of_measurement=UnitOfTime.SECONDS,
            )
        ),
    }
    replacement_date = defaults.get(CONF_BATTERY_REPLACEMENT_DATE)
    fields[
        vol.Optional(
            CONF_BATTERY_REPLACEMENT_DATE,
            default=replacement_date,
        )
        if replacement_date
        else vol.Optional(CONF_BATTERY_REPLACEMENT_DATE)
    ] = selector.DateSelector()
    return fields


def _setup_schema(
    defaults: dict[str, Any],
    detected: dict[str, int],
) -> vol.Schema:
    fields: dict[Any, Any] = {
        vol.Required(
            CONF_NAME,
            default=defaults.get(CONF_NAME, ""),
        ): selector.TextSelector(),
    }
    fields.update(_common_schema(defaults, list(detected)))
    return vol.Schema(fields)


CORE_FIELDS = {
    CONF_HAT_ADDRESS,
    CONF_HAT_TYPE,
    CONF_BATTERY_CAPACITY,
    CONF_BATTERY_CURRENT_THRESHOLD,
    CONF_FULL_CHARGE_VOLTAGE,
    CONF_RUNTIME_LOAD_CURRENT,
    CONF_RUNTIME_CALIBRATION,
    CONF_UPDATE_INTERVAL,
}
SHUTDOWN_FIELDS = {
    CONF_WARNING_BATTERY_LEVEL,
    CONF_CRITICAL_BATTERY_LEVEL,
}
HEALTH_FIELDS = {
    CONF_BATTERY_REPLACEMENT_DATE,
    CONF_BATTERY_REPLACEMENT_DAYS,
    CONF_CYCLE_LIMIT,
    CONF_DEEP_DISCHARGE_LEVEL,
    CONF_DEEP_DISCHARGE_COUNT_LIMIT,
    CONF_HIGH_VOLTAGE_THRESHOLD,
    CONF_HIGH_VOLTAGE_HOURS_LIMIT,
    CONF_RUNTIME_DEGRADATION_LEVEL,
}
TESTING_FIELDS = {
    CONF_AUTOMATIC_TESTING,
    CONF_SELF_TEST_DURATION,
    CONF_SELF_TEST_MINIMUM_LEVEL,
    CONF_SELF_TEST_SETTLING_TIME,
    CONF_SELF_TEST_FAILURE_LEVEL,
    CONF_SELF_TEST_EMERGENCY_VOLTAGE,
    CONF_RELAY_GPIO,
    CONF_RELAY_ACTIVE_LOW,
    CONF_RELAY_SOURCE_TIMEOUT,
    CONF_RELAY_TEST_TIMEOUT,
}


def _group_schema(
    defaults: dict[str, Any],
    names: set[str],
    detected_addresses: list[str] | None = None,
) -> vol.Schema:
    """Return one manageable group from the complete options schema."""
    return vol.Schema(
        {
            marker: field
            for marker, field in _common_schema(
                defaults,
                detected_addresses,
            ).items()
            if marker.schema in names
        }
    )


def _section_schema(
    defaults: dict[str, Any],
    *,
    include_setup: bool = False,
    detected: dict[str, int] | None = None,
) -> vol.Schema:
    """Return all settings in one form with collapsible groups."""
    fields: dict[Any, Any] = {}
    if include_setup:
        assert detected
        fields.update(
            {
                vol.Required(
                    CONF_NAME,
                    default=defaults.get(CONF_NAME, ""),
                ): selector.TextSelector(),
            }
        )
    detected_addresses = list(detected) if detected else None
    fields.update(
        {
            vol.Required("ups_runtime"): section(
                _group_schema(defaults, CORE_FIELDS, detected_addresses),
                {"collapsed": False},
            ),
            vol.Required("shutdown"): section(
                _group_schema(defaults, SHUTDOWN_FIELDS),
                {"collapsed": False},
            ),
            vol.Required("battery_health"): section(
                _group_schema(defaults, HEALTH_FIELDS),
                {"collapsed": True},
            ),
            vol.Required("automatic_testing"): section(
                _group_schema(defaults, TESTING_FIELDS),
                {"collapsed": True},
            ),
        }
    )
    return vol.Schema(fields)


def _flatten_sections(user_input: dict[str, Any]) -> dict[str, Any]:
    """Flatten section dictionaries into the existing option-key layout."""
    values: dict[str, Any] = {}
    for key, value in user_input.items():
        if isinstance(value, dict):
            values.update(value)
        else:
            values[key] = value
    return values


def _discover_ina219_devices() -> tuple[dict[str, int], bool]:
    """Return detected INA219-compatible addresses and whether buses exist."""
    found: dict[str, int] = {}
    opened_bus = False
    for bus_number in I2C_BUSES:
        try:
            with SMBus(bus_number) as bus:
                opened_bus = True
                for address in INA219_ADDRESSES:
                    try:
                        data = bus.read_i2c_block_data(address, 0x00, 2)
                    except OSError:
                        continue
                    if len(data) == 2:
                        found.setdefault(hex(address), bus_number)
        except (FileNotFoundError, OSError):
            continue
    return found, opened_bus


class WaveshareUPSConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create a Waveshare UPS configuration entry."""

    VERSION = 1

    def __init__(self) -> None:
        self._detected: dict[str, int] | None = None
        self._values: dict[str, Any] = {}

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return WaveshareUPSOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Discover and configure a UPS."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if self._detected is None:
            self._detected, opened_bus = await self.hass.async_add_executor_job(
                _discover_ina219_devices
            )
            if not opened_bus:
                return self.async_abort(reason="i2c_unavailable")
            if not self._detected:
                return self.async_abort(reason="ups_not_detected")

        errors: dict[str, str] = {}
        if user_input is not None:
            values = _flatten_sections(user_input)
            if CONF_BATTERY_REPLACEMENT_DATE not in values:
                self._values.pop(CONF_BATTERY_REPLACEMENT_DATE, None)
            self._values.update(values)
            if not _valid_levels(self._values):
                errors["base"] = "invalid_battery_levels"
            elif not _valid_address(self._values):
                errors["base"] = "invalid_hat_address"
            elif not _valid_relay(self._values):
                errors["base"] = "invalid_relay_gpio"
            elif not _valid_self_test(self._values):
                errors["base"] = "invalid_self_test"
            else:
                title = self._values.pop(CONF_NAME)
                address = self._values[CONF_HAT_ADDRESS]
                self._values[CONF_HAT_BUS] = self._detected[address]
                await self.async_set_unique_id(
                    f"{self._values[CONF_HAT_BUS]}::{address}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=title,
                    data={},
                    options=self._values,
                )
        result = self.async_show_form(
            step_id="user",
            data_schema=_section_schema(
                self._values,
                include_setup=True,
                detected=self._detected,
            ),
            errors=errors,
        )
        result["translation_domain"] = DOMAIN
        return result


class WaveshareUPSOptionsFlow(OptionsFlow):
    """Edit settings for an existing Waveshare UPS."""

    def __init__(self, entry: ConfigEntry) -> None:
        self._values = dict(entry.options)
        self._values.pop("min_charging", None)
        legacy_enabled = self._values.pop("relay_enabled", None)
        legacy_mode = self._values.pop("calibration_mode", None)
        if CONF_AUTOMATIC_TESTING not in self._values:
            self._values[CONF_AUTOMATIC_TESTING] = bool(
                legacy_enabled or legacy_mode == "automatic"
            )

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Show configuration actions."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["configure", "reset_configuration"],
        )

    async def async_step_configure(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Show and save integration options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            values = _flatten_sections(user_input)
            if CONF_BATTERY_REPLACEMENT_DATE not in values:
                self._values.pop(CONF_BATTERY_REPLACEMENT_DATE, None)
            self._values.update(values)
            if not _valid_levels(self._values):
                errors["base"] = "invalid_battery_levels"
            elif not _valid_address(self._values):
                errors["base"] = "invalid_hat_address"
            elif not _valid_relay(self._values):
                errors["base"] = "invalid_relay_gpio"
            elif not _valid_self_test(self._values):
                errors["base"] = "invalid_self_test"
            else:
                return self.async_create_entry(title="", data=self._values)

        result = self.async_show_form(
            step_id="configure",
            data_schema=_section_schema(self._values),
            errors=errors,
        )
        result["translation_domain"] = DOMAIN
        return result

    async def async_step_reset_configuration(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Confirm restoring installation defaults."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data=reset_options(self._values),
            )
        result = self.async_show_form(
            step_id="reset_configuration",
            data_schema=vol.Schema({}),
        )
        result["translation_domain"] = DOMAIN
        return result
