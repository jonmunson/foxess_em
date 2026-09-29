import json
from pathlib import Path

from custom_components.foxess_em.enhanced.replay import run_replay

FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "enhanced"
    / "synthetic_seven_day_replay.json"
)


def test_synthetic_seven_day_fixture_runs_deterministically():
    payload = json.loads(FIXTURE.read_text())
    assert payload["metadata"]["synthetic"] is True
    result = run_replay(payload["records"])
    assert result.count == 7
    assert result.rows[0].timestamp < result.rows[-1].timestamp
    assert result == run_replay(list(reversed(payload["records"])))
    assert result.total_enhanced_kwh >= 0
