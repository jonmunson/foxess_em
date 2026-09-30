"""Value-oriented outputs for enhanced planning."""

from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Mapping

from .const import MAX_HISTORY_DAYS, MIN_HISTORY_DAYS, ForecastMode, LoadMatchMode


@dataclass(frozen=True)
class Diagnostics:
    status: str = "ok"
    messages: tuple[str, ...] = ()
    insufficient_history: bool = False
    forecast_source: str | None = None


@dataclass(frozen=True)
class EnhancedSettings:
    enabled: bool = False
    history_days: int = 14
    load_match: LoadMatchMode = LoadMatchMode.ALL_DAYS
    forecast_mode: ForecastMode = ForecastMode.P50
    blend_weights: Mapping[str, float] = field(
        default_factory=lambda: MappingProxyType({"p10": 0.0, "p50": 1.0, "p90": 0.0})
    )
    load_percentile: float = 50.0
    reserve_percentile: float = 10.0
    reserve_window_minutes: int = 60
    reserve_min_kwh: float = 0.0
    reserve_max_kwh: float = math.inf

    def __post_init__(self):
        if not MIN_HISTORY_DAYS <= self.history_days <= MAX_HISTORY_DAYS:
            raise ValueError("history_days must be 7..30")
        if not 0 <= self.load_percentile <= 100:
            raise ValueError("load_percentile must be 0..100")
        if not 0 <= self.reserve_percentile <= 100:
            raise ValueError("reserve_percentile must be 0..100")
        if self.reserve_window_minutes <= 0:
            raise ValueError("reserve_window_minutes must be positive")
        if self.reserve_min_kwh < 0 or self.reserve_max_kwh < self.reserve_min_kwh:
            raise ValueError("invalid reserve bounds")
        weights = {str(k): float(v) for k, v in self.blend_weights.items()}
        if any(not math.isfinite(v) or v < 0 for v in weights.values()):
            raise ValueError("blend weights must be finite and nonnegative")
        total = sum(weights.values())
        if self.forecast_mode == ForecastMode.BLEND and total <= 0:
            raise ValueError("blend weights must have a positive total")
        normalized = {k: v / total for k, v in weights.items()} if total else weights
        object.__setattr__(self, "blend_weights", MappingProxyType(normalized))


@dataclass(frozen=True)
class EnhancedResult:
    enhanced_target_kwh: float = 0.0
    charge_required_kwh: float = 0.0
    reserve_kwh: float = 0.0
    status: str = "disabled"
    legacy_delta_kwh: float = 0.0
    diagnostics: Diagnostics = field(default_factory=Diagnostics)
