"""DST-safe, timezone-explicit historical load profiles."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd

from .const import LoadMatchMode


@dataclass(frozen=True)
class LoadProfile:
    values: pd.DataFrame
    diagnostics: tuple[str, ...] = ()


def build_load_profile(
    samples,
    timezone: str,
    history_days: int = 14,
    percentile: float = 50,
    match_mode: LoadMatchMode = LoadMatchMode.ALL_DAYS,
    interval_minutes: int = 60,
    now: datetime | None = None,
) -> LoadProfile:
    if not 7 <= history_days <= 30:
        raise ValueError("history_days must be 7..30")
    if not 0 <= percentile <= 100:
        raise ValueError("percentile must be 0..100")
    if interval_minutes <= 0 or 1440 % interval_minutes:
        raise ValueError("interval_minutes must divide 1440")
    df = samples.copy() if isinstance(samples, pd.DataFrame) else pd.DataFrame(samples)
    time_col = (
        "timestamp"
        if "timestamp" in df
        else "datetime" if "datetime" in df else "period_start"
    )
    load_col = "load" if "load" in df else "load_kwh"
    if time_col not in df or load_col not in df:
        raise ValueError("samples need timestamp and load columns")
    raw_ts = pd.to_datetime(df[time_col], errors="coerce")
    if getattr(raw_ts.dt, "tz", None) is None:
        raise ValueError("load samples must have timezone-aware timestamps")
    ts = raw_ts.dt.tz_convert("UTC")
    df = pd.DataFrame(
        {"timestamp": ts, "load": pd.to_numeric(df[load_col], errors="coerce")}
    ).dropna()
    local = df.timestamp.dt.tz_convert(timezone)
    end = pd.Timestamp(now if now is not None else datetime.now().astimezone())
    if end.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    end = end.tz_convert(timezone)
    df = df[(local >= end - pd.Timedelta(days=history_days)) & (local <= end)].copy()
    local = df.timestamp.dt.tz_convert(timezone)
    df["minute"] = (
        local.dt.hour * 60 + (local.dt.minute // interval_minutes) * interval_minutes
    )
    df["day_type"] = np.where(local.dt.dayofweek < 5, "weekday", "weekend")
    group = (
        ["minute"] if match_mode == LoadMatchMode.ALL_DAYS else ["day_type", "minute"]
    )
    values = (
        df.groupby(group, dropna=False)["load"]
        .quantile(percentile / 100)
        .to_frame("load")
    )
    messages = (
        () if len(df) else ("insufficient history: no samples in requested window",)
    )
    return LoadProfile(values=values, diagnostics=messages)


def lookup_load(
    profile: LoadProfile,
    when: datetime,
    match_mode: LoadMatchMode = LoadMatchMode.ALL_DAYS,
) -> float | None:
    local = pd.Timestamp(when)
    if local.tzinfo is None:
        raise ValueError("lookup timestamp must be timezone-aware")
    minute = local.hour * 60 + local.minute
    key = minute
    if match_mode == LoadMatchMode.WEEKDAY_WEEKEND:
        key = ("weekday" if local.dayofweek < 5 else "weekend", minute)
    try:
        return float(profile.values.loc[key, "load"])
    except KeyError:
        return None
