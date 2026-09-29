"""Pure, read-only shadow comparison for enhanced planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .models import EnhancedResult
from .planner import EnhancedPlan, PlannerInput, plan_energy


@dataclass(frozen=True)
class ShadowResult:
    """The planner's diagnostic snapshot; unavailable values stay unavailable."""

    enhanced_target_kwh: float | None = None
    charge_required_kwh: float | None = None
    reserve_kwh: float | None = None
    status: str = "unavailable"
    legacy_delta_kwh: float | None = None
    diagnostics: tuple[str, ...] = ()

    def as_result(self) -> EnhancedResult:
        """Return the legacy value object, retaining safe zero defaults."""
        return EnhancedResult(
            self.enhanced_target_kwh or 0.0,
            self.charge_required_kwh or 0.0,
            self.reserve_kwh or 0.0,
            self.status,
            self.legacy_delta_kwh or 0.0,
        )


def compare_shadow(
    legacy_target: float | Callable[[], float] | None,
    planner_input: PlannerInput | None = None,
    planner: Callable[..., EnhancedPlan] = plan_energy,
    *,
    enabled: bool = True,
    **kwargs: Any,
) -> ShadowResult:
    """Calculate a comparison without importing or invoking any write path."""
    if not enabled:
        return ShadowResult(status="disabled", diagnostics=("enhanced_disabled",))
    if planner_input is None and not kwargs:
        return ShadowResult(
            status="unavailable", diagnostics=("planner_input_unavailable",)
        )
    try:
        legacy = float(legacy_target() if callable(legacy_target) else legacy_target)
        plan = (
            planner(planner_input, **kwargs)
            if planner_input is not None
            else planner(**kwargs)
        )
        return ShadowResult(
            plan.enhanced_target_kwh,
            plan.charge_required_kwh,
            plan.reserve_kwh,
            plan.status,
            plan.enhanced_target_kwh - legacy,
            tuple(plan.diagnostics.messages),
        )
    except Exception as err:  # diagnostic boundary: shadow never affects legacy control
        return ShadowResult(
            status="error", diagnostics=(f"planner_error:{type(err).__name__}",)
        )


shadow = compare_shadow
