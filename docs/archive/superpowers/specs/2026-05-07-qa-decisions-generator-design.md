# QA Decisions Generator — design

**Date:** 2026-05-07
**Status:** Draft, ready for review
**Scope:** Project C, slice C1 — plumb `qa_report` decisions (TSV) into the existing exclusion registry. Out of scope: C0 (audit trail), C3 (lev2 `--exclusions-file` symmetry), end-to-end exclusion-flow doc.

---

## Context

The `qa_report` script produces an HTML cohort QA review and consumes a sidecar decisions TSV (`subject|session|task|run|action|reason`) where the user records per-scan or per-subject choices. The decisions are rendered into the HTML report at `src/neuro_workflow/qa/report.py` but never persisted to the exclusion registry. Today, a "pass/exclude/review" decision in the qa_report UI is invisible to `compile_exclusions` and to lev1.

The motion generator runs an *independent* motion check on the same fmriprep confound files that drive qa_report's motion column. The two can disagree: a scan can be flagged "exclude" by the user in qa_report yet pass the motion generator's thresholds (or vice versa). The user's manual decision is the more authoritative signal but doesn't propagate.

This spec adds a `QADecisionsGenerator` that reads the decisions TSV and emits per-scan exclusion entries that `compile_exclusions` already understands. Single source of truth for exclusion intent.

---

## Goals

1. New `QADecisionsGenerator` implementing the existing `ExclusionGenerator` Protocol — slots into the registry without changes to `compile_exclusions` or its CLI.
2. Reuses `qa.decisions.load_decisions` (existing) to parse the TSV. Generator only does the conversion to exclusion entries.
3. Handles both decision granularities the loader supports:
   - **Scan-level** (`ScanKey` key) → one exclusion entry, BIDS-prefixed.
   - **Subject-level** (bare subject string key) → expanded to per-scan entries via `bids_dir.glob('sub-<id>/ses-*/func/*_bold.nii.gz')`.
4. Only `action="exclude"` rows produce entries. `action="pass"` and `action="review"` are counted in a stdout summary and skipped.
5. CLI: `neuro-run exclusions generate qa_decisions <ds> --decisions-tsv <path>` produces `data/exclusions/sources/<ds>/qa_decisions.json` ready for `neuro-run exclusions compile <ds>`.
6. Subject filter: when `dataset_config["subjects_file"]` is present, drop rows whose subject isn't in the dataset's roster (matches L1OG behavior). Filter applies *before* BIDS glob so subject-level rows for non-member subjects don't trigger a glob.
7. Tests cover all three decision actions, scan-level vs subject-level, missing/empty/invalid TSV, the subject-level-no-BIDS-match case, and the dataset filter.

## Non-goals

