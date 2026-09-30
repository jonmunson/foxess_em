## FoxESS EM Enhanced shadow mode

FoxESS EM Enhanced is an **opt-in, read-only shadow path**. It is disabled by default and does not replace the existing FoxESS EM scheduler or write to an inverter. Enable it only when you want diagnostic comparisons in Home Assistant.

### Settings and sensors

The enhanced config step exposes:

- `enhanced_enabled`: false by default; enables the shadow sensors.
- `enhanced_mode`: `p10`, `p50`, `p90`, or `blend` forecast selection.
- `enhanced_history_days`: a validated 7–30 day profile window.
- `enhanced_load_percentile`: P50–P90 historical load selection.
- `enhanced_load_match_mode`: combine all days or match weekdays/weekends.

When enabled, five read-only sensors are published: **Enhanced Target**, **Charge Required**, **Reserve**, **Status**, and **Legacy Delta**. Their exact entity IDs depend on the config entry; replace the placeholders in [`dashboard-enhanced-shadow.yaml`](dashboard-enhanced-shadow.yaml).

The planner reports fallback diagnostics when requested forecast quantiles are absent. `blend` uses the midpoint of P10 and P50 and falls back to the compatible `pv_estimate` value when a quantile is absent. The live load model reads a separate 7–30-day Recorder window, applies the selected percentile per local minute, and can choose matching weekday/weekend profiles. The legacy two-day controller remains unchanged.

### Honest current limitations

- Actual-PV feedback and adaptive reserve are not connected to live operation; the fixed day buffer is used as a clearly diagnosed reserve fallback.
- There is no live enhanced control: enhanced output is never passed to charge services, schedules, FoxESS cloud, or an inverter.

### Synthetic replay and privacy

The committed replay at `tests/fixtures/enhanced/synthetic_seven_day_replay.json` is deterministic synthetic data for tests only. It is explicitly marked synthetic and contains no household identifiers, HA entity IDs, IP addresses, credentials, or personal export. Run it through the regression test with:

```bash
.venv/bin/python -m pytest tests/enhanced/test_seven_day_replay_fixture.py -q
```

Keep real exports under ignored paths such as `data/replay/`, `tests/fixtures/local/`, or `exports/`. Do not commit raw HA history or credentials. The repository safety test checks tracked source and fixtures for obvious private addresses and credential-like values.

### Not implemented

This MVP intentionally does not claim actual PV-feedback adaptation, cloud publishing, or enhanced inverter control. Those require separate production work and validation.
