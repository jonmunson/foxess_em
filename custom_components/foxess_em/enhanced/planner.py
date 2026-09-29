"""Pure enhanced battery target planner; this module has no HA/write-path imports."""
from __future__ import annotations
from dataclasses import dataclass
import math
from .models import Diagnostics, EnhancedResult

@dataclass(frozen=True)
class PlannerInput:
    load_kwh: float
    pv_kwh: float
    soc: float
    capacity_kwh: float
    min_soc: float = 0.0
    charge_efficiency: float = 1.0
    max_charge_power_kw: float = math.inf
    interval_hours: float = 1.0
    reserve_kwh: float = 0.0
    legacy_target_kwh: float = 0.0

@dataclass(frozen=True)
class EnhancedPlan:
    enhanced_target_kwh: float
    charge_required_kwh: float
    reserve_kwh: float
    status: str
    legacy_delta_kwh: float = 0.0
    diagnostics: Diagnostics = Diagnostics()


def plan_energy(inp: PlannerInput | None = None, **kwargs) -> EnhancedPlan:
    """Return the charge target needed to cover net load and reserve.

    Target is grid/battery charge energy before efficiency, bounded by available
    battery capacity and interval charge power. Surplus PV produces no charge
    requirement (the target remains zero).
    """
    if inp is None:
        inp = PlannerInput(**kwargs)
    vals = (inp.load_kwh, inp.pv_kwh, inp.soc, inp.capacity_kwh, inp.min_soc,
            inp.charge_efficiency, inp.max_charge_power_kw, inp.interval_hours, inp.reserve_kwh)
    if not all(math.isfinite(float(v)) for v in vals if v != math.inf):
        return EnhancedPlan(0.0, 0.0, max(0.0, inp.reserve_kwh), "error", diagnostics=Diagnostics("error", ("non-finite input",)))
    if inp.capacity_kwh < 0 or not 0 <= inp.min_soc <= 100 or not 0 <= inp.soc <= 100 or inp.soc < inp.min_soc:
        raise ValueError("invalid battery state")
    if not 0 < inp.charge_efficiency <= 1 or inp.interval_hours <= 0 or inp.max_charge_power_kw < 0:
        raise ValueError("invalid charging limits")
    usable = inp.capacity_kwh * max(0.0, inp.soc - inp.min_soc) / 100.0
    needed = max(0.0, inp.load_kwh - inp.pv_kwh) + max(0.0, inp.reserve_kwh)
    charge = max(0.0, needed - usable) / inp.charge_efficiency
    charge = min(charge, inp.max_charge_power_kw * inp.interval_hours)
    status = "surplus_pv" if inp.pv_kwh >= inp.load_kwh else "ok"
    target = charge
    return EnhancedPlan(target, charge, max(0.0, inp.reserve_kwh), status,
                        target - inp.legacy_target_kwh,
                        Diagnostics(status=status))

plan = plan_energy