- Modifying `qa_report` itself or its UI flow (this is a downstream consumer of the existing TSV).
- Adding a `review`-action exclusion entry kind (the schema only supports `exclude` today; `review` rows are user-pending and intentionally don't propagate).
- A canonical default path for the decisions TSV (YAGNI; researchers always know where their TSV is and pass it explicitly).
- Wildcard `session="*"` entries (rejected during brainstorming — would force compile_exclusions changes).

---

## Architecture

One new file, one new class, one CLI registration line, plus a small extraction of the shared dataset-filter helper.

```
src/neuro_workflow/exclusions/qa_decisions.py        ← new
src/neuro_workflow/exclusions/base.py                ← extract _load_dataset_subjects
src/neuro_workflow/exclusions/lev1_outlier.py        ← consume the extracted helper
src/neuro_workflow/cli.py                            ← +1 import line
tests/exclusions/test_qa_decisions.py                ← new
```

The generator is a `ExclusionGenerator` (Protocol from `exclusions/base.py`) with `name="qa_decisions"`, a description, and a `generate(dataset_name, dataset_config, args) -> list[dict]` method. `register_generator(QADecisionsGenerator())` runs at module import. `cli.py` imports the module so the registration fires.

Why extract `_load_dataset_subjects`: it lives in `lev1_outlier.py` today and would be duplicated in `qa_decisions.py` otherwise. Promotion to `exclusions/base.py` is small (~25 lines), keeps a single source of truth for the subject-filter rules, and makes future generators that need the same filter trivial. Both consumers follow the same `Path.is_absolute()` / cwd-relative rules.

CLI args added to the `exclusions generate qa_decisions` subcommand:
- `--decisions-tsv PATH` — required at runtime (not argparse-required, since the shared subparser would propagate that to other generators — same hot-fix lesson from PR #6).

---

## Data flow

```
[user runs qa_report, annotates decisions in <ds>.tsv]
                        ↓
neuro-run exclusions generate qa_decisions <ds> \
    --decisions-tsv <path>/qa_decisions_<ds>.tsv
                        ↓
QADecisionsGenerator.generate(ds, cfg, args)
   ├─ if not args.decisions_tsv.is_file(): raise FileNotFoundError(path-in-message)
   ├─ decisions = qa.decisions.load_decisions(args.decisions_tsv)
   ├─ subjects = base._load_dataset_subjects(cfg)   # may be None
   ├─ for key, decision in decisions.items():
   │      counts[decision.action] += 1
   │      if decision.action != "exclude": continue
   │      if isinstance(key, ScanKey):
   │          if subjects and _norm_sub(key.subject) not in subjects: continue
   │          emit one entry from key + reason
   │      else:                                       # str: subject-level
   │          sub_norm = _norm_sub(key)
   │          if subjects and sub_norm not in subjects: continue
   │          for bold in (cfg["bids_dir"] / sub_norm).glob('ses-*/func/*_bold.nii.gz'):
   │              emit one entry parsed from bold filename + (subject-level) reason
   ├─ entries.sort(key=lambda e: (e["subject"], e["session"], e["task"], e["run"]))
   ├─ print summary: f"qa_decisions: {n_excluded} excluded ({n_scan} scan-level, {n_expanded} expanded from {n_subj_rows} subject-level), {n_review} review-skipped, {n_pass} pass-skipped"
   └─ return entries
                        ↓
data/exclusions/sources/<ds>/qa_decisions.json   ← per-scan entries
                        ↓
neuro-run exclusions compile <ds>
                        ↓
~/.neuro_workflow/exclusions/<ds>/compiled_exclusions.json
                        ↓
lev1.run --exclusions-file <compiled>     ← honored on next lev1 run
```

**Idempotency:** rerunning with the same TSV produces identical, sorted output.

**Coupling:** depends on `qa.decisions.load_decisions` (existing), `dataset_config["bids_dir"]` (existing), and the soon-shared `_load_dataset_subjects` helper. No new types.

---

## Output entry shape

Scan-level decision:

```python
{
    "subject": "sub-s03",
    "session": "ses-02",
    "task": "task-cuedTS",
    "run": "run-1",
    "source": "qa_decisions",
    "action": "exclude",
    "reason": "qa_decisions: noisy task data (scan-level)",
}
```

Subject-level decision (one entry per BOLD file matched):

```python
{
    "subject": "sub-s03",
    "session": "ses-02",
    "task": "task-cuedTS",
    "run": "run-1",
    "source": "qa_decisions",
    "action": "exclude",
    "reason": "qa_decisions: dropped from cohort (subject-level)",
}
```

Granularity is encoded in the reason string only — no `metrics` dict needed. Schema matches motion / behavioral / lev1_outlier.

---

## BIDS prefix normalization

`qa.decisions.load_decisions` preserves whatever's in the TSV (the loader doesn't normalize). The qa_report UI today writes BIDS-prefixed values (`sub-s03`, `ses-02`, `task-cuedTS`, `run-1`). The generator handles both prefixed and unprefixed forms by normalizing on output:

- `subject`: `sub-{id}` (strip then re-add `sub-`).
- `session`: `ses-{id}` if not already prefixed.
- `task`: `task-{name}` if not already prefixed.
- `run`: `run-{n}` if not already prefixed.

The subject-filter comparison normalizes both sides before checking.

---

## Stdout summary

After generation, one line of stdout:

```
qa_decisions: 7 excluded (5 scan-level, 2 expanded from 1 subject-level), 3 review-skipped, 12 pass-skipped
```

Researcher reads this to know what flowed through and what was held back.

---

## Error handling + edge cases

- **Missing TSV** → `FileNotFoundError` with the path in the message. The generator checks `path.is_file()` before delegating to `load_decisions` (whose lenient `{}` return is preserved for other callers).
- **Empty TSV (header only)** → `[]`. Summary prints `qa_decisions: 0 excluded ...`.
- **Invalid `action` value** (e.g., `"maybe"`) → `load_decisions` raises `ValueError` with the offending value + path; the generator lets it propagate.
- **Subject-level row for a non-existent subject in BIDS** (typo, or subject already bidsignored upstream) → `bids_dir / "sub-<id>"` either doesn't exist or has zero `_bold.nii.gz` files; expansion emits 0 entries for that subject. Summary still records the row was processed: `expanded from 1 subject-level` even when expansion is empty (or refine to `expanded from 1 subject-level (1 had 0 BOLD matches)` if simple to do).
- **Subject filter drops subject-level row before glob**: filter applies before BIDS I/O, saving filesystem reads.
- **Conflicting decisions for the same scan**: `load_decisions` returns a dict; the last row wins (dict overwrite). Document: one row per scan; resolved decisions win.
- **Subject in dataset roster but its sub-* dir doesn't exist** (e.g., dataset_config points at a stale BIDS dir): `bids_dir / "sub-<id>"` doesn't exist; glob returns []. Empty expansion. No exception.
- **Empty BIDS dir entirely**: same as above, generator returns []. No exception.

---

## Tests

`tests/exclusions/test_qa_decisions.py` (mirrors L1OG style):

1. `test_qa_decisions_generator_importable` — smoke.
2. `test_scan_level_exclude_emits_one_entry` — one `action=exclude` row → one entry with all BIDS prefixes.
3. `test_subject_level_exclude_expands_via_bids_glob` — fake BIDS tree with 3 BOLD files for `sub-s03`, TSV row `s03 - - - exclude noisy` → 3 entries, all `sub-s03`, all reason ending `(subject-level)`.
4. `test_subject_level_with_no_bids_files_emits_zero` — subject-level row for a sub with no BIDS scans → 0 entries.
5. `test_pass_and_review_rows_skipped` — mixed actions; only `exclude` produces entries; capsys confirms summary line shows `pass-skipped` and `review-skipped` counts.
6. `test_invalid_action_propagates_value_error` — TSV with `action=maybe` → `ValueError`.
7. `test_missing_tsv_raises_file_not_found_error` — bogus path → `FileNotFoundError` with path in message.
8. `test_empty_tsv_returns_empty_list` — header-only TSV → `[]`.
9. `test_subject_filter_drops_non_member_rows` — scan-level rows for in-dataset and out-of-dataset subjects; subjects_file restricts roster → only in-dataset entries remain.
10. `test_subject_filter_drops_subject_level_before_glob` — subject-level row for non-member subject; subjects_file restricts → 0 entries, BIDS glob never invoked (verified via no-BIDS tmp_path that would otherwise have caused 0 matches anyway, but stronger: monkey-patch `Path.glob` to record calls and assert none for the non-member subject).
11. `test_compile_pipeline_integration` — TDD-style end-to-end: redirect `core_excl.EXCLUSIONS_DIR` to tmp, generate entries, `save_source_entries` + `compile_exclusions` → compiled list contains the entries with correct source.

After the `_load_dataset_subjects` extraction (Component table above), the existing L1OG dataset-filter tests must continue to pass without code changes. That's the cross-check that the helper extraction didn't regress.

---

## Code-style guardrails

- Single file `src/neuro_workflow/exclusions/qa_decisions.py`, ≤180 lines (allowing room for the BIDS-glob expansion helper).
- One test file, `tmp_path` only, no fixture factories.
- Follow L1OG's structure: dataclass for any threshold-like config (none here, since there are no thresholds), private module-level helpers, single class at the bottom, `register_generator(...)` at module exit.
- `_load_dataset_subjects` lives in `exclusions/base.py` after the extraction; the L1OG file imports it from there. Same name. Same signature. Same behavior.
- No retroactive abstractions. No "decision adapter registry" or "row visitor" patterns.

---

## Open questions / decisions deferred to implementation

1. **Whether to enrich the "expanded from N subject-level" summary** with a sub-count of how many had zero BIDS matches. Implementer makes the call; if it's two extra lines, do it. If the bookkeeping spreads everywhere, skip.
2. **Whether to print a separate WARNING when a subject-level row produces 0 BIDS matches** vs. just including it silently in the summary. Implementer's call; either works. The summary line is the audit trail either way.
3. **CLI flag name**: spec uses `--decisions-tsv`. If the existing motion generator's pattern of un-prefixed paths is preferred (e.g., `--qa-decisions-tsv` to avoid collision with a future generator named just `decisions`), the implementer can rename. Both are clear.
