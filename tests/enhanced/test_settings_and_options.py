"""Tests for enhanced setting compatibility and the options flow."""

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.foxess_em.config_flow import EnhancedOptionsFlowHandler
from custom_components.foxess_em.const import (
    ENHANCED_ENABLED,
    ENHANCED_HISTORY_DAYS,
    ENHANCED_MODE,
)
from custom_components.foxess_em.enhanced.settings import normalize_settings


@pytest.mark.parametrize("value", ["true", "TRUE", " yes ", "1", "on"])
def test_normalize_settings_accepts_true_boolean_strings(value):
    assert normalize_settings({ENHANCED_ENABLED: value})[ENHANCED_ENABLED] is True


@pytest.mark.parametrize("value", ["false", "no", "0", "off", "garbage"])
def test_normalize_settings_rejects_false_boolean_strings(value):
    assert normalize_settings({ENHANCED_ENABLED: value})[ENHANCED_ENABLED] is False


def test_normalize_settings_replaces_bad_mode_and_history():
    result = normalize_settings(
        {ENHANCED_MODE: "invalid", ENHANCED_HISTORY_DAYS: "not-a-number"}
    )
    assert result[ENHANCED_MODE] == "p50"
    assert result[ENHANCED_HISTORY_DAYS] == 14


def test_options_schema_uses_options_then_data_defaults():
    entry = SimpleNamespace(
        data={ENHANCED_ENABLED: False, ENHANCED_MODE: "p10", ENHANCED_HISTORY_DAYS: 8},
        options={ENHANCED_ENABLED: True, ENHANCED_MODE: "p90"},
    )
    result = asyncio.run(EnhancedOptionsFlowHandler(entry).async_step_init())
    schema = result["data_schema"]
    assert schema({}) == {
        ENHANCED_ENABLED: True,
        ENHANCED_MODE: "p90",
        ENHANCED_HISTORY_DAYS: 8,
    }


def test_options_submission_contains_only_enhanced_keys():
    entry = SimpleNamespace(data={}, options={})
    result = asyncio.run(
        EnhancedOptionsFlowHandler(entry).async_step_init(
            {ENHANCED_ENABLED: True, ENHANCED_MODE: "blend", ENHANCED_HISTORY_DAYS: 21}
        )
    )
    assert result["data"] == {
        ENHANCED_ENABLED: True,
        ENHANCED_MODE: "blend",
        ENHANCED_HISTORY_DAYS: 21,
    }
