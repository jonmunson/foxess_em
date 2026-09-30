from custom_components.foxess_em.enhanced.planner import PlannerInput, plan_energy


def test_planner_accounts_for_usable_soc_reserve_and_efficiency():
    result = plan_energy(
        PlannerInput(
            load_kwh=5,
            pv_kwh=1,
            soc=20,
            capacity_kwh=10,
            min_soc=10,
            reserve_kwh=1,
            charge_efficiency=0.8,
            max_charge_power_kw=20,
            legacy_target_kwh=2,
        )
    )
    # net+reserve=5, usable above min SOC=1; 4/.8=5
    assert result.charge_required_kwh == 5
    assert result.legacy_delta_kwh == 3


def test_planner_surplus_pv_needs_no_charge():
    result = plan_energy(PlannerInput(load_kwh=2, pv_kwh=4, soc=10, capacity_kwh=10))
    assert result.charge_required_kwh == 0 and result.status == "surplus_pv"


def test_planner_respects_power_limit_and_is_value_oriented():
    result = plan_energy(
        PlannerInput(
            load_kwh=10,
            pv_kwh=0,
            soc=0,
            capacity_kwh=10,
            max_charge_power_kw=2,
            interval_hours=0.5,
        )
    )
    assert result.charge_required_kwh == 1
    assert not hasattr(result, "schedule")
