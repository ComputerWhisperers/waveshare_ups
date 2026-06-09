"""Sensor entities for the Waveshare UPS."""

from dataclasses import dataclass
from datetime import date

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .calibration import CALIBRATION_RESULTS, CALIBRATION_STATUSES
from .const import DOMAIN
from .coordinator import WaveshareUPSCoordinator
from .entity import WaveshareUPSEntity
from .health import SELF_TEST_RESULTS, SELF_TEST_STATUSES


@dataclass(frozen=True, kw_only=True)
class WaveshareSensorDescription(SensorEntityDescription):
    """Sensor metadata with a stable entity-ID suffix."""

    object_id_suffix: str


SENSORS = (
    WaveshareSensorDescription(
        key="battery_percentage",
        name="Battery",
        translation_key="battery_percentage",
        object_id_suffix="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WaveshareSensorDescription(
        key="runtime",
        name="Runtime",
        translation_key="runtime",
        object_id_suffix="runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    WaveshareSensorDescription(
        key="calibration_status",
        name="Calibration Status",
        translation_key="calibration_status",
        object_id_suffix="calibration_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(CALIBRATION_STATUSES),
    ),
    WaveshareSensorDescription(
        key="calibration_elapsed",
        name="Calibration Elapsed",
        translation_key="calibration_elapsed",
        object_id_suffix="calibration_elapsed",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    WaveshareSensorDescription(
        key="last_runtime_calibration",
        name="Last Runtime Calibration",
        translation_key="last_runtime_calibration",
        object_id_suffix="last_runtime_calibration",
        device_class=SensorDeviceClass.DATE,
    ),
    WaveshareSensorDescription(
        key="last_calibration_status",
        name="Last Calibration Status",
        translation_key="last_calibration_status",
        object_id_suffix="last_calibration_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(CALIBRATION_RESULTS),
    ),
    WaveshareSensorDescription(
        key="last_battery_change",
        name="Last Battery Change",
        translation_key="last_battery_change",
        object_id_suffix="last_battery_change",
        device_class=SensorDeviceClass.DATE,
    ),
    WaveshareSensorDescription(
        key="battery_age",
        name="Battery Age",
        translation_key="battery_age",
        object_id_suffix="battery_age",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WaveshareSensorDescription(
        key="ups_state",
        name="Output Source",
        translation_key="ups_state",
        object_id_suffix="source",
        device_class=SensorDeviceClass.ENUM,
        options=["utility", "battery"],
    ),
    WaveshareSensorDescription(
        key="self_test_status",
        name="Self-Test Status",
        translation_key="self_test_status",
        object_id_suffix="self_test_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(SELF_TEST_STATUSES),
    ),
    WaveshareSensorDescription(
        key="last_self_test_status",
        name="Last Self-Test Status",
        translation_key="last_self_test_status",
        object_id_suffix="last_self_test_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(SELF_TEST_RESULTS),
    ),
    WaveshareSensorDescription(
        key="last_self_test_date",
        name="Last Self-Test Date",
        translation_key="last_self_test_date",
        object_id_suffix="last_self_test_date",
        device_class=SensorDeviceClass.DATE,
    ),
    WaveshareSensorDescription(
        key="output",
        name="Output",
        translation_key="output",
        object_id_suffix="output",
        device_class=SensorDeviceClass.ENUM,
        options=["normal", "warning", "critical", "high_voltage"],
    ),
    WaveshareSensorDescription(
        key="current",
        name="Current",
        translation_key="current",
        object_id_suffix="current",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.MILLIAMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    WaveshareSensorDescription(
        key="load_voltage",
        name="Battery Voltage",
        translation_key="load_voltage",
        object_id_suffix="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    WaveshareSensorDescription(
        key="supply_voltage",
        name="Supply Voltage",
        translation_key="supply_voltage",
        object_id_suffix="supply_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
    WaveshareSensorDescription(
        key="current_sense_voltage",
        name="Current Sense Voltage",
        translation_key="current_sense_voltage",
        object_id_suffix="current_sense_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=3,
    ),
    WaveshareSensorDescription(
        key="power",
        name="Power",
        translation_key="power",
        object_id_suffix="power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add Waveshare UPS sensors."""
    coordinator: WaveshareUPSCoordinator = hass.data[DOMAIN][entry.entry_id]
    descriptions = (
        SENSORS
        if coordinator.automatic_testing
        else tuple(
            description
            for description in SENSORS
            if description.key
            not in {
                "self_test_status",
                "last_self_test_status",
                "last_self_test_date",
            }
        )
    )
    async_add_entities(
        WaveshareUPSSensor(coordinator, entry, description)
        for description in descriptions
    )


class WaveshareUPSSensor(WaveshareUPSEntity, SensorEntity):
    """Expose one value from the coordinator snapshot."""

    def __init__(
        self,
        coordinator: WaveshareUPSCoordinator,
        entry: ConfigEntry,
        description: WaveshareSensorDescription,
    ) -> None:
        WaveshareUPSEntity.__init__(
            self,
            coordinator,
            entry,
            "sensor",
            description.key,
            description.object_id_suffix,
        )
        self.entity_description = description

    @property
    def native_value(self) -> StateType | date:
        """Return the latest calculated or measured value."""
        return getattr(self.coordinator.data, self.entity_description.key)

    @property
    def available(self) -> bool:
        """Return whether the UPS answered the latest poll."""
        metadata_sensor = self.entity_description.key in {
            "last_battery_change",
            "battery_age",
            "calibration_status",
            "calibration_elapsed",
            "last_runtime_calibration",
            "last_calibration_status",
            "self_test_status",
            "last_self_test_status",
            "last_self_test_date",
        }
        return self.coordinator.last_update_success and (
            metadata_sensor or self.coordinator.data.online
        )
