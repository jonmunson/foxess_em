"""Disposable HA composition-root harness with a recording inverter.

The harness deliberately replaces transport and platform boundaries: no socket,
HTTP, serial, or real Home Assistant service is reachable from these tests.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import socket
from types import SimpleNamespace

import pandas as pd
import pytest

from custom_components.foxess_em import async_setup_entry, async_unload_entry
from custom_components.foxess_em.const import (
    AUX_POWER,
    BATTERY_CAPACITY,
    BATTERY_SOC,
    CONNECTION_TYPE,
    DAY_BUFFER,
    DOMAIN,
    ECO_END_TIME,
    ECO_START_TIME,
    ENHANCED_ENABLED,
    ENHANCED_HISTORY_DAYS,
    ENHANCED_MODE,
    FOX_MODBUS_HOST,
    FOX_MODBUS_PORT,
    FOX_MODBUS_TCP,
    HOUSE_POWER,
    MIN_SOC,
    PLATFORMS,
)
from custom_components.foxess_em.enhanced.controller import EnhancedController
from custom_components.foxess_em.enhanced.planner import PlannerInput


class RecordingFoxService:
    """Transport substitute: reads are synthetic and writes are auditable."""

    def __init__(self):
        self.writes = []

    async def start_force_charge_now(self, *args):
        self.writes.append(("start_force_charge_now", args))

    async def start_force_charge_off_peak(self, *args):
        self.writes.append(("start_force_charge_off_peak", args))

    async def stop_force_charge(self, *args):
        self.writes.append(("stop_force_charge", args))


class FakeServices:
    def __init__(self):
        self.registered = {}

    def async_register(self, domain, name, handler):
        self.registered[(domain, name)] = handler


class FakeConfigEntries:
    def __init__(self):
        self.forwarded = []
        self.unloaded = []

    async def async_forward_entry_setups(self, entry, platforms):
        self.forwarded.append((entry.entry_id, tuple(platforms)))

    async def async_forward_entry_unload(self, entry, platform):
        self.unloaded.append((entry.entry_id, platform))
        return True


class FakeHass:
    def __init__(self):
        self.data = {}
        self.services = FakeServices()
        self.config_entries = FakeConfigEntries()
        self.config = SimpleNamespace(time_zone="UTC")
        self.states = SimpleNamespace(
            get=lambda entity_id: (
                SimpleNamespace(state="50")
                if entity_id == "sensor.synthetic_soc"
                else None
            )
        )


class FakeEntry:
    entry_id = "synthetic-entry"
    data = {
        CONNECTION_TYPE: FOX_MODBUS_TCP,
        FOX_MODBUS_HOST: "192.0.2.10",
        FOX_MODBUS_PORT: 502,
        ECO_START_TIME: "00:00:00",
        ECO_END_TIME: "06:00:00",
        HOUSE_POWER: "sensor.synthetic_house",
        AUX_POWER: "sensor.synthetic_aux",
        BATTERY_SOC: "sensor.synthetic_soc",
        BATTERY_CAPACITY: 10,
        MIN_SOC: 10,
        DAY_BUFFER: 1,
    }
    options = {}

    def __init__(self, enabled=False):
        self.options = {ENHANCED_ENABLED: enabled}
        self.listeners = []

    def add_update_listener(self, callback):
        self.listeners.append(callback)
        return lambda: self.listeners.remove(callback)


class FakeController:
    def __init__(self, *args, **kwargs):
        self.listeners = []
        self.unloaded = False

    def add_update_listener(self, callback):
        self.listeners.append(callback)
        return lambda: self.listeners.remove(callback)

    async def clear_schedule(self, *args):
        return None

    def unload(self):
        self.unloaded = True
        self.listeners.clear()

    async def async_refresh(self):
        return None


class FakeAverage(FakeController):
    """Synthetic minute-level load history for the real snapshot provider."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        now = datetime.now(timezone.utc)
        index = pd.date_range(now - timedelta(days=16), now, freq="1min")
        self.frame = pd.DataFrame({"datetime": index, "load": [0.001] * len(index)})

    def resample_data(self):
        return self.frame


class FakeForecast(FakeController):
    """Synthetic future solar forecast for the real snapshot provider."""

    def __init__(self, *args, **kwargs):
        super().__init__()
        now = datetime.now(timezone.utc)
        index = pd.date_range(now, now + timedelta(days=2), freq="30min")
        self.frame = pd.DataFrame({"pv_estimate": [0.01] * len(index)}, index=index)

    def resample_data(self):
        return self.frame


class FakeBattery(FakeController):
    def charge_total(self):
        return 2.0


class FakeCharge(FakeController):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.fox = kwargs.get("fox") or (args[3] if len(args) > 3 else None)


@pytest.fixture
def patched_root(monkeypatch):
    import custom_components.foxess_em as root

    service = RecordingFoxService()
    monkeypatch.setattr(root, "Schedule", lambda *a, **k: FakeController())
    monkeypatch.setattr(root, "FoxModbuservice", lambda *a, **k: service)
    monkeypatch.setattr(root, "FoxModbus", lambda *a, **k: object())
    monkeypatch.setattr(root, "ForecastController", FakeForecast)
    monkeypatch.setattr(root, "AverageController", FakeAverage)
    monkeypatch.setattr(root, "BatteryController", FakeBattery)
    monkeypatch.setattr(root, "ChargeService", FakeCharge)
    return service


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    """Fail immediately if any unpatched path attempts a socket connection."""

    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in the disposable harness")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


async def setup(hass, entry):
    assert await async_setup_entry(hass, entry)
    return hass.data[DOMAIN][entry.entry_id]


