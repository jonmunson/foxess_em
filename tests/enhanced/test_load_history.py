"""Tests for the live Enhanced historical load path."""

from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace

from homeassistant.core import CoreState
import pandas as pd

from custom_components.foxess_em.average import average_controller as average_module
from custom_components.foxess_em.average.average_controller import AverageController
from custom_components.foxess_em.enhanced.const import LoadMatchMode
from custom_components.foxess_em.enhanced.load_profile import (
    build_load_profile,
    lookup_load,
)
from custom_components.foxess_em.enhanced.snapshot import ReadOnlySnapshotProvider


class Bus:
    def async_listen_once(self, _event, _callback):
        return lambda: None


class States:
    def get(self, _entity_id):
        return SimpleNamespace(state="50")


class Forecast:
    def __init__(self, now):
        horizon_start = now.replace(hour=4, minute=30, second=0, microsecond=0)
        if horizon_start <= now:
            horizon_start += timedelta(days=1)
        self.frame = pd.DataFrame(
            {"pv_estimate": [1.0, 1.0]},
            index=pd.DatetimeIndex(
                [
                    horizon_start + timedelta(minutes=30),
                    horizon_start + timedelta(minutes=90),
                ]
            ),
        )

    def resample_data(self):
        return self.frame


class HistoricalAverage:
    def __init__(self, frame):
        self.frame = frame

    def resample_data(self):
        return self.frame


class Battery:
    def charge_total(self):
        return 2.0


def test_average_controller_preserves_legacy_default_and_accepts_enhanced_window(
    monkeypatch,
):
    monkeypatch.setattr(
        average_module,
        "async_track_utc_time_change",
        lambda *_args, **_kwargs: lambda: None,
    )
    hass = SimpleNamespace(state=CoreState.starting, bus=Bus())

    legacy = AverageController(hass, time(0, 30), time(4, 30), "sensor.load", [])
    enhanced = AverageController(
        hass,
        time(0, 30),
        time(4, 30),
        "sensor.load",
        [],
        history_days=21,
    )

    assert legacy._model._tracked_sensors["house_load_history"].primary.period.days == 2
    assert (
        enhanced._model._tracked_sensors["house_load_history"].primary.period.days == 21
    )


def test_profile_history_window_excludes_old_samples_and_percentile_changes_value():
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    rows = [
        {"timestamp": now - pd.Timedelta(days=days), "load": float(20 - days)}
        for days in range(1, 15)
    ]
    rows.append({"timestamp": now - pd.Timedelta(days=13), "load": 1000.0})

    p50 = build_load_profile(
        rows, "UTC", history_days=7, percentile=50, interval_minutes=1, now=now
    )
    p75 = build_load_profile(
        rows, "UTC", history_days=7, percentile=75, interval_minutes=1, now=now
    )

    p50_value = lookup_load(p50, now.replace(hour=12), LoadMatchMode.ALL_DAYS)
    p75_value = lookup_load(p75, now.replace(hour=12), LoadMatchMode.ALL_DAYS)
    assert p50_value is not None
    assert p75_value is not None
    assert p50_value < p75_value
    assert p75.values["load"].max() < 1000.0


def test_weekday_weekend_profile_uses_target_day_type():
    now = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)  # Monday
    dates = pd.date_range("2026-09-07T12:00:00Z", periods=8, freq="1D")
    frame = pd.DataFrame(
        {
            "timestamp": dates,
            "load": [10.0 if stamp.dayofweek >= 5 else 1.0 for stamp in dates],
        }
    )
    profile = build_load_profile(
        frame,
        "UTC",
        history_days=7,
        percentile=50,
        match_mode=LoadMatchMode.WEEKDAY_WEEKEND,
        interval_minutes=1,
        now=now,
    )

    weekday = lookup_load(
        profile,
        datetime(2026, 9, 15, 12, tzinfo=timezone.utc),
        LoadMatchMode.WEEKDAY_WEEKEND,
    )
    weekend = lookup_load(
        profile,
        datetime(2026, 9, 19, 12, tzinfo=timezone.utc),
        LoadMatchMode.WEEKDAY_WEEKEND,
    )

    assert weekday == 1.0
    assert weekend == 10.0


def minute_history(start, end, load_for_timestamp):
    index = pd.date_range(start, end, freq="1min")
    return pd.DataFrame(
        {"datetime": index, "load": [load_for_timestamp(stamp) for stamp in index]}
    )


def live_provider(now, history, percentile, match_mode):
    hass = SimpleNamespace(states=States(), config=SimpleNamespace(time_zone="UTC"))
    return ReadOnlySnapshotProvider(
        hass,
        HistoricalAverage(history),
        Forecast(now),
        Battery(),
        "sensor.battery_soc",
        10.0,
        0.1,
        eco_start_time=time(0, 30),
        eco_end_time=time(4, 30),
        now=lambda: now,
        history_days=7,
        load_percentile=percentile,
        load_match_mode=match_mode,
    )


def test_live_provider_percentile_materially_changes_planned_load():
    now = datetime(2026, 9, 28, 1, tzinfo=timezone.utc)
    history = minute_history(
        "2026-09-20T01:00:00Z",
        now,
        lambda stamp: 0.001 * (stamp.day % 10 + 1),
    )

    p50, _ = live_provider(now, history, 50, "all_days")()
    p75, _ = live_provider(now, history, 75, "all_days")()

    assert p75.load_kwh > p50.load_kwh


def test_live_provider_weekend_matching_changes_weekend_horizon():
    now = datetime(2026, 9, 25, 23, tzinfo=timezone.utc)  # Friday -> Saturday peak
    history = minute_history(
        "2026-09-17T01:00:00Z",
        now,
        lambda stamp: 0.01 if stamp.dayofweek >= 5 else 0.001,
    )

    all_days, _ = live_provider(now, history, 50, "all_days")()
    matched, _ = live_provider(now, history, 50, "weekday_weekend")()

    assert matched.load_kwh > all_days.load_kwh
