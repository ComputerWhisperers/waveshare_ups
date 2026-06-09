"""Tests for resetting configuration options."""

import ast
from pathlib import Path
from typing import Any

OPTIONS_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "waveshare_ups"
    / "options.py"
)


def test_reset_options_restores_defaults_and_preserves_history() -> None:
    tree = ast.parse(OPTIONS_PATH.read_text(encoding="utf-8"))
    imported_names = next(
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "const"
    ).names
    namespace: dict[str, Any] = {"Any": Any}
    for imported in imported_names:
        name = imported.name
        namespace[name] = (
            name.removeprefix("CONF_").lower()
            if name.startswith("CONF_")
            else name
        )
    executable = ast.Module(
        body=[
            node
            for node in tree.body
            if isinstance(node, (ast.Assign, ast.FunctionDef))
        ],
        type_ignores=[],
    )
    exec(compile(executable, str(OPTIONS_PATH), "exec"), namespace)

    current = {
        "hat_address": "0x41",
        "hat_bus": 1,
        "hat_type": "b",
        "battery_capacity": 9000,
        "battery_replacement_date": "2026-06-05",
        "runtime_calibration": 185,
        "automatic_testing": True,
    }

    reset = namespace["reset_options"](current)

    assert reset["hat_address"] == "0x41"
    assert reset["hat_bus"] == 1
    assert reset["battery_replacement_date"] == "2026-06-05"
    assert reset["runtime_calibration"] == 185
    assert reset["hat_type"] == "DEFAULT_HAT_TYPE"
    assert reset["battery_capacity"] == "DEFAULT_BATTERY_CAPACITY"
    assert reset["automatic_testing"] == "DEFAULT_AUTOMATIC_TESTING"
