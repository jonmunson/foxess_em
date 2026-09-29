"""Compatibility tests for optional Enhanced configuration."""

import voluptuous as vol

from custom_components.foxess_em.config_flow import BatteryManagerFlowHandler
from custom_components.foxess_em.const import (
    ENHANCED_DEFAULTS,
    ENHANCED_ENABLED,
    ENHANCED_HISTORY_DAYS,
    ENHANCED_MODE,
)


def test_enhanced_defaults_are_disabled_and_do_not_require_migration():
    flow = BatteryManagerFlowHandler()

    values = flow._enhanced_schema({})

    assert flow.VERSION == 2
    assert values == ENHANCED_DEFAULTS
    assert values[ENHANCED_ENABLED] is False


def test_enhanced_settings_validate_and_round_trip():
    flow = BatteryManagerFlowHandler()
    configured = {
        ENHANCED_ENABLED: True,
        ENHANCED_MODE: "p10",
        ENHANCED_HISTORY_DAYS: 21,
    }

    assert flow._enhanced_schema(configured) == configured


def test_enhanced_history_window_and_mode_are_constrained():
    flow = BatteryManagerFlowHandler()

    for days in (6, 31):
        try:
            flow._enhanced_schema(
                {
                    ENHANCED_ENABLED: True,
                    ENHANCED_MODE: "p50",
                    ENHANCED_HISTORY_DAYS: days,
                }
            )
        except vol.Invalid:
            pass
        else:
            raise AssertionError(f"history window {days} should be rejected")

    try:
        flow._enhanced_schema(
            {
                ENHANCED_ENABLED: True,
                ENHANCED_MODE: "invented",
                ENHANCED_HISTORY_DAYS: 14,
            }
        )
    except vol.Invalid:
        pass
    else:
        raise AssertionError("unknown forecast mode should be rejected")
