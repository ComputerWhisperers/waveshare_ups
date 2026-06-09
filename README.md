[![Latest Release][badge_release]][release_link]
[![HACS Custom][badge_hacs]][hacs_link]
[![License: MIT][badge_license]][license_link]

# Waveshare 3S UPS for Raspberry Pi

A Home Assistant custom integration for monitoring Waveshare UPS hardware
connected to a Raspberry Pi over I2C. Supported models include the Waveshare
UPS HAT A, B, and D, along with the Waveshare UPS Module 3S.

This project was originally inspired by
[rpi_waveshare_ups][original_project] by [uvjim][original_author]. The current
implementation was independently written from the INA219 datasheet, Waveshare
hardware documentation, and Home Assistant developer documentation.

## Purpose

This project was created to make UPS information available in Home Assistant
and to provide useful states for automations. One example is safely shutting
down a Raspberry Pi when an outage continues long enough for the battery to
reach a critical level.

Battery percentage and runtime are estimates derived from the measurements
reported by the UPS board. They should not be treated as laboratory-grade
measurements or as a replacement for the protections built into the UPS.
Always test shutdown automations before relying on them.

## Requirements

- A supported Waveshare UPS connected to the Raspberry Pi
- I2C enabled on the Raspberry Pi
- Home Assistant with access to the Raspberry Pi I2C bus
- [HACS](https://hacs.xyz/) for the recommended installation method

Instructions for enabling I2C depend on the Home Assistant installation:

- [Home Assistant OS I2C instructions][ha_i2c]
- [Raspberry Pi configuration documentation][rpi_i2c]

## Installation

This integration is not currently included in the default HACS repository
list. Add it as a custom repository:

1. Open HACS in Home Assistant.
2. Open the menu and select **Custom repositories**.
3. Enter `https://github.com/ComputerWhisperers/waveshare_ups`.
4. Select **Integration** as the category.
5. Download the integration and restart Home Assistant.
6. Go to **Settings > Devices & services > Add Integration**.
7. Search for **Waveshare 3S UPS for Raspberry Pi**.

You can also open the repository in HACS with this button:

[![Open this repository in HACS][hacs_badge]][hacs_link]

## Setup

During setup, the integration scans the available I2C buses for the UPS. The
settings are divided into four pages so related options stay together:

- **UPS and runtime**: Name, I2C address, board version, battery capacity,
  battery-power current threshold, full-charge voltage, estimated runtime
  load, internal runtime calibration, and update interval.
- **Shutdown thresholds**: Warning battery level and Shutdown battery level.
- **Battery health**: Replacement date, age and cycle limits, deep-discharge
  limits, high-voltage exposure limits, and runtime-degradation threshold.
- **Calibration, self-test, and GPIO**: Automatic testing toggle, self-test
  limits, relay GPIO and polarity, and safety timeouts.

The defaults are intended for the Waveshare 3S board with 3200 mAh batteries.
The default battery-power threshold is -100 mA.

The current threshold is the single reference used for Source, Battery State,
runtime behavior, utility-mode percentage stabilization, and Output status.

## Entities

Entity IDs use the name entered during setup. For example, a setup name of
`MyUPS` creates entities beginning with `sensor.myups_` and
`binary_sensor.myups_`.

### Binary Sensors

| Name | Example entity ID | Description |
|---|---|---|
| Status | `binary_sensor.myups_status` | Online when the integration can communicate with the UPS board. |
| Battery State | `binary_sensor.myups_battery_state` | Charging when current is at or above the configured battery-power threshold; otherwise discharging. |
| Initiate Shutdown | `binary_sensor.myups_initiate_shutdown` | On when Output is Critical, Output Source is Battery, and neither calibration nor self-test is active. |
| Battery Maintenance | `binary_sensor.myups_battery_maintenance` | On when a configured gradual-wear limit is reached. It turns off while Battery Fault is on. |
| Battery Fault | `binary_sensor.myups_battery_fault` | Latched on when a self-test detects a severe percentage or voltage drop. |

### Sensors

| Name | Example entity ID | Description |
|---|---|---|
| Battery | `sensor.myups_battery` | Estimated remaining battery percentage. |
| Runtime | `sensor.myups_runtime` | Estimated remaining runtime in hours. |
| Calibration Status | `sensor.myups_calibration_status` | Idle, Waiting for Battery, or Running. It returns to Idle when a test ends. |
| Calibration Elapsed | `sensor.myups_calibration_elapsed` | Battery runtime measured during the active or most recent test. |
| Last Calibration Date | `sensor.myups_last_runtime_calibration` | Date when the most recent successful calibration completed. |
| Last Calibration Status | `sensor.myups_last_calibration_status` | Completed or Cancelled result from the latest calibration. |
| Last Battery Change | `sensor.myups_last_battery_change` | Persisted date when the batteries were last replaced. |
| Battery Age | `sensor.myups_battery_age` | Number of days since the stored battery replacement date. |
| Self-Test Status | `sensor.myups_self_test_status` | Idle, Waiting for Battery, or Running. Disabled when automatic testing is off. |
| Last Self-Test Status | `sensor.myups_last_self_test_status` | Passed, Failed, Cancelled, or Interrupted. Disabled when automatic testing is off. |
| Last Self-Test Date | `sensor.myups_last_self_test_date` | Date of the latest self-test result. Disabled when automatic testing is off. |
| Output Source | `sensor.myups_source` | Reports Utility or Battery. The existing entity-ID suffix remains `source`. |
| Output | `sensor.myups_output` | Reports Normal, Warning, Critical, or High Voltage for automations. |
| Current | `sensor.myups_current` | Current reported by the UPS in mA. |
| Battery Voltage | `sensor.myups_battery_voltage` | Voltage measured on the load side of the current-sense circuit. |
| Supply Voltage | `sensor.myups_supply_voltage` | Input supply voltage while utility power is present; reports 0 V while running on battery. |
| Current Sense Voltage | `sensor.myups_current_sense_voltage` | Small voltage drop used by the UPS to determine current. |
| Power | `sensor.myups_power` | Power reported by the UPS in watts. |

Equivalent battery cycles, deep-discharge count, and high-voltage time are
tracked internally for Battery Maintenance but are not exposed as entities.
They remain available in the integration diagnostics for troubleshooting.

### Buttons

| Name | Example entity ID | Description |
|---|---|---|
| Battery Replaced | `button.myups_battery_replaced` | Stores the current date as the last battery replacement date. |
| Start Runtime Calibration | `button.myups_start_runtime_calibration` | Arms a full-charge battery runtime test. |
| Cancel Runtime Calibration | `button.myups_cancel_runtime_calibration` | Cancels an active or waiting calibration test. |
| Start Self-Test | `button.myups_start_self_test` | Starts a short relay-controlled battery test. Disabled when automatic testing is off. |
| Cancel Self-Test | `button.myups_cancel_self_test` | Cancels a self-test and restores utility. Disabled when automatic testing is off. |

## Resetting Configuration

Open **Configure**, select **Reset Configuration to Defaults**, and confirm the
reset. The board address, battery replacement date, learned runtime calibration,
and persistent battery history are preserved.

## Battery and Runtime Estimates

Battery percentage is estimated from the voltage characteristics for the
selected UPS model. The 3S module uses a multi-point discharge curve and a
configurable Full Charge Voltage, which defaults to 12.49 V. The upper curve
scales smoothly to the configured value instead of merely moving the 100%
cutoff, preserving gradual readings through 94%, 96%, 98%, and 99%.

While utility power is present, the displayed percentage may increase as the
batteries charge, but temporary voltage sag from CPU activity will not lower
it. When the UPS switches to battery power, the percentage follows the
measured voltage curve again. Downward changes are rate-limited to no more
than one percentage point every two minutes so the immediate voltage sag
under load is not mistaken for an equally immediate loss of capacity.

Runtime is calculated from the configured battery capacity, estimated battery
percentage, and expected discharge current. The configured runtime load is
used as a minimum because some UPS boards may report less current than the
Raspberry Pi is actually consuming. Runtime is smoothed and displayed in
six-minute increments to reduce rapid fluctuations. Runtime calibration is
applied after this calculation. For example, if an estimate of three hours
consistently lasts only 2.4 hours, set calibration to 80%.

## Runtime Calibration

The integration can measure actual battery runtime and update the calibration
percentage automatically:

1. Leave utility power connected and charge the Battery sensor to 100%.
2. Press **Start Runtime Calibration**. Calibration Status changes to
   Waiting for Battery.
3. Disconnect utility power from the UPS. When Output Source changes to Battery,
   Calibration Status changes to Running and the timer starts.
4. Keep Home Assistant and the Raspberry Pi under their normal operating load.
   Leave the UPS on battery until Output reaches Critical. The test completes
   automatically and Calibration Status returns to Idle.
5. Reconnect utility power.

At completion, the integration compares the measured battery runtime with the
uncalibrated expected runtime from 100% to the configured Critical level. It
then saves the resulting Runtime Calibration percentage and applies it to
future runtime estimates.

The active test, start time, and latest result are stored in Home Assistant's
persistent storage. A manual calibration therefore resumes after a Home
Assistant restart. If utility power returns before Output reaches Critical,
the test is marked Cancelled and no new calibration percentage is saved. The
Cancel Runtime Calibration button can also stop a test manually.

The Raspberry Pi may shut down before Home Assistant records Critical if a
shutdown automation reacts immediately to Output. During the first calibration
test, allow enough time for the integration to record the Critical state
before shutdown.

When **Enable Automatic Calibration and Self-Test** is on, steps 3 and 5 are
performed by the configured GPIO relay. When it is off, calibration remains
manual and the relay is not controlled.

## Automatic Testing and Utility Relay (Beta)

The beta GPIO option can make runtime calibration self-contained on Raspberry
Pi 4 and Raspberry Pi 5 systems running Home Assistant OS. It uses the
official `gpiod` Python bindings and discovers the Raspberry Pi GPIO
controller by its `pinctrl` label, so it does not depend on a fixed
`/dev/gpiochip` number.

Automatic testing defaults to off. Configure:

- **Enable Automatic Calibration and Self-Test**: Enables GPIO relay control
  and the self-test entities.
- **Relay GPIO Number (BCM)**: GPIO number, not physical header pin number.
  GPIO17, physical pin 11, is the default.
- **Relay activates on LOW**: Off by default, meaning a HIGH GPIO signal
  activates the relay. Turn it on only for a relay that activates from LOW.
- **Switch-to-battery timeout**: Restores utility if Source does not become
  Battery after the relay opens.
- **Maximum calibration duration**: Restores utility if Critical is
  not reached within the configured number of hours.

Use a relay module that accepts the Raspberry Pi's 3.3 V GPIO signal. The
relay contacts must be rated for the UPS input voltage and current. Wire the
UPS's positive DC supply through the relay's normally closed contacts so
utility remains connected when the relay is not energized. Never connect
13 V, relay-coil current, or mains voltage directly to a Raspberry Pi GPIO.

GPIO2 and GPIO3 cannot be selected because the UPS uses them for I2C. Confirm
that the selected GPIO is not used by a fan, HAT, or another integration.

With automatic testing off, Start and Cancel Runtime Calibration never operate
GPIO; utility must be disconnected and restored by hand. With it on, Start energizes the
relay and verifies that Source changes to Battery, while Cancel immediately
restores utility. At Critical, timeout, UPS communication failure, integration
unload, or a normal Home Assistant restart, the integration also commands the
relay back to utility-connected. An automatic test interrupted by a restart
is cancelled once utility is detected. Normally closed contacts provide the
additional hardware fallback when GPIO control is lost.

The **Start Self-Test** button briefly removes utility power. After the
configured settling time, the integration fails the test if battery percentage
falls to the configured failure level or voltage reaches the emergency level.
A failure restores utility and latches Battery Fault. A healthy test restores
utility after the configured duration and records Passed. A restart or loss of
UPS communication records Interrupted rather than assuming a battery fault.

This is beta functionality because GPIO availability can vary with Home
Assistant OS and Raspberry Pi hardware revisions. Test relay polarity and
utility restoration before relying on unattended testing.

## Battery Maintenance

The replacement date is stored in the Home Assistant config entry. Usage
counters, battery fault, self-test history, and calibration state are stored
in Home Assistant persistent storage. These values survive restarts and
integration updates.

Battery Maintenance evaluates battery age, equivalent cycles, deep
discharges, high-voltage exposure, and degradation from the first learned
runtime. Battery Fault represents a severe self-test failure and suppresses
Battery Maintenance so only the more urgent condition is shown.

Pressing **Battery Replaced** records the current date and resets both warnings,
all battery-use counters, self-test history, and learned runtime calibration.

Last Battery Change and Battery Age remain available even if communication
with the UPS board is temporarily lost.

Percentage smoothing affects only the displayed Battery and Runtime estimates.
Output continues to use the immediate measured percentage and model-specific
low-voltage limit so Warning and Critical automations are not delayed.

While utility power is present, Output changes to High Voltage only after
Battery Voltage remains strictly above the configured High Voltage Threshold
for 15 seconds. A reading exactly equal to the threshold does not activate the
state. A small recovery margin prevents repeated state changes near the limit.
High Voltage does not turn on Initiate Shutdown.

## Configurable Options

After installation, open the integration and select **Configure**. Options use
the same four grouped pages as initial setup: UPS and runtime, shutdown
thresholds, battery health, and calibration/self-test with GPIO.

The shutdown battery level must be lower than the warning battery level.

## License

This project is licensed under the [MIT License](LICENSE).

[badge_release]: https://img.shields.io/github/v/release/ComputerWhisperers/waveshare_ups?display_name=release&style=for-the-badge&cacheSeconds=3600
[badge_hacs]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[badge_license]: https://img.shields.io/github/license/ComputerWhisperers/waveshare_ups?style=for-the-badge
[license_link]: LICENSE
[release_link]: https://github.com/ComputerWhisperers/waveshare_ups/releases/latest
[original_project]: https://github.com/uvjim/rpi_waveshare_ups
[original_author]: https://github.com/uvjim
[ha_i2c]: https://www.home-assistant.io/common-tasks/os/#enable-i2c
[rpi_i2c]: https://www.raspberrypi.com/documentation/computers/configuration.html
[hacs_badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[hacs_link]: https://my.home-assistant.io/redirect/hacs_repository/?owner=ComputerWhisperers&repository=waveshare_ups&category=Integration
