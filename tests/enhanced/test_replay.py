import json

from custom_components.foxess_em.enhanced.replay import run_replay


def test_replay_is_sorted_and_deterministic():
    records = [
        {
            "timestamp": "2026-01-02T00:00:00+00:00",
            "load_kwh": 2,
            "pv_kwh": 0,
            "soc": 0,
            "capacity_kwh": 10,
        },
        {
            "timestamp": "2026-01-01T00:00:00+00:00",
            "load_kwh": 1,
            "pv_kwh": 0,
            "soc": 0,
            "capacity_kwh": 10,
        },
    ]
    a = run_replay(records, legacy_target=lambda r: 0.5)
    b = run_replay(list(reversed(records)), legacy_target=lambda r: 0.5)
    assert [r.timestamp for r in a.rows] == [
        "2026-01-01T00:00:00+00:00",
        "2026-01-02T00:00:00+00:00",
    ]
    assert a == b and a.count == 2 and a.total_delta_kwh == a.total_enhanced_kwh - 1
    assert json.loads(json.dumps(a.to_dict()))["count"] == 2


def test_replay_empty_input_has_stable_metrics():
    result = run_replay([])
    assert result.count == 0 and result.mean_absolute_delta_kwh == 0
