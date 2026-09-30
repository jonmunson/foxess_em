"""Deterministic, serializable replay/comparison core."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Mapping

from .planner import PlannerInput, plan_energy


@dataclass(frozen=True)
class ReplayRow:
    timestamp: str
    legacy_target_kwh: float
    enhanced_target_kwh: float
    delta_kwh: float
    status: str


@dataclass(frozen=True)
class ReplaySummary:
    rows: tuple[ReplayRow, ...]
    count: int
    total_legacy_kwh: float
    total_enhanced_kwh: float
    total_delta_kwh: float
    mean_absolute_delta_kwh: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": [asdict(row) for row in self.rows],
            "count": self.count,
            "total_legacy_kwh": self.total_legacy_kwh,
            "total_enhanced_kwh": self.total_enhanced_kwh,
            "total_delta_kwh": self.total_delta_kwh,
            "mean_absolute_delta_kwh": self.mean_absolute_delta_kwh,
        }


def run_replay(
    records: Iterable[Mapping[str, Any]],
    legacy_target: Callable[[Mapping[str, Any]], float] | float = 0.0,
) -> ReplaySummary:
    rows = []
    ordered = sorted(
        records, key=lambda r: str(r.get("timestamp", r.get("datetime", "")))
    )
    for record in ordered:
        ts = str(record.get("timestamp", record.get("datetime", "")))
        legacy = float(
            legacy_target(record)
            if callable(legacy_target)
            else record.get("legacy_target_kwh", legacy_target)
        )
        values = {
            k: record[k]
            for k in ("load_kwh", "pv_kwh", "soc", "capacity_kwh")
            if k in record
        }
        if "load_kwh" not in values:
            values["load_kwh"] = float(record.get("load", 0.0))
        if "pv_kwh" not in values:
            values["pv_kwh"] = float(record.get("pv", record.get("pv_estimate", 0.0)))
        values.setdefault("soc", 50.0)
        values.setdefault("capacity_kwh", 10.0)
        for key in (
            "min_soc",
            "charge_efficiency",
            "max_charge_power_kw",
            "interval_hours",
            "reserve_kwh",
        ):
            if key in record:
                values[key] = record[key]
        result = plan_energy(PlannerInput(**values, legacy_target_kwh=legacy))
        rows.append(
            ReplayRow(
                ts,
                legacy,
                result.enhanced_target_kwh,
                result.legacy_delta_kwh,
                result.status,
            )
        )
    total_l = sum(r.legacy_target_kwh for r in rows)
    total_e = sum(r.enhanced_target_kwh for r in rows)
    return ReplaySummary(
        tuple(rows),
        len(rows),
        total_l,
        total_e,
        total_e - total_l,
        sum(abs(r.delta_kwh) for r in rows) / len(rows) if rows else 0.0,
    )


replay = run_replay
