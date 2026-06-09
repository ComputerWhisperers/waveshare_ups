"""Static contract checks for the grouped configuration form."""

import ast
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parents[1] / "custom_components" / "waveshare_ups"


def test_options_flow_has_configuration_and_reset_actions() -> None:
    """Keep editing and resetting accessible from Configure."""
    tree = ast.parse((ROOT / "config_flow.py").read_text(encoding="utf-8"))
    options_flow = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WaveshareUPSOptionsFlow"
    )
    step_methods = {
        node.name
        for node in options_flow.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name.startswith("async_step_")
    }

    assert step_methods == {
        "async_step_init",
        "async_step_configure",
        "async_step_reset_configuration",
    }


def test_section_values_flatten_to_existing_option_keys() -> None:
    """Section grouping must not change persisted option keys."""
    tree = ast.parse((ROOT / "config_flow.py").read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_flatten_sections"
    )
    module = ast.Module(body=[function], type_ignores=[])
    namespace: dict[str, object] = {"Any": Any}
    exec(compile(module, "config_flow.py", "exec"), namespace)

    flatten = namespace["_flatten_sections"]
    assert callable(flatten)
    assert flatten(
        {
            "name": "UPS",
            "ups_runtime": {"battery_capacity": 3200},
            "automatic_testing": {
                "automatic_testing": True,
                "relay_gpio": 17,
            },
        }
    ) == {
        "name": "UPS",
        "battery_capacity": 3200,
        "automatic_testing": True,
        "relay_gpio": 17,
    }


def test_all_section_and_field_labels_are_human_readable() -> None:
    """Require source strings for sections and their settings."""
    strings = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
    expected = {
        "ups_runtime": {
            "name": "UPS",
            "fields": {
                "hat_address": "Board Address",
                "hat_type": "Board Type",
                "battery_capacity": "Battery Capacity",
                "full_charge_voltage": "Full Charge Voltage",
            },
        },
        "shutdown": {"name": "Shutdown", "fields": {}},
        "battery_health": {"name": "Battery Health", "fields": {}},
        "automatic_testing": {
            "name": "Calibration and Self-Test",
            "fields": {
                "automatic_testing": ("Enable Automatic Calibration and Self-Test"),
                "relay_gpio": "Relay GPIO Pin (BCM)",
                "relay_active_low": "Relay Triggered by LOW",
            },
        },
    }

    for flow in ("config", "options"):
        step = "user" if flow == "config" else "configure"
        sections = strings[flow]["step"][step]["sections"]
        for key, expected_section in expected.items():
            assert sections[key]["name"] == expected_section["name"]
            for field, label in expected_section["fields"].items():
                assert sections[key]["data"][field] == label


def test_configuration_form_title_and_translation_domain() -> None:
    """Keep the configuration title and explicit translation binding intact."""
    strings = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
    assert strings["config"]["step"]["user"]["title"] == "UPS Configuration"
    assert strings["options"]["step"]["init"]["title"] == "UPS Configuration"
    assert strings["options"]["step"]["configure"]["title"] == "UPS Configuration"

    source = (ROOT / "config_flow.py").read_text(encoding="utf-8")
    assert source.count('result["translation_domain"] = DOMAIN') == 3


def test_board_address_is_available_in_setup_and_options() -> None:
    """Keep the board address in the UPS section for every form."""
    source = (ROOT / "config_flow.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    core_fields = next(
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "CORE_FIELDS"
            for target in node.targets
        )
    )
    names = {
        element.id
        for element in core_fields.value.elts
        if isinstance(element, ast.Name)
    }

    assert "CONF_HAT_ADDRESS" in names
    assert "CONF_FULL_CHARGE_VOLTAGE" in names


def test_output_supports_high_voltage_state() -> None:
    """Expose the sustained overvoltage state through the Output entity."""
    sensor_source = (ROOT / "sensor.py").read_text(encoding="utf-8")
    coordinator_source = (ROOT / "coordinator.py").read_text(encoding="utf-8")
    strings = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))

    assert '"high_voltage"' in sensor_source
    assert "HIGH_VOLTAGE_CONFIRMATION_SECONDS = 15" in coordinator_source
    assert (
        strings["entity"]["sensor"]["output"]["state"]["high_voltage"] == "High Voltage"
    )


def test_setup_has_distinct_i2c_failure_messages() -> None:
    """Explain whether the bus or the UPS board is unavailable."""
    strings = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
    aborts = strings["config"]["abort"]
    assert "i2c_unavailable" in aborts
    assert "ups_not_detected" in aborts
    assert aborts["i2c_unavailable"] != aborts["ups_not_detected"]

    source = (ROOT / "config_flow.py").read_text(encoding="utf-8")
    assert 'reason="i2c_unavailable"' in source
    assert 'reason="ups_not_detected"' in source


def test_reset_to_defaults_is_a_configure_action() -> None:
    """Expose reset in Configure with a confirmation button."""
    strings = json.loads((ROOT / "strings.json").read_text(encoding="utf-8"))
    options_steps = strings["options"]["step"]
    assert options_steps["init"]["menu_options"]["reset_configuration"] == (
        "Reset Configuration to Defaults"
    )
    assert options_steps["reset_configuration"]["submit"] == "Reset Configuration"

    config_source = (ROOT / "config_flow.py").read_text(encoding="utf-8")
    button_source = (ROOT / "button.py").read_text(encoding="utf-8")
    options_source = (ROOT / "options.py").read_text(encoding="utf-8")
    assert "async_show_menu" in config_source
    assert "async_step_reset_configuration" in config_source
    assert "WaveshareResetConfigurationButton" not in button_source
    for field in (
        "CONF_BATTERY_REPLACEMENT_DATE",
        "CONF_HAT_ADDRESS",
        "CONF_HAT_BUS",
        "CONF_RUNTIME_CALIBRATION",
    ):
        assert (
            field
            in options_source.split("RESET_PRESERVED_FIELDS", 1)[1].split("}", 1)[0]
        )


def test_internal_wear_counters_are_not_entities() -> None:
    """Track maintenance counters internally without exposing sensors."""
    sensor_source = (ROOT / "sensor.py").read_text(encoding="utf-8")
    diagnostics_source = (ROOT / "diagnostics.py").read_text(encoding="utf-8")
    init_source = (ROOT / "__init__.py").read_text(encoding="utf-8")
    for key in (
        "equivalent_cycles",
        "deep_discharge_count",
        "high_voltage_hours",
    ):
        assert f'key="{key}"' not in sensor_source
        assert key in (ROOT / "health.py").read_text(encoding="utf-8")
        assert f'"{key}"' in init_source
    assert "battery_health_diagnostics" in diagnostics_source
    assert "entity_registry.async_remove" in init_source
