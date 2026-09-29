"""Pure bounded adaptive reserve calculation.

Reserve is based on recent positive errors: max(0, actual_net - forecast_net).
The configured percentile of those errors is multiplied by the explicit safety
factor and clamped to the configured bounds.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class ReserveResult:
    reserve_kwh: float
    errors_kwh: tuple[float, ...]
    status: str = "ok"
    diagnostics: tuple[str, ...] = ()


def calculate_reserve(
    errors=None,
    *,
    actual_net=None,
    forecast_net=None,
    sample_window: int | None = None,
    percentile: float = 90.0,
    safety_factor: float = 1.0,
    min_reserve: float = 0.0,
    max_reserve: float = math.inf,
) -> ReserveResult:
    """Calculate a deterministic, bounded reserve from recent positive errors."""
    if errors is None:
        if actual_net is None or forecast_net is None:
            raise ValueError("provide errors or actual_net and forecast_net")
        errors = (float(a) - float(f) for a, f in zip(actual_net, forecast_net))
    if sample_window is not None and sample_window <= 0:
        raise ValueError("sample_window must be positive")
    if (
        not 0 <= percentile <= 100
        or safety_factor < 0
        or min_reserve < 0
        or max_reserve < min_reserve
    ):
        raise ValueError("invalid reserve settings")
    vals = [float(v) for v in errors]
    if sample_window is not None:
        vals = vals[-sample_window:]
    positives = tuple(v for v in vals if math.isfinite(v) and v > 0)
    if not positives:
        return ReserveResult(
            float(min_reserve), (), "fallback", ("no positive forecast errors",)
        )
    raw = float(np.percentile(positives, percentile, method="linear")) * safety_factor
    reserve = min(float(max_reserve), max(float(min_reserve), raw))
    return ReserveResult(reserve, positives, "ok", ())


# Friendly alias for callers using the domain term.
adaptive_reserve = calculate_reserve
