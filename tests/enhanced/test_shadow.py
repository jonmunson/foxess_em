from custom_components.foxess_em.enhanced.planner import PlannerInput
from custom_components.foxess_em.enhanced.shadow import compare_shadow


def test_shadow_disabled_and_missing_input_are_safe():
    assert compare_shadow(None, enabled=False).status == "disabled"
    result = compare_shadow(None)
    assert result.status == "unavailable"
    assert result.enhanced_target_kwh is None


def test_shadow_success_and_error():
    inp = PlannerInput(load_kwh=2, pv_kwh=0, soc=50, capacity_kwh=2)
    result = compare_shadow(1, inp)
    assert result.status == "ok"
    assert result.enhanced_target_kwh == 1
    assert result.legacy_delta_kwh == 0
    failed = compare_shadow(
        1, inp, planner=lambda *_a, **_k: (_ for _ in ()).throw(ValueError())
    )
    assert failed.status == "error"
    assert failed.diagnostics == ("planner_error:ValueError",)