def test_network_guard_rejects_socket_connections():
    with pytest.raises(AssertionError, match="network access is forbidden"):
        socket.socket().connect(("192.0.2.1", 502))


def test_disabled_entry_does_not_construct_enhanced(monkeypatch, patched_root):
    import custom_components.foxess_em as root
    import custom_components.foxess_em.enhanced.controller as controller_module
    import custom_components.foxess_em.enhanced.snapshot as snapshot_module

    def forbidden_constructor(*_args, **_kwargs):
        raise AssertionError("disabled mode constructed an enhanced component")

    monkeypatch.setattr(controller_module, "EnhancedController", forbidden_constructor)
    monkeypatch.setattr(
        snapshot_module, "ReadOnlySnapshotProvider", forbidden_constructor
    )
    monkeypatch.setattr(
        root,
        "normalize_settings",
        lambda data: {
            ENHANCED_ENABLED: False,
            ENHANCED_MODE: "p50",
            ENHANCED_HISTORY_DAYS: 14,
            "enhanced_load_percentile": 75,
            "enhanced_load_match_mode": "weekday_weekend",
        },
    )
    monkeypatch.setattr(root, "async_get_clientsession", lambda hass: object())
    hass = FakeHass()
    entry = FakeEntry(False)
    state = asyncio.run(setup(hass, entry))
    assert "enhanced" not in state
    assert hass.config_entries.forwarded == [("synthetic-entry", tuple(PLATFORMS))]
    assert patched_root.writes == []
    assert asyncio.run(async_unload_entry(hass, entry)) is True


def test_enabled_shadow_is_read_only_and_unload_reload_is_clean(
    monkeypatch, patched_root
):
    import custom_components.foxess_em as root

    monkeypatch.setattr(root, "async_get_clientsession", lambda hass: object())
    monkeypatch.setattr(
        root,
        "normalize_settings",
        lambda data: {
            ENHANCED_ENABLED: True,
            ENHANCED_MODE: "p50",
            ENHANCED_HISTORY_DAYS: 14,
            "enhanced_load_percentile": 75,
            "enhanced_load_match_mode": "weekday_weekend",
        },
    )
    # The real EnhancedController is exercised with a synthetic planner snapshot.
    snapshot = PlannerInput(
        load_kwh=1.0,
        pv_kwh=0.0,
        soc=50,
        capacity_kwh=10,
        min_soc=10,
        max_charge_power_kw=3,
        interval_hours=1,
        reserve_kwh=1,
    )
    controller = EnhancedController(True, lambda: (snapshot, 2.0))
    assert controller.update().status in {"ok", "unavailable"}
    assert patched_root.writes == []

    hass = FakeHass()
    first_entry = FakeEntry(True)
    state = asyncio.run(setup(hass, first_entry))
    assert state["enhanced"].enabled is True
    assert state["enhanced"].status == "ok"
    assert patched_root.writes == []
    state["enhanced"].update_callback()
    assert patched_root.writes == []
    assert len(state["controllers"]["battery"].listeners) == 1
    assert len(state["enhanced_average"].listeners) == 1
    first_controllers = tuple(state["controllers"].values())
    first_history = state["enhanced_average"]
    assert asyncio.run(async_unload_entry(hass, first_entry)) is True
    assert not hass.data[DOMAIN].get("synthetic-entry")
    assert all(controller.unloaded for controller in first_controllers)
    assert first_history.unloaded is True

    # Reload creates a fresh graph with one listener per read-only source; the
    # previous callbacks do not survive unload and no write is emitted.
    second_entry = FakeEntry(True)
    reloaded = asyncio.run(setup(hass, second_entry))
    assert len(reloaded["controllers"]["battery"].listeners) == 1
    assert len(reloaded["enhanced_average"].listeners) == 1
    assert patched_root.writes == []
    assert asyncio.run(async_unload_entry(hass, second_entry)) is True


def test_explicit_legacy_service_call_is_the_only_recorded_write(
    monkeypatch, patched_root
):
    import custom_components.foxess_em as root

    monkeypatch.setattr(root, "async_get_clientsession", lambda hass: object())
    hass = FakeHass()
    entry = FakeEntry(False)
    asyncio.run(setup(hass, entry))
    asyncio.run(hass.services.registered[(DOMAIN, "start_force_charge_now")]())
    assert [name for name, _ in patched_root.writes] == ["start_force_charge_now"]
    assert asyncio.run(async_unload_entry(hass, entry)) is True


def test_enhanced_history_failure_keeps_legacy_setup(monkeypatch, patched_root):
    import custom_components.foxess_em as root

    monkeypatch.setattr(root, "async_get_clientsession", lambda hass: object())

    class LegacyThenFail(FakeController):
        calls = 0

        def __init__(self, *a, **k):
            type(self).calls += 1
            if type(self).calls == 2:
                raise RuntimeError("recorder unavailable")
            super().__init__(*a, **k)

    monkeypatch.setattr(root, "AverageController", LegacyThenFail)
    monkeypatch.setattr(
        root,
        "normalize_settings",
        lambda data: {
            ENHANCED_ENABLED: True,
            ENHANCED_MODE: "p50",
            ENHANCED_HISTORY_DAYS: 14,
            "enhanced_load_percentile": 75,
            "enhanced_load_match_mode": "weekday_weekend",
        },
    )
    hass = FakeHass()
    entry = FakeEntry(True)
    state = asyncio.run(setup(hass, entry))
    assert "controllers" in state
    assert state["enhanced"].status == "unavailable"
    assert asyncio.run(async_unload_entry(hass, entry)) is True
    assert not hass.data[DOMAIN].get("synthetic-entry")
