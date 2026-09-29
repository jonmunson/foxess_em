"""Pure forecast quantile selection."""
from __future__ import annotations
import math
import pandas as pd
from .const import ForecastMode

def select_forecast(data: pd.DataFrame, mode: ForecastMode | str = ForecastMode.P50, weights=None) -> tuple[pd.Series, tuple[str, ...]]:
    if not isinstance(data, pd.DataFrame): data = pd.DataFrame(data)
    mode = ForecastMode(mode)
    diagnostics = []
    def valid(name):
        if name not in data: return None
        values = pd.to_numeric(data[name], errors="coerce")
        return values.where(values.apply(lambda x: math.isfinite(float(x)) and x >= 0 if pd.notna(x) else False))
    base = valid("pv_estimate")
    if base is None: base = valid("p50")
    if base is None: raise ValueError("forecast has no usable pv_estimate/p50")
    p50 = valid("pv_p50")
    if mode == ForecastMode.P50:
        chosen, source = (p50 if p50 is not None else base), "p50" if p50 is not None else "p50 fallback to pv_estimate"
    elif mode == ForecastMode.P10:
        candidate = valid("pv_p10")
        chosen, source = (candidate if candidate is not None else base), "p10" if candidate is not None else "p10 fallback to p50"
    elif mode == ForecastMode.P90:
        candidate = valid("pv_p90")
        chosen, source = (candidate if candidate is not None else base), "p90" if candidate is not None else "p90 fallback to p50"
    else:
        weights = weights or {"p10": 0, "p50": 1, "p90": 0}
        clean = {k: max(0.0, float(v)) for k, v in weights.items() if math.isfinite(float(v))}
        total = sum(clean.values())
        if total <= 0: raise ValueError("blend weights must have positive total")
        chosen = None
        for key, weight in clean.items():
            candidate = valid("pv_" + key)
            value = (candidate if candidate is not None else base).fillna(base) * weight / total
            chosen = value if chosen is None else chosen + value
        source = "blend"
    diagnostics.append(source)
    assert chosen is not None
    return chosen.fillna(0).clip(lower=0), tuple(diagnostics)
