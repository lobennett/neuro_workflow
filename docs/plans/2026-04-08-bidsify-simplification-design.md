# Bidsify Pipeline Simplification Design

**Date:** 2026-04-08
**Approach:** Surgical removal (Approach A)

## Goal

Simplify the bidsify pipeline to a focused Flywheel-to-BIDS converter: pull all data, name correctly with session label corrections, trim 7 BOLD dummy volumes, log timestamps. Remove all .bidsignore automation, physio trimming, behavioral trimming, duplicate filtering, parallel processing, and retry logic.

## Config Consolidation

**New file:** `config/pipeline_config.json`

Replaces:
- `src/neuro_workflow/bidsify/reconciliation_config.json`
- `config/behavioral_samples.json`
- `config/reconciliation_config.json` (deprecated)

Structure:
```json
{
  "flywheel": {
    "project": "r01network",
    "subject_aliases": { "s19-2": "s19", "s29-2": "s29", "s43-2": "s43", "ex26207": "s297" },
    "skip_subjects": ["n01"],
    "session_overrides": {
      "s03": {
        "22752": { "reassign_to": "s10", "reason": "..." },
        "25210": { "exclude": true, "reason": "..." }
      },
      "s29": {
        "22424": { "exclude": true, "reason": "..." }
      }
    }
  },
  "samples": {
    "discovery": ["s03", "s10", "s19", "s29", "s43"],
    "validation": ["s76", "s247", ... 41 non-excluded ...],
    "excluded": { "s214": "reason", "s222": "reason", ... 11 total }
  },
  "notes": {
    "discovery": ["s03/session 22752 was mislabeled...", ...],
    "validation": ["ex26207 is an alias for s297...", ...]
  }
}
```

`excluded` is a first-class sample name. `neuro-run submit bidsify excluded` works like discovery/validation.

Behavioral annotations (irreconcilable scans, trimming, discrepancies) are NOT in this config. They belong to a later behavioral phase, with `docs/SCAN-NOTES.md` as ground truth.

`config/behavioral_session_mapping.json` stays separate (generated, large).

## Code Changes to run.py

### Remove
- `physio_trimming` import
- `bidsignore_entries` parameter, initialization, aggregation, and file writing
- `_latest_anat_acq` pre-computation and anatomical duplicate filtering
- `dwi_scans_by_key` duplicate tracking
- MPRAGEPromo .bidsignore logic (MPRAGEPromo still skipped via SKIP_ACQUISITIONS in config.py)
- Physio trimming block (trim_physio_data calls)
- `_safe_patch_sidecar()` retry wrapper (replace with direct `patch_sidecar()` calls)
- `ThreadPoolExecutor` parallel processing (replace with sequential loop)

### Keep
- BOLD 7-volume trimming (inline nibabel trim)
- Physio download + BIDS conversion (no trimming)
- Fieldmap and B0Field patching
- Reconciliation JSON output
- Dataset description and README writing

### Add
- Run counters per modality: `anat_run_counter[(suffix, acq)]`, `dwi_run_counter[(dir, acq)]` — duplicates get run-01, run-02, etc.
- Timestamp collection per session
- `sourcedata/session_timestamps.tsv` output with columns: subject, bids_session, flywheel_session_label, flywheel_timestamp
- `excluded` as valid sample name (subject list from dict keys)
- Dataset name mapping: `"excluded": "Network Excluded Sample"`

### Net effect
~607 lines -> ~400 lines

## config.py Changes

- Rename `load_reconciliation_config()` to `load_pipeline_config()`
- Read from `config/pipeline_config.json` (project root) instead of bidsify subpackage

## Files to Delete

From `src/neuro_workflow/bidsify/`:
- `physio_trimming.py` (151 lines)
- `trimming_orchestrator.py` (163 lines)
- `exclusions_manifest.py` (118 lines)
- `behavioral_trimming.py` (58 lines)
- `bold_trimming.py` (128 lines)
- `integration.py` (1 line)
- `reconciliation_config.json` (226 lines)

From `config/`:
- `reconciliation_config.json` (deprecated)
- `behavioral_samples.json` (absorbed into pipeline_config.json)

## Files to Archive Locally

Moved to `~/.neuro_workflow_archive/` (out of git):
- `src/neuro_workflow/bids_validation/` (BoldAnalyzer code)
- `tests/bids_validation/` (3 test files, ~1000 lines)
- `config/behavioral_discrepancy_mapping.json` (re-verify later against SCAN-NOTES.md)

## Test Changes

### Delete
- `tests/bidsify/test_physio_trimming.py`
- `tests/bidsify/test_behavioral_trimming.py`
- `tests/bidsify/test_trimming_orchestrator.py`
- `tests/bidsify/test_exclusions_manifest.py`
- `tests/bidsify/test_bold_trimming.py`

### Update
- `test_config.py` — test `load_pipeline_config()` from `config/pipeline_config.json`
- `test_run.py` — remove bidsignore assertions, test sequential processing, test timestamp TSV

### New (TDD)
- Test run-number incrementing for duplicate anatomicals/DWI within a session
- Test `session_timestamps.tsv` output format and content
- Test that no `.bidsignore` file is written
- Test `excluded` sample name resolution (dict keys -> subject list)

### Keep unchanged
- `test_flywheel_query.py`, `test_physio.py`, `test_physio_query.py`, `test_file_selector.py`, `test_bids_writer.py`, `test_cli_integration.py`

## Documentation Updates

### Remove
- `STATUS-PIPELINE-SIMPLIFICATION.md` (root) — obsolete

### Update
- `CLAUDE.md` — rewrite bidsify sections for simplified pipeline
- `README.md` — update pipeline description
- `docs/WORKFLOW.md` — rewrite Phase 1, remove/defer Phase 3
- `docs/ARCHITECTURE.md` — update module reference
- `docs/BIDS-ARCHITECTURE.md` — remove .bidsignore references

### Keep as-is
- `docs/SCAN-NOTES.md` — ground truth for behavioral phase
- `docs/BEHAVIORAL_BOLD_DISCREPANCIES.md` — useful later
- `docs/BEHAVIORAL_INTEGRATION_COMPLETION_2026-03-19.md` — historical
- `VISUAL_GUIDE.md` — unrelated

## Pipeline Execution

After code changes committed:

1. Rebuild container: `bash neuro_workflow.sh`
2. Delete existing BIDS dirs on scratch
3. Run:
   ```bash
   neuro-run submit bidsify discovery  --output-dir /scratch/users/logben/discovery_bids --overwrite
   neuro-run submit bidsify validation --output-dir /scratch/users/logben/validation_bids --overwrite
   neuro-run submit bidsify excluded   --output-dir /scratch/users/logben/excluded_bids --overwrite
   ```
4. Verify: session_timestamps.tsv exists, no .bidsignore, duplicate scans have run numbering
