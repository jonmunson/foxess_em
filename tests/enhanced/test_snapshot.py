"""Tests for the read-only Home Assistant snapshot adapter."""

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo
from types import SimpleNamespace

import pandas as pd
import pytest

from custom_components.foxess_em.enhanced.snapshot import (
    ReadOnlySnapshotProvider,
    SnapshotUnavailable,
)

NOW = datetime(2026, 9, 28, 1, 0, tzinfo=timezone.utc)


class Average:
    def __init__(self, load=10.0):
        self.load = load

    def average_peak_house_load(self):
        return self.load


class Forecast:
    def __init__(self, frame):
        self.frame = frame

    def resample_data(self):
        return self.frame


class Battery:
    def __init__(self, target=3.0):
        self.target = target

    def charge_total(self):
        return self.target


class States:
    def __init__(self, value="50"):
        self.value = value

    def get(self, _entity_id):
        if self.value is None:
            return None
        return SimpleNamespace(state=self.value)


def forecast_frame(include_quantiles=True):
    index = pd.DatetimeIndex(
        [
            "2026-09-28T03:00:00+00:00",  # before the peak horizon
            "2026-09-28T05:00:00+00:00",
            "2026-09-28T06:00:00+00:00",
            "2026-09-29T01:00:00+00:00",  # after the peak horizon
        ]
    )
    data = {"pv_estimate": [99.0, 1.0, 2.0, 99.0]}
    if include_quantiles:
        data.update(
            {
                "pv_p10": [88.0, 0.5, 1.0, 88.0],
                "pv_p90": [111.0, 1.5, 3.0, 111.0],
            }
        )
    return pd.DataFrame(data, index=index)


def provider(mode="p50", *, state="50", frame=None, buffer=5.0):
    hass = SimpleNamespace(states=States(state))
    return ReadOnlySnapshotProvider(
        hass,
        Average(),
        Forecast(frame if frame is not None else forecast_frame()),
        Battery(),
        "sensor.battery_soc",
        10.0,
        0.1,
        max_charge_power_kw=3.6,
        fixed_day_buffer_kwh=buffer,
        mode=mode,
        eco_start_time=time(0, 30),
        eco_end_time=time(4, 30),
        now=lambda: NOW,
    )


@pytest.mark.parametrize(
    ("mode", "expected_pv"),
    [("p10", 1.5), ("p50", 3.0), ("p90", 4.5), ("blend", 2.25)],
)
def test_snapshot_uses_real_quantile_columns_and_peak_horizon(mode, expected_pv):
    source = provider(mode)

    planner_input, legacy = source()

    assert planner_input.load_kwh == 10.0
    assert planner_input.pv_kwh == expected_pv
    assert planner_input.soc == 50.0
    assert planner_input.reserve_kwh == 5.0
    assert legacy == 3.0
    assert "legacy_two_day_load_profile" in source.last_diagnostics
    assert "fixed_reserve_fallback" in source.last_diagnostics
    if mode == "blend":
        assert "fixed_conservative_blend" in source.last_diagnostics


def test_missing_quantile_falls_back_to_central_forecast():
    source = provider("p10", frame=forecast_frame(include_quantiles=False))

    planner_input, _legacy = source()

    assert planner_input.pv_kwh == 3.0
    assert "p10 fallback to p50" in source.last_diagnostics


@pytest.mark.parametrize("state", [None, "unknown", "nan"])
def test_snapshot_rejects_missing_or_invalid_soc(state):
    with pytest.raises(SnapshotUnavailable) as error:
        provider(state=state)()

    assert error.value.diagnostics == ("soc_unavailable",)


def test_snapshot_rejects_forecast_without_rows_in_horizon():
    frame = forecast_frame().iloc[[0, 3]]

    with pytest.raises(SnapshotUnavailable) as error:
        provider(frame=frame)()

    assert error.value.diagnostics[0] == "forecast_unavailable"


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 3, 28, 1, tzinfo=timezone.utc), 294.0),
        (datetime(2026, 10, 24, 1, tzinfo=timezone.utc), 315.0),
    ],
)
def test_snapshot_horizon_handles_london_dst_transitions(now, expected):
    index = pd.date_range(
        now.astimezone(ZoneInfo("Europe/London")).replace(
            hour=0, minute=30, second=0, microsecond=0
        ),
        periods=30,
        freq="h",
    )
    source = ReadOnlySnapshotProvider(
        SimpleNamespace(states=States()),
        Average(),
        Forecast(pd.DataFrame({"pv_estimate": range(len(index))}, index=index)),
        Battery(),
        "sensor.battery_soc",
        10.0,
        0.1,
        fixed_day_buffer_kwh=0,
        eco_start_time=time(0, 30),
        eco_end_time=time(4, 30),
        now=lambda: now,
    )

    planner_input, _legacy = source()

    assert planner_input.pv_kwh == expected
