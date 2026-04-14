"""Tests for scripts/category_defaults.json (Story 8.2)."""

import json
import pathlib

import pytest

from scripts.import_assets_csv import get_category_defaults

SCRIPTS_DIR = pathlib.Path(__file__).parent.parent / "scripts"
DEFAULTS_FILE = SCRIPTS_DIR / "category_defaults.json"

REQUIRED_FIELDS = ("useful_life_months", "salvage_value", "depreciation_method", "is_depreciable")
EXPECTED_CATEGORIES = {
    "EDIFICACIONES",
    "MAQUINARIA Y EQUIPOS",
    "MUEBLES Y ENSERES",
    "TERRENOS",
    "Equipos de Cómputo",
    "Vehículos",
}
VALID_METHODS = ("lineal", "none")

# Pinned per epic spec (Story 8.2 AC) — detects silent regressions on specific values.
EXPECTED_VALUES = {
    "EDIFICACIONES":        {"useful_life_months": 240, "salvage_value": "0", "depreciation_method": "lineal", "is_depreciable": True},
    "MAQUINARIA Y EQUIPOS": {"useful_life_months": 120, "salvage_value": "0", "depreciation_method": "lineal", "is_depreciable": True},
    "MUEBLES Y ENSERES":    {"useful_life_months": 120, "salvage_value": "0", "depreciation_method": "lineal", "is_depreciable": True},
    "TERRENOS":             {"useful_life_months": 0,   "salvage_value": "0", "depreciation_method": "none",   "is_depreciable": False},
    "Equipos de Cómputo":   {"useful_life_months": 60,  "salvage_value": "0", "depreciation_method": "lineal", "is_depreciable": True},
    "Vehículos":            {"useful_life_months": 60,  "salvage_value": "0", "depreciation_method": "lineal", "is_depreciable": True},
}


@pytest.fixture(scope="module")
def category_defaults():
    with open(DEFAULTS_FILE, encoding="utf-8") as f:
        return json.load(f)


# --- Group A: File structure validation ---


def test_json_loads_successfully():
    with open(DEFAULTS_FILE, encoding="utf-8") as f:
        json.load(f)


def test_all_six_categories_present(category_defaults):
    assert set(category_defaults.keys()) == EXPECTED_CATEGORIES


def test_each_category_has_all_required_fields(category_defaults):
    for cat, values in category_defaults.items():
        for field in REQUIRED_FIELDS:
            assert field in values, f"Category '{cat}' missing field '{field}'"


# --- Group B: Value correctness ---


def test_terrenos_values(category_defaults):
    terrenos = category_defaults["TERRENOS"]
    assert terrenos["useful_life_months"] == 0
    assert terrenos["salvage_value"] == "0"
    assert terrenos["depreciation_method"] == "none"
    assert terrenos["is_depreciable"] is False


def test_salvage_value_is_string_not_int(category_defaults):
    for cat, values in category_defaults.items():
        assert isinstance(values["salvage_value"], str), (
            f"Category '{cat}' salvage_value must be str (D3 compliance)"
        )


def test_depreciable_categories_have_positive_useful_life(category_defaults):
    for cat, values in category_defaults.items():
        if values["is_depreciable"] is True:
            assert values["useful_life_months"] > 0, (
                f"Depreciable category '{cat}' must have useful_life_months > 0"
            )


def test_non_depreciable_categories_have_zero_useful_life(category_defaults):
    for cat, values in category_defaults.items():
        if values["is_depreciable"] is False:
            assert values["useful_life_months"] == 0, (
                f"Non-depreciable category '{cat}' must have useful_life_months == 0"
            )


def test_valid_depreciation_methods(category_defaults):
    for cat, values in category_defaults.items():
        assert values["depreciation_method"] in VALID_METHODS, (
            f"Category '{cat}' has invalid depreciation_method"
        )


@pytest.mark.parametrize("category,expected", list(EXPECTED_VALUES.items()))
def test_category_has_exact_expected_values(category_defaults, category, expected):
    actual = category_defaults[category]
    for field, expected_value in expected.items():
        assert actual[field] == expected_value, (
            f"Category '{category}' field '{field}': "
            f"expected {expected_value!r}, got {actual[field]!r}"
        )


# --- Group C: Lookup helper behavior (preview for Story 8.3) ---


def test_lookup_known_category_returns_defaults(category_defaults):
    result = get_category_defaults("EDIFICACIONES", category_defaults)
    assert result == category_defaults["EDIFICACIONES"]
    assert result["useful_life_months"] == 240


def test_lookup_unknown_category_raises_value_error(category_defaults):
    with pytest.raises(ValueError, match="MOBILIARIO"):
        get_category_defaults("MOBILIARIO", category_defaults)
