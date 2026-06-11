# Lev1OutlierGenerator — design

**Date:** 2026-05-07
**Status:** Draft, ready for review
**Scope:** "Project B" first slice from the 2026-05-06 brainstorm — auto-flagging the lev1 cohort-QC findings into the existing exclusion registry. Out of scope: running the existing motion + behavioral generators on the rerun cohort, lev2 audit (separate brainstorm).

---

## Context

The lev1 audit (PR #4, merged 2026-05-07) added a cohort QC module (`neuro_workflow.qa.lev1_outliers`) that produces a per-(scan, contrast) review surface: `lev1_outliers.csv`, `lev1_flagged.tsv`, and a Jeanette-style PDF. Today, those outputs are reviewed manually; nothing flows back into the existing exclusion registry (`src/neuro_workflow/core/exclusions.py` + `src/neuro_workflow/exclusions/{base,motion,behavioral}.py`).

This spec adds a `Lev1OutlierGenerator` that converts cohort QC findings into per-scan exclusion entries that `compile_exclusions` already understands. The plumbing into lev1 (via `--exclusions-file <compiled>`) already works.

---

## Goals

1. Add `Lev1OutlierGenerator` implementing the existing `ExclusionGenerator` Protocol — slots into the registry without changes to `compile_exclusions` or its CLI.
2. Generator reads `lev1_outliers.csv` (the exhaustive cohort QC output) and applies three OR'd auto-exclude rules:
   - **Combined**: `vif >= combined_vif` AND `outlier_pct >= combined_outlier_pct`
   - **Strict VIF**: `vif >= strict_vif`
   - **Strict outliers**: `outlier_pct >= strict_outlier_pct`
   Defaults: `combined_vif=10`, `combined_outlier_pct=10`, `strict_vif=15`, `strict_outlier_pct=15`.
3. Per-scan aggregation: if any contrast on `(subject, session, task, run)` triggers any rule, emit one exclusion entry for that scan. The reason field captures every flagged contrast and every rule that fired.
4. CLI: `neuro-run exclusions generate lev1_outlier --dataset <ds> --lev1-outliers-csv <path> [thresholds]` produces `data/exclusions/sources/<ds>/lev1_outlier.json` ready for `neuro-run exclusions compile <ds>`.
5. Manual review escape valve preserved: `data/exclusions/<dataset>_overrides.json` `force-include` keeps an auto-flagged scan; `force-exclude` adds one that wasn't auto-flagged. No new override mechanism.
6. Tests cover all three rules independently, per-scan aggregation, threshold configurability, the NaN/empty-`outlier_pct` case (cohort-of-1 degeneracy), and end-to-end on the real discovery cohort QC output.

## Non-goals

- Running motion/behavioral generators on the rerun cohort (research-level threshold decisions; separate scope).
- Recomputing cohort QC inside the generator (read existing CSV; recomputing duplicates work).
- Changing the existing 50% high-exclusion threshold or the `_desc-highExclusion` filename tag (already exists; out of scope).
- Per-(scan, contrast) granularity (existing schema is per-scan; surgical exclusion is YAGNI until lev2 operates per-contrast).
- Lev2 wiring (separate audit + spec).

---

## Architecture

One new file, one new class, one CLI registration line. Reuses the existing registry, compile, and override mechanics.

```
src/neuro_workflow/exclusions/lev1_outlier.py        ← new
src/neuro_workflow/cli.py                            ← +1 import line
tests/exclusions/test_lev1_outlier.py                ← new
```

The generator is a `ExclusionGenerator` (Protocol from `exclusions/base.py`) with `name="lev1_outlier"`, a description string, and a `generate(dataset_name, dataset_config, args) -> list[dict]` method. `register_generator(Lev1OutlierGenerator())` runs at module import. `cli.py` imports the module so the registration fires.

CLI args added to the `exclusions generate lev1_outlier` subcommand:
- `--lev1-outliers-csv PATH` (required) — full path to cohort QC's `lev1_outliers.csv`.
- `--combined-vif` (default 10.0).
- `--combined-outlier-pct` (default 10.0).
- `--strict-vif` (default 15.0).
- `--strict-outlier-pct` (default 15.0).

Generator-specific arg wiring follows whatever existing pattern motion/behavioral use (verify at implementation time; if they hand-roll their args inline in `cmd_exclusions_generate`, do the same here).

---

## Data flow

```
[lev1 produces per-scan VIF csv + per-scan effect-size NIfTIs]
                        ↓
neuro_workflow.qa.lev1_outliers          (cohort QC, runs once on a cohort)
                        ↓
qa_lev1_<dataset>/lev1_outliers.csv      ← exhaustive (subject, session, run, task, contrast, vif, outlier_pct, ...)
                        ↓
neuro-run exclusions generate lev1_outlier \
    --dataset <ds> \
    --lev1-outliers-csv <path>/lev1_outliers.csv \
    [--combined-vif 10] [--combined-outlier-pct 10] \
    [--strict-vif 15] [--strict-outlier-pct 15]
                        ↓
data/exclusions/sources/<ds>/lev1_outlier.json   ← per-scan entries
                        ↓
neuro-run exclusions compile <ds>
                        ↓
~/.neuro_workflow/exclusions/<ds>/compiled_exclusions.json
                        ↓
lev1.run --exclusions-file <compiled>     ← honored on next lev1 run

[user override loop, optional, manual]
data/exclusions/<ds>_overrides.json:
  - {action: "force-include", ...}   ← keep an auto-flagged scan
  - {action: "force-exclude", ...}   ← exclude an unflagged scan
                        ↓ next compile picks these up
```

**Idempotency:** rerunning the generator with the same CSV and same thresholds produces identical output (sorted by subject/session/task/run, deterministic reason format).

**No coupling back to lev1 internals** — generator only depends on the CSV's column names (`subject, session, run, task, contrast, vif, outlier_pct, flagged_outliers, flagged_vif`).

---

## Output entry shape

One dict per flagged scan. Schema matches motion generator:

```python
{
    "subject": "sub-s03",
    "session": "ses-02",
    "task": "task-cuedTS",
    "run": "run-1",
    "source": "lev1_outlier",
    "action": "exclude",
    "reason": (
        "lev1_outlier: response_time vif=18.09 (strict_vif); "
        "cue_switch_cost vif=11.5,outlier=12.3% (combined)"
    ),
    "metrics": {
        "max_vif": 18.09,
        "max_outlier_pct": 12.3,
        "n_flagged_contrasts": 2,
        "rules_fired": ["combined", "strict_vif"],
    },
}
```

`task` is prefixed with `task-` to match existing motion entries; `run` is the bare digit (matches motion).

---

## Per-scan aggregation logic

```python
def _row_fires_any_rule(row, thresholds):
    vif = row.vif if row.vif is not None else 0.0
    pct = row.outlier_pct if row.outlier_pct is not None else 0.0
    rules = []
    if vif >= thresholds.combined_vif and pct >= thresholds.combined_outlier_pct:
        rules.append("combined")
    if vif >= thresholds.strict_vif:
        rules.append("strict_vif")
    if pct >= thresholds.strict_outlier_pct:
        rules.append("strict_outliers")
    return rules

# group rows of lev1_outliers.csv by (subject, session, task, run)
# for each group: collect the contrasts that fire any rule, build the entry, emit
```

NaN / empty `outlier_pct` is treated as 0.0 (cohort-of-1 / degenerate case where cohort QC couldn't compute it). Same for VIF.

---

## Tests

`tests/exclusions/test_lev1_outlier.py`:

1. **Each rule fires independently** — 4 rows with `(vif, outlier_pct)`: `(11, 11)` → combined; `(18, 2)` → strict_vif; `(4, 18)` → strict_outliers; `(8, 8)` → no rule. Assert exactly the first three produce exclusion entries.
2. **Per-scan aggregation** — two flagged contrasts on the same `(subject, session, task, run)`: one entry emitted, both contrasts in `reason`, `metrics.n_flagged_contrasts == 2`, `rules_fired` includes both rules.
3. **Threshold configurability** — same input, with `combined_vif=20`: assert different (smaller) output count.
4. **Reason format determinism** — assert substring contents include the contrast name, the triggering numeric values, and the rule name.
5. **Empty CSV → `[]`.**
6. **Missing CSV → `FileNotFoundError`** with the offending path in the message.
7. **NaN / empty `outlier_pct` handling** — row with `outlier_pct=""` and `vif=4` does not fire any rule.
8. **Compile integration** — write generator output to a fake `sources/<ds>/lev1_outlier.json`; call `compile_exclusions(ds)`; assert the merged result contains the entries.
9. **End-to-end on real data** (skipped if `/scratch/users/logben/qa_lev1_discovery/lev1_outliers.csv` not present) — invoke generator on the real cohort QC output, assert a non-empty list, all entries `source="lev1_outlier"` and `action="exclude"`, required keys all present.

---

## Code-style guardrails

- Single file `src/neuro_workflow/exclusions/lev1_outlier.py`, ≤150 lines, plain functions + frozen dataclass for the row + thresholds schemas.
- One test file, `tmp_path` only, no fixture factories.
- No silent fallbacks: missing CSV raises, malformed CSV row raises with line context.
- No retroactive abstractions ("we might add more rule types later"). YAGNI.
- Generator is registered once at module import; no factory/Builder patterns.

---

## Sanity context for discovery (N=5)

Discovery cohort QC produced max `outlier_pct` ≈ 3.5% (cohort QC math: at `n_std=3` and population SD, max possible |z| at small N is `sqrt(N−1) ≈ 2.0` for N=5, so outliers are bounded). At full N=46, outlier_pct can grow to give meaningful signal.

Implications:
- On discovery alone, neither the combined rule nor the strict-outliers rule will fire. Only the strict-VIF rule (`vif >= 15`) will hit. Generator will produce some entries, just from VIF.
- After the validation cohort lev1 + cohort QC re-runs at N=46, all three rules become discriminating. The generator code is unchanged at that point.

This is fine. The generator's job is to apply rules; whether the rules fire depends on the data. No degenerate-N guard needed.

---

## Open questions / decisions deferred to implementation

1. **Generator-specific CLI arg wiring**: the existing motion/behavioral generators may register their args inline in `cmd_exclusions_generate` or via a hook. Implementer reads `cli.py` and matches the existing pattern. No new mechanism.
2. **`tests/exclusions/` directory**: doesn't exist today. Implementer creates it with an `__init__.py` if needed.
3. **Skip-marker for the end-to-end test**: prefer `pytest.skip(reason)` based on path existence rather than environment markers, matching what other lev1 tests do (`tests/analysis/test_lev1_data_chain.py`).
