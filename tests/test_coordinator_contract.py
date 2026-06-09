"""Static checks for coordinator constants without importing Home Assistant."""

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1] / "custom_components" / "waveshare_ups"


def test_all_referenced_default_constants_are_imported() -> None:
    """Catch missing constant imports that would fail integration setup."""
    tree = ast.parse((ROOT / "coordinator.py").read_text(encoding="utf-8"))
    referenced = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id.startswith("DEFAULT_")
    }
    imported = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "const"
        for alias in node.names
    }

    assert referenced <= imported


def test_self_test_confirms_percentage_before_displaying_it() -> None:
    """Expose sustained load sag without displaying one noisy sample."""
    source = (ROOT / "coordinator.py").read_text(encoding="utf-8")

    assert "SELF_TEST_PERCENTAGE_CONFIRMATION_SECONDS = 5" in source
    assert "self._self_test_percentage_candidate_since" in source
    assert "data.measured_battery_percentage" in source
