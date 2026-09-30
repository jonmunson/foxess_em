"""Read-only composition controller for enhanced shadow mode."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .planner import PlannerInput
from .shadow import ShadowResult, compare_shadow

Provider = Callable[
    [], tuple[PlannerInput, float] | tuple[PlannerInput, Callable[[], float]]
]


@dataclass
class EnhancedController:
    """Obtain snapshots, calculate diagnostics, and notify read-only listeners."""

    enabled: bool
    provider: Provider | None = None
    result: ShadowResult = field(default_factory=ShadowResult)
    _update_listeners: list[Callable[[], None] | Any] = field(
        default_factory=list, repr=False
    )

    def add_update_listener(
        self, listener: Callable[[], None] | Any
    ) -> Callable[[], None]:
        self._update_listeners.append(listener)
        removed = False

        def unsubscribe() -> None:
            nonlocal removed
            if not removed:
                removed = True
                if listener in self._update_listeners:
                    self._update_listeners.remove(listener)

        return unsubscribe

    def update_callback(self) -> ShadowResult:
        self.update()
        for listener in tuple(self._update_listeners):
            try:
                listener() if callable(listener) else listener.update_callback()
            except Exception:
                continue
        return self.result

    def update(
        self,
        planner_input: PlannerInput | None = None,
        legacy_target: float | Callable[[], float] | None = None,
        **kwargs: Any,
    ) -> ShadowResult:
        if not self.enabled:
            self.result = compare_shadow(None, enabled=False)
            return self.result
        try:
            if planner_input is None:
                if self.provider is None:
                    self.result = ShadowResult(
                        status="unavailable", diagnostics=("provider_unavailable",)
                    )
                    return self.result
                planner_input, legacy_target = self.provider()
            self.result = compare_shadow(legacy_target, planner_input, **kwargs)
            provider_diagnostics = tuple(getattr(self.provider, "last_diagnostics", ()))
            if provider_diagnostics:
                self.result = ShadowResult(
                    self.result.enhanced_target_kwh,
                    self.result.charge_required_kwh,
                    self.result.reserve_kwh,
                    self.result.status,
                    self.result.legacy_delta_kwh,
                    self.result.diagnostics + provider_diagnostics,
                )
        except Exception as err:
            if hasattr(err, "diagnostics"):
                self.result = ShadowResult(
                    status="unavailable", diagnostics=tuple(err.diagnostics)
                )
                return self.result
            self.result = ShadowResult(
                status="error", diagnostics=(f"provider_error:{type(err).__name__}",)
            )
        return self.result

    def unload(self) -> None:
        self._update_listeners.clear()
        self.result = ShadowResult(status="disabled", diagnostics=("unloaded",))

    @property
    def status(self):
        return self.result.status

    @property
    def enhanced_target_kwh(self):
        return self.result.enhanced_target_kwh

    @property
    def charge_required_kwh(self):
        return self.result.charge_required_kwh

    @property
    def reserve_kwh(self):
        return self.result.reserve_kwh

    @property
    def legacy_delta_kwh(self):
        return self.result.legacy_delta_kwh

    @property
    def diagnostics(self):
        return self.result.diagnostics
