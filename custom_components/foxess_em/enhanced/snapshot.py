"""Read-only adapter from FoxESS controllers to planner input."""

from __future__ import annotations

from datetime import datetime, time, timedelta
import math
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd

from ..enhanced.forecast import select_forecast
from .const import LoadMatchMode
from .load_profile import build_load_profile, lookup_load
from .planner import PlannerInput


class SnapshotUnavailable(RuntimeError):
    """Raised when a safe planner snapshot cannot be built."""

    def __init__(self, *diagnostics: str):
        self.diagnostics = tuple(diagnostics)
        super().__init__(", ".join(self.diagnostics))


class ReadOnlySnapshotProvider:
    """Build a safe planner snapshot without retaining or invoking write services."""

    def __init__(
        self,
        hass,
        average_controller,
        forecast_controller,
        battery_controller,
        battery_soc_entity: str,
        capacity_kwh: float,
        min_soc: float,
        max_charge_power_kw: float = math.inf,
        fixed_day_buffer_kwh: float = 0.0,
        mode: str = "p50",
        eco_start_time: time | None = None,
        eco_end_time: time | None = None,
        now: Callable[[], datetime] | None = None,
        history_days: int | None = None,
        load_percentile: int = 75,
        load_match_mode: str = "weekday_weekend",
    ):
        self.hass, self.average, self.forecast, self.battery = (
            hass,
            average_controller,
            forecast_controller,
            battery_controller,
        )
        self.soc_entity = battery_soc_entity
        self.capacity = float(capacity_kwh)
        self.min_soc = float(min_soc) * 100 if float(min_soc) <= 1 else float(min_soc)
        self.max_charge_power = float(max_charge_power_kw)
        self.fixed_buffer = float(fixed_day_buffer_kwh)
        self.mode, self.eco_start, self.eco_end = (
            str(mode),
            eco_start_time,
            eco_end_time,
        )
        self.now = now or (lambda: datetime.now().astimezone())
        self.history_days = history_days
        self.load_percentile = load_percentile
        self.load_match_mode = LoadMatchMode(load_match_mode)
        self.last_diagnostics: tuple[str, ...] = ()

    def _window(self) -> tuple[datetime, datetime]:
        current = self.now()
        if current.tzinfo is None:
            raise SnapshotUnavailable("clock_timezone_unavailable")
        timezone_name = getattr(getattr(self.hass, "config", None), "time_zone", None)
        timezone = ZoneInfo(timezone_name) if timezone_name else current.tzinfo
        current = current.astimezone(timezone)
        start = datetime.combine(current.date(), self.eco_end, current.tzinfo)
        if start <= current:
            start += timedelta(days=1)
        end = datetime.combine(start.date(), self.eco_start, current.tzinfo)
        if end <= start:
            end += timedelta(days=1)
        return start, end

    def _horizon(self, index: pd.DatetimeIndex) -> pd.Series:
        start, end = self._window()
        local = (
            index.tz_convert(start.tzinfo)
            if index.tz is not None
            else index.tz_localize(start.tzinfo)
        )
        return (local >= start) & (local <= end)

    def __call__(self) -> tuple[PlannerInput, float]:
        diagnostics: list[str] = []
        if not (self.eco_start and self.eco_end):
            raise SnapshotUnavailable("eco_horizon_unavailable")
        try:
            if self.history_days is None:
                load = float(self.average.average_peak_house_load())
                diagnostics.append("legacy_two_day_load_profile")
            else:
                frame = self.average.resample_data()
                profile = build_load_profile(
                    frame.rename(columns={"datetime": "timestamp"}),
                    self.hass.config.time_zone,
                    self.history_days,
                    self.load_percentile,
                    self.load_match_mode,
                    interval_minutes=1,
                    now=self.now(),
                )
                if profile.values.empty:
                    raise ValueError
                start, end = self._window()
                minutes = pd.date_range(start, end, freq="1min", inclusive="both")
                values = [
                    lookup_load(profile, stamp.to_pydatetime(), self.load_match_mode)
                    for stamp in minutes
                ]
                if not values or any(value is None for value in values):
                    raise ValueError
                load = float(sum(value for value in values if value is not None))
                diagnostics.extend(
                    (
                        f"history_days:{self.history_days}",
                        f"load_percentile:{self.load_percentile}",
                        f"load_match_mode:{self.load_match_mode.value}",
                    )
                )
        except (AttributeError, TypeError, ValueError):
            raise SnapshotUnavailable(
                "enhanced_load_profile_unavailable", "load_unavailable"
            ) from None
        if not math.isfinite(load) or load < 0:
            raise SnapshotUnavailable(
                "enhanced_load_profile_unavailable", "load_invalid"
            )
        try:
            frame = self.forecast.resample_data()
            if not isinstance(frame, pd.DataFrame) or frame.empty:
                raise ValueError
            weights = None
            if self.mode == "blend":
                # Conservative midpoint between Solcast P10 and P50.
                weights = {"p10": 0.5, "p50": 0.5, "p90": 0.0}
                diagnostics.append("fixed_conservative_blend")
            selected, forecast_diagnostics = select_forecast(
                frame, self.mode, weights=weights
            )
            diagnostics.extend(forecast_diagnostics)
            mask = self._horizon(pd.DatetimeIndex(selected.index))
            selected = pd.to_numeric(selected, errors="coerce")[mask].dropna()
            if selected.empty:
                raise ValueError
            pv = float(selected.sum())
        except Exception as err:
            raise SnapshotUnavailable(
                "forecast_unavailable", f"forecast_error:{type(err).__name__}"
            ) from None
        state = self.hass.states.get(self.soc_entity) if self.hass is not None else None
        try:
            soc = float(state.state)
            if not math.isfinite(soc):
                raise ValueError
        except (AttributeError, TypeError, ValueError):
            raise SnapshotUnavailable("soc_unavailable") from None
        if not math.isfinite(self.capacity) or self.capacity <= 0:
            raise SnapshotUnavailable("capacity_invalid")
        if not math.isfinite(self.min_soc) or not 0 <= self.min_soc <= 100:
            raise SnapshotUnavailable("min_soc_invalid")
        try:
            legacy = float(self.battery.charge_total())
            if not math.isfinite(legacy):
                raise ValueError
        except (AttributeError, TypeError, ValueError, KeyError):
            raise SnapshotUnavailable("legacy_target_unavailable") from None
        if self.fixed_buffer < 0 or not math.isfinite(self.fixed_buffer):
            raise SnapshotUnavailable("fixed_reserve_invalid")
        if self.fixed_buffer:
            diagnostics.append("fixed_reserve_fallback")
        self.last_diagnostics = tuple(diagnostics)
        return (
            PlannerInput(
                load,
                pv,
                soc,
                self.capacity,
                self.min_soc,
                max_charge_power_kw=self.max_charge_power,
                reserve_kwh=self.fixed_buffer,
                legacy_target_kwh=legacy,
            ),
            legacy,
        )
