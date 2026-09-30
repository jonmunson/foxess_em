# FoxESS EM Enhanced Shadow-Mode MVP Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Add a disabled-by-default, local-only enhanced planning and shadow-controller path that computes and exposes enhanced targets without depending on `FoxService`, mutating `Schedule`, or writing to an inverter, while preserving the existing `foxess_em` behavior and configuration.

**Architecture:** Keep the existing legacy controllers, `BatteryController`, `Schedule`, `ChargeService`, and inverter write services unchanged on the active path. Add a pure package under `custom_components/foxess_em/enhanced/` with immutable/value-oriented inputs and outputs for load profiling, forecast quantiles, adaptive reserve, planning, replay, and shadow comparison. Wire it into Home Assistant only when an explicit enhanced option is enabled; the integration will publish diagnostic sensors and status, but will never pass enhanced output to `ChargeService` or any Fox service in this MVP.

**Tech Stack:** Python 3.13-compatible code, Home Assistant custom integration APIs, pandas/numpy only where already justified by the project, pytest/pytest-asyncio (or the repository's existing async conventions), timezone-aware `datetime`/`zoneinfo`, synthetic JSON fixtures, and existing sensor/config-entry infrastructure.

---

## Scope and invariants

- Preserve the `custom_components.foxess_em` domain and all existing config keys/defaults.
- Leave the legacy `AverageController` (including its current two-day behavior) and `BatteryController` path intact.
- Extend the forecast data contract compatibly: keep `pv_estimate`; map optional Solcast `pv_estimate10` and `pv_estimate90` to `pv_p10` and `pv_p90`.
- Enhanced code must not import or instantiate `FoxService`, `FoxCloudService`, `FoxModbuservice`, `ChargeService`, `BatteryModel`, or `Schedule`.
- Raw/personal replay data must remain local and gitignored; committed fixtures are synthetic and contain no HA entity IDs, API keys, IP addresses, or personal exports.
- Explicitly defer live enhanced control, inverter writes, cloud publishing, and replacing legacy scheduling.

## Ordered implementation tasks

### Task 1: Establish local Python 3.13 test/dev checks and safe-data guard

**Objective:** Make the repository's local validation commands explicit before adding code.

**Files:**
- Modify: `requirements_test.txt` (only if an existing dependency is incompatible or missing)
- Modify: `setup.cfg` (only if needed for Python 3.13/test discovery)
- Modify: `.gitignore`
- Create: `tests/test_repository_safety.py`

**Step 1: Write failing safety tests**

Add tests that fail if tracked/fixture content contains obvious secrets or personal HA data patterns (API-key field names with values, private IPs, and non-synthetic entity IDs), while allowing the repository's code references and placeholders. Add a test that local replay paths such as `tests/fixtures/local/` and `data/replay/` are ignored.

**Step 2: Run the focused tests**

Run:

```bash
python3.13 -m pytest tests/test_repository_safety.py -q
```

Expected: FAIL until ignore rules and test-safe fixture conventions exist.

**Step 3: Add minimal ignore rules and test helpers**

Ignore local replay directories, raw HA exports, `.env*`, and likely credential files without ignoring committed synthetic fixtures. Do not add actual user data.

**Step 4: Re-run and inspect the diff**

Run:

```bash
python3.13 -m pytest tests/test_repository_safety.py -q
python3.13 -m compileall -q custom_components tests
```

Expected: PASS and no syntax errors. If Python 3.13 cannot install the current Home Assistant constraints, record the exact incompatibility in `README.md` or `CONTRIBUTING.md`; do not weaken runtime behavior merely to satisfy an unavailable dependency.

### Task 2: Define enhanced domain types and configuration defaults

**Objective:** Create a pure, dependency-light contract for settings, forecast points, load profiles, plans, and diagnostics.

**Files:**
- Create: `custom_components/foxess_em/enhanced/__init__.py`
- Create: `custom_components/foxess_em/enhanced/models.py`
- Create: `custom_components/foxess_em/enhanced/const.py`
- Test: `tests/enhanced/test_models.py`

**Step 1: Write failing model tests**

Cover validation and serialization of:

- `EnhancedSettings(enabled=False)` defaults.
- Profile window restricted to 7–30 days.
- Matching mode `all_days` or `weekday_weekend`.
- Percentile `p10`, `p50`, `p90`, or `blend`.
- Normalized blend weights that sum to one.
- Forecast points retaining `pv_estimate` and optional p10/p90 values.
- Plan/diagnostic objects carrying enhanced target, charge required, reserve, status, and legacy delta.

**Step 2: Run the tests to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_models.py -q
```

Expected: FAIL because the enhanced package does not yet exist.

**Step 3: Implement immutable dataclasses and constants**

Use frozen dataclasses where practical. Normalize/validate values at construction, retain raw `pv_estimate` for compatibility, and keep diagnostics explicit instead of raising for recoverable forecast fallback conditions.

**Step 4: Run focused tests and type/syntax checks**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_models.py -q
python3.13 -m compileall -q custom_components/foxess_em/enhanced
```

Expected: PASS.

### Task 3: Extend the forecast contract without breaking legacy consumers

**Objective:** Preserve existing forecast behavior while importing optional Solcast quantiles.

**Files:**
- Modify: `custom_components/foxess_em/forecast/solcast_api.py:54-92`
- Modify: `custom_components/foxess_em/forecast/forecast_model.py:28-119`
- Test: `tests/enhanced/test_forecast_contract.py`

**Step 1: Write failing contract tests**

Use synthetic Solcast records to prove:

- `pv_estimate` remains present and unchanged in meaning.
- `pv_estimate10` becomes `pv_p10` and `pv_estimate90` becomes `pv_p90` when present.
- Missing quantiles do not fail loading and produce a documented fallback diagnostic.
- Existing resampling and legacy totals still operate when only `pv_estimate` exists.

**Step 2: Run the tests to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_forecast_contract.py -q
```

Expected: FAIL on missing quantile mapping/columns.

**Step 3: Implement compatibility mapping**

Copy optional keys through the API client and resampler. Ensure numeric aggregation/resampling handles absent columns and does not make legacy `pv_estimate` calls depend on quantiles.

**Step 4: Run focused regression tests**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_forecast_contract.py tests/test_fox_modbus.py -q
```

Expected: PASS; existing tests must remain green.

### Task 4: Implement DST-safe load-profile grouping and interval percentile

**Objective:** Compute configurable 7–30-day local-time load baselines without assuming fixed UTC offsets.

**Files:**
- Create: `custom_components/foxess_em/enhanced/load_profile.py`
- Test: `tests/enhanced/test_load_profile.py`
- Create: `tests/fixtures/enhanced/synthetic_load_week.json`

**Step 1: Write failing tests**

Cover timezone-aware samples across a DST transition, local interval grouping, all-days matching, weekday/weekend matching, incomplete windows, and percentile interpolation. Assert that grouping uses local wall-clock date/time after conversion to the configured timezone, not UTC date or naive timestamps.

**Step 2: Run the tests**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_load_profile.py -q
```

Expected: FAIL because no profile implementation exists.

**Step 3: Implement the smallest pure API**

Provide functions/classes equivalent to `build_load_profile(samples, settings, timezone)` and `load_for_interval(profile, timestamp)`. Reject naive input or require an explicit timezone policy; document the choice. Use only the requested historical window and return diagnostics for insufficient samples.

**Step 4: Verify formulas and DST behavior**

Run the focused test command again. Expected: all profile tests PASS, including the repeated/missing local-hour cases around DST.

### Task 5: Implement forecast percentile selection and weighted blend fallback

**Objective:** Select p10/p50/p90 or a normalized weighted blend while remaining useful with legacy p50-only forecasts.

**Files:**
- Create: `custom_components/foxess_em/enhanced/forecast.py`
- Test: `tests/enhanced/test_forecast_selection.py`

**Step 1: Write failing tests**

Test exact p10/p50/p90 selection, normalized blend weights, missing-quantile fallback to `pv_estimate`, partial quantile fallback, non-negative/finite output handling, and diagnostics identifying the fallback rather than silently changing modes.

**Step 2: Run to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_forecast_selection.py -q
```

Expected: FAIL.

**Step 3: Implement pure selection**

Accept the forecast contract from Task 3 and return selected PV plus a diagnostic status. For blend mode, normalize configured non-negative weights over available quantiles according to the documented policy, then fall back to p50/`pv_estimate` if no requested quantile exists.

**Step 4: Verify**

Run the focused test command. Expected: PASS with no calls to Home Assistant or Solcast.

### Task 6: Implement bounded adaptive reserve from synthetic/local error history

**Objective:** Add a bounded reserve derived only from recent positive net forecast errors.

**Files:**
- Create: `custom_components/foxess_em/enhanced/reserve.py`
- Test: `tests/enhanced/test_reserve.py`
- Create: `tests/fixtures/enhanced/synthetic_forecast_errors.json`

**Step 1: Write failing tests**

Prove that only positive errors contribute, the configured recent sample window is honored, the chosen statistic/formula is deterministic, and minimum/maximum reserve bounds are enforced. Include empty history and all-negative history diagnostics.

**Step 2: Run to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_reserve.py -q
```

Expected: FAIL.

**Step 3: Implement pure bounded reserve calculation**

Document the formula in code and the plan: calculate positive `actual_net - forecast_net` errors, apply the configured robust statistic (for example percentile), add a safety factor only if explicitly configured, then clamp to `[min_reserve, max_reserve]`. Do not read user files or call external services.

**Step 4: Verify**

Run the focused tests and confirm only synthetic fixtures are used.

### Task 7: Build the pure enhanced planner

**Objective:** Produce an enhanced target and charge requirement from load, selected PV, reserve, battery inputs, and settings without mutating legacy state.

**Files:**
- Create: `custom_components/foxess_em/enhanced/planner.py`
- Test: `tests/enhanced/test_planner.py`

**Step 1: Write failing formula tests**

Cover net energy calculation, reserve inclusion, SOC/capacity/min-SOC bounds, charge efficiency/power limits, no-sun and surplus-sun cases, insufficient profile/forecast diagnostics, and deterministic output. Add a guard test passing a fake object that would fail if `Schedule`-like mutation is attempted.

**Step 2: Run to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_planner.py -q
```

Expected: FAIL.

**Step 3: Implement the planner**

Use plain values/dataframes supplied by callers; do not import `BatteryModel`, `Schedule`, `FoxService`, or `ChargeService`. Return an immutable plan containing enhanced target, charge required, reserve, status, and diagnostics. Keep live inverter control out of the package.

**Step 4: Verify no write dependency**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_planner.py -q
```

Expected: PASS, including import/source checks proving no forbidden write-path dependency.

### Task 8: Add synthetic seven-day replay/comparison core

**Objective:** Compare legacy and enhanced targets over a deterministic seven-day synthetic fixture.

**Files:**
- Create: `custom_components/foxess_em/enhanced/replay.py`
- Create: `tests/fixtures/enhanced/synthetic_seven_day.json`
- Test: `tests/enhanced/test_replay.py`

**Step 1: Write failing replay tests**

Assert stable replay ordering, seven-day coverage, per-interval legacy/enhanced targets and deltas, aggregate comparison metrics, missing-quantile fallback behavior, and no external calls or writes.

**Step 2: Run to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_replay.py -q
```

Expected: FAIL.

**Step 3: Implement replay**

Define a replay input containing synthetic load/forecast/battery state and a legacy target function supplied as a callable/value adapter. Produce serializable comparison rows and summary metrics. Keep fixture values obviously synthetic and free of entity IDs or credentials.

**Step 4: Verify**

Run the focused replay tests and a JSON parse check. Expected: PASS and reproducible output across runs.

### Task 9: Implement the pure shadow controller

**Objective:** Compare legacy and enhanced targets while making it impossible to perform inverter writes.

**Files:**
- Create: `custom_components/foxess_em/enhanced/shadow.py`
- Test: `tests/enhanced/test_shadow.py`

**Step 1: Write failing tests**

Test that the shadow controller accepts a legacy target value/callable and enhanced planner inputs, emits the required diagnostic fields, reports disabled/fallback/error status, and never requires `FoxService`, `Schedule`, or a Home Assistant object.

**Step 2: Run to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_shadow.py -q
```

Expected: FAIL.

**Step 3: Implement shadow comparison**

Create a pure adapter that calls the planner and computes `enhanced_target - legacy_target`. Treat exceptions as diagnostic status with safe no-control output; do not catch errors by invoking a legacy write path.

**Step 4: Verify dependency boundary**

Run focused tests plus:

```bash
python3.13 -m pytest tests/enhanced/test_shadow.py -q
```

Expected: PASS and no forbidden imports.

### Task 10: Add disabled-by-default config compatibility and safe logging

**Objective:** Persist enhanced settings without breaking VERSION=2 entries or exposing secrets in debug logs.

**Files:**
- Modify: `custom_components/foxess_em/const.py`
- Modify: `custom_components/foxess_em/config_flow.py:50-190` and migration/options sections
- Modify: `custom_components/foxess_em/__init__.py:84-102`
- Test: `tests/enhanced/test_config_compatibility.py`
- Test: `tests/enhanced/test_logging_safety.py`

**Step 1: Write failing compatibility/logging tests**

Prove old data-only entries load with enhanced defaults disabled, old keys remain unchanged, new options round-trip, `entry.options` precedence remains compatible, and debug records contain neither Fox/Solcast credentials nor complete raw config/options mappings.

**Step 2: Run to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_config_compatibility.py tests/enhanced/test_logging_safety.py -q
```

Expected: FAIL on new settings/log redaction.

**Step 3: Implement settings and redacted logging**

Add namespaced enhanced keys with explicit defaults. Prefer an options flow step or options handler that edits only enhanced keys; retain existing config-flow steps and migration behavior. Replace complete mapping logs with a fixed safe summary (enabled/mode/window/status) and never log API keys, hosts, entity IDs, or arbitrary options.

**Step 4: Verify legacy compatibility**

Run the focused tests and existing config-flow tests if present. Expected: PASS; `VERSION` remains 2 unless migration is demonstrably required, in which case add a migration test for every old entry shape.

### Task 11: Wire shadow computation into setup without activating control

**Objective:** Instantiate enhanced components only when enabled and keep legacy setup/write behavior unchanged.

**Files:**
- Modify: `custom_components/foxess_em/__init__.py:132-229`
- Create: `custom_components/foxess_em/enhanced/controller.py`
- Test: `tests/enhanced/test_setup_shadow_mode.py`

**Step 1: Write failing setup tests**

Use a minimal Home Assistant fixture/mocks to prove disabled entries do not instantiate enhanced services, enabled entries create only a read/diagnostic controller, legacy `ChargeService` remains the only registered write path, and unload removes enhanced listeners/state.

**Step 2: Run to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_setup_shadow_mode.py -q
```

Expected: FAIL.

**Step 3: Implement the narrow composition-root wiring**

Create an enhanced controller that receives data through existing read-only controllers/sensors or explicit adapters, publishes an in-memory shadow result, and registers no inverter services. Add it to `hass.data[DOMAIN][entry.entry_id]` under a separate key and clean it up on unload. Do not alter legacy callbacks except where a read-only listener is required.

**Step 4: Verify**

Run focused setup tests and the existing suite. Expected: PASS with old setup behavior preserved.

### Task 12: Add Home Assistant diagnostic sensors

**Objective:** Expose enhanced target, charge required, reserve, status, and legacy delta with useful attributes.

**Files:**
- Modify: `custom_components/foxess_em/sensor.py` or create `custom_components/foxess_em/enhanced/sensor.py` according to existing platform registration
- Modify: `custom_components/foxess_em/common/sensor.py` only if shared infrastructure is needed
- Test: `tests/enhanced/test_sensors.py`

**Step 1: Write failing entity tests**

Assert entity names/unique IDs are stable and namespaced, disabled mode does not expose misleading active values, enabled mode exposes all five required sensors, unavailable/fallback states are represented correctly, and attributes contain diagnostics without secrets or raw user data.

**Step 2: Run to verify failure**

Run:

```bash
python3.13 -m pytest tests/enhanced/test_sensors.py -q
```

Expected: FAIL.

**Step 3: Implement read-only entities**

Use the generic sensor infrastructure where it cleanly supports attributes; use dedicated entities if update callbacks/state translation require it. Ensure entities read controller state only and have no service/write methods.

**Step 4: Verify**

Run focused tests and an entity-registration test. Expected: PASS.

### Task 13: Document shadow mode, privacy, dashboard, and deferred work

**Objective:** Make local operation and data boundaries clear to users and maintainers.

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Create: `docs/enhanced-shadow-mode.md`
- Create: `docs/dashboard-enhanced-shadow.yaml`
- Modify: `.gitignore` (if Task 1 did not complete all guards)

**Step 1: Write documentation acceptance checklist**

Document installation/test commands, settings/defaults, sensor meanings, percentile/blend/fallback diagnostics, reserve formula and bounds, DST/local grouping, synthetic replay usage, privacy guarantees, local fixture location, and explicit non-goals (no live enhanced control, no inverter writes, no cloud publishing).

**Step 2: Add a dashboard example**

Use placeholder entity IDs only, clearly mark them as replacements, and include the five diagnostic sensors plus status/legacy delta.

**Step 3: Verify documentation and privacy**

Run:

```bash
python3.13 -m pytest tests/test_repository_safety.py -q
python3.13 -m compileall -q custom_components tests
```

Expected: PASS with no private data in committed files.

### Task 14: Run the complete local verification matrix

**Objective:** Prove the MVP meets formulas, compatibility, replay, no-write, and repository-safety acceptance criteria.

**Files:**
- No new files; fix only files named by failing tests.

**Step 1: Run focused enhanced tests**

```bash
python3.13 -m pytest tests/enhanced -q --no-cov
```

Expected: all enhanced tests pass.

**Step 2: Run the existing regression suite**

```bash
python3.13 -m pytest tests -q --no-cov
```

Expected: all existing and enhanced tests pass without requiring live HA/FoxESS/Solcast services.

**Step 3: Run coverage and lint-style checks used by the repository**

```bash
python3.13 -m pytest tests --cov=custom_components.foxess_em --cov-report=term-missing
python3.13 -m compileall -q custom_components tests
```

Expected: the repository's configured coverage threshold is met, or any pre-existing global-coverage limitation is recorded precisely; no new untested enhanced branches are accepted.

**Step 4: Verify the dependency boundary and working tree**

```bash
python3.13 -m pytest tests/enhanced/test_shadow.py tests/enhanced/test_setup_shadow_mode.py -q
python3.13 -m pytest tests/test_repository_safety.py -q
 git diff --check
 git status --short
```

Expected: no enhanced test imports a write service, no test performs inverter writes, no credentials/private exports are present, and only intended local MVP files are changed.

## Final acceptance criteria

- Existing `foxess_em` domain and legacy config entries still load unchanged.
- Enhanced settings default to disabled and can be configured without requiring migration of old entries.
- Forecasts preserve `pv_estimate` and optionally expose `pv_p10`/`pv_p90`; p10/p50/p90/blend selection has explicit fallback diagnostics.
- Load profiles support 7–30 days, all-days or weekday/weekend matching, interval percentile, and DST-safe local grouping.
- Adaptive reserve uses only recent positive synthetic/local forecast errors and is bounded.
- Pure planning, replay, and shadow comparison have no FoxService/Schedule dependency and perform no inverter writes.
- Seven-day synthetic replay is deterministic and compares legacy versus enhanced targets.
- HA diagnostics expose enhanced target, charge required, reserve, status, and legacy delta.
- Debug logging never emits complete config/options or credentials.
- Docs include dashboard example, privacy statement, local fixture guidance, gitignore/private-data guard, and deferred live-control/cloud-publishing work.
- No live enhanced control or cloud publishing is implemented in this MVP.
