"""Tests for read-only Enhanced diagnostic entities."""

from types import SimpleNamespace

from custom_components.foxess_em.enhanced.controller import EnhancedController
from custom_components.foxess_em.enhanced.planner import PlannerInput
from custom_components.foxess_em.enhanced.sensor import sensors


def snapshot():
    return PlannerInput(5.0, 1.0, 50.0, 10.0, reserve_kwh=1.0), 2.0


def test_five_sensors_have_stable_ids_values_and_safe_attributes():
    controller = EnhancedController(True, snapshot)
    controller.update_callback()

    entities = sensors(controller, SimpleNamespace(entry_id="entry-1"))

    assert len(entities) == 5
    assert {entity.unique_id for entity in entities} == {
        "entry-1_enhanced_enhanced_target_kwh",
        "entry-1_enhanced_charge_required_kwh",
        "entry-1_enhanced_reserve_kwh",
        "entry-1_enhanced_status",
        "entry-1_enhanced_legacy_delta_kwh",
    }
    assert all(entity.available for entity in entities)
    assert {entity.name for entity in entities} == {
        "FoxESS Enhanced Enhanced Target",
        "FoxESS Enhanced Charge Required",
        "FoxESS Enhanced Reserve",
        "FoxESS Enhanced Status",
        "FoxESS Enhanced Legacy Delta",
    }
    for entity in entities:
        assert set(entity.extra_state_attributes) == {"status", "diagnostics"}
        assert "api" not in repr(entity.extra_state_attributes).lower()


def test_disabled_and_unavailable_sensors_do_not_publish_values():
    disabled = EnhancedController(False, snapshot)
    disabled.update_callback()
    disabled_entities = sensors(disabled, SimpleNamespace(entry_id="entry-2"))
    assert all(not entity.available for entity in disabled_entities)
    assert all(entity.native_value is None for entity in disabled_entities)

    unavailable = EnhancedController(True)
    unavailable.update_callback()
    unavailable_entities = sensors(unavailable, SimpleNamespace(entry_id="entry-3"))
    status = next(entity for entity in unavailable_entities if entity._key == "status")
    numeric = [entity for entity in unavailable_entities if entity._key != "status"]
    assert status.available
    assert status.native_value == "unavailable"
    assert status.extra_state_attributes["diagnostics"] == ["provider_unavailable"]
    assert all(not entity.available for entity in numeric)
    assert all(entity.native_value is None for entity in numeric)
