# Claude Code Guidelines for neuro_workflow

## Python Execution
**CRITICAL: Always use `uv run python` when executing Python scripts in this project.**

❌ WRONG:
```bash
python src/neuro_workflow/bidsify/run.py
python -m py_compile src/neuro_workflow/bidsify/run.py
```

✅ CORRECT:
```bash
uv run python src/neuro_workflow/bidsify/run.py
uv run python -m py_compile src/neuro_workflow/bidsify/run.py
```

**Why:** This project uses `uv` for dependency management. Using system python will fail to find the project's dependencies and installed modules.

## Project Structure

### Key Directories
- `src/neuro_workflow/` - Main package source code
- `scripts/` - Standalone scripts (bidsify, behavioral migration, etc.)
- `tests/` - Test suite
- `docs/` - Documentation
- `config/` - Configuration files

### Critical Files
- `src/neuro_workflow/bidsify/run.py` - Main Flywheel → BIDS conversion orchestrator
- `src/neuro_workflow/bidsify/bids_writer.py` - BIDS file writing utilities
- `src/neuro_workflow/cli.py` - CLI entry point
- `config/pipeline_config.json` - Single source of truth for pipeline configuration (subject lists, session mappings, scan notes)
- `pyproject.toml` - Project configuration and dependencies

## Bidsify Pipeline (April 8, 2026)

### Architecture

The bidsify pipeline is **sequential** (no parallel processing, no ThreadPoolExecutor). It processes one subject/session/scan at a time via `src/neuro_workflow/bidsify/run.py`.

### Configuration

- **Single source of truth:** `config/pipeline_config.json`
- Loaded via `load_pipeline_config()` (replaces the old `load_reconciliation_config()`)
- Contains subject lists, session mappings, scan notes, irreconcilable scans, and trim metadata
- **Deprecated:** `src/neuro_workflow/bidsify/reconciliation_config.json` and `config/reconciliation_config.json` (legacy, do not use)

### What Bidsify Does

1. **Downloads NIfTI and sidecar JSON** from Flywheel for each scan
2. **Does NOT trim BOLD volumes** — trimming is done post-bidsify via `scripts/trim_bold.py`
   - Run `uv run python scripts/trim_bold.py <bids_dir>` after bidsify completes
   - After trimming, use `--dummy-scans 0` in fMRIPrep (volumes already removed)
   - If trim_bold.py has NOT been run, use `--dummy-scans 7` in fMRIPrep instead
3. **Downloads and converts physiological data** to BIDS format (cardiac + respiratory)
   - Physio is NOT trimmed during bidsify; trimming deferred to preprocessing
4. **Handles duplicate scans** with run numbering (run-01, run-02) instead of filtering or .bidsignore
5. **Logs session timestamps** to `sourcedata/session_timestamps.tsv` per BIDS dataset
6. **No .bidsignore generation** -- curation of ignored files is done manually after bidsify

### Deleted Modules

The following modules were removed as part of the April 2026 simplification:
- `physio_trimming` -- physio no longer trimmed during bidsify
- `trimming_orchestrator` -- no orchestrated multi-step trimming
- `exclusions_manifest` -- no automatic exclusion manifest generation
- `behavioral_trimming` -- behavioral trimming moved out of bidsify
- `bold_trimming` -- dummy volume trimming is now done via `scripts/trim_bold.py`
- `integration` -- removed
- `bids_validation` -- validation done externally via bids-validator

### Post-Bidsify Scripts

Three standalone scripts in `scripts/` for post-processing:

1. **`scripts/trim_bold.py`** -- Trim 7 dummy volumes from all BOLD NIfTIs in a BIDS directory. Updates sidecar JSONs with `NumberOfVolumesDiscardedByUser: 7`. Idempotent (safe to run twice).
2. **`scripts/reconcile_sessions.py`** -- Read-only analysis matching BIDS functional scans to raw behavioral CSVs. Produces a TSV manifest for human (or Claude-assisted) review.
3. **`scripts/migrate_behavioral.py`** -- Consumes the reviewed TSV manifest and copies behavioral CSVs to BIDS sourcedata with BIDS naming.

Workflow: `reconcile_sessions.py` -> review manifest -> `migrate_behavioral.py` -> `.bidsignore` for excluded scans.

### Three Samples

The pipeline operates on three named samples:
- **discovery** -- 5 subjects for initial pipeline development and testing
- **validation** -- 41 non-excluded subjects for full validation
- **excluded** -- 11 excluded subjects (processed separately for archival)

### Example Workflow

```bash
# Run discovery BIDS generation
uv run neuro-run submit bidsify discovery \
  --output-dir /scratch/users/logben/discovery_bids \
  --overwrite

# Run BIDS validator after bidsify completes
bids-validator /scratch/users/logben/discovery_bids

# Trim 7 dummy volumes (run once after bidsify, idempotent)
uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids

# Preprocessing note: Use fMRIPrep with --dummy-scans 0 (volumes already trimmed)
fmriprep --dummy-scans 0 /scratch/users/logben/discovery_bids /derivatives --fs-license /path/to/license
```

## Running Bidsify

### RECOMMENDED: Submit via Container + SLURM

Use `uv run neuro-run submit bidsify` to automatically generate an SBATCH script and submit via Singularity container. Subject lists are read from `config/pipeline_config.json` -- no need to pass `--subjects` on the command line.

```bash
# Discovery sample (5 subjects)
uv run neuro-run submit bidsify discovery \
  --output-dir /scratch/users/logben/discovery_bids \
  --overwrite

# Validation sample (41 non-excluded subjects)
uv run neuro-run submit bidsify validation \
  --output-dir /scratch/users/logben/validation_bids \
  --overwrite

# Excluded sample (11 excluded subjects)
uv run neuro-run submit bidsify excluded \
  --output-dir /scratch/users/logben/excluded_bids \
  --overwrite
```

**What happens:**
- Generates SBATCH script with container invocation
- Uses Singularity container at `/home/groups/russpold/singularity_images/neuro_workflow.sif`
- Submits to SLURM `russpold` partition
- Logs written to: `<output-dir>/sourcedata/logs/`

**Monitor jobs:**
```bash
squeue -u $USER | grep bidsify
tail -f /scratch/users/logben/discovery_bids/sourcedata/logs/bidsify_discovery-*.out
```

### Local Execution (Debugging Only)

For local testing without container/SLURM:

```bash
uv run python -m neuro_workflow.cli bidsify <sample> \
    --output-dir <bids_output> \
    [--subjects <list>] \
    [-v]
```

**Note:** This requires Flywheel API access and may hang in some environments. Use container approach for production.

## Testing Changes
```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/ -v
uv run pytest tests/bids_validation/ -v  # Specific test suite
```

## Common Issues and Solutions

### "ModuleNotFoundError: No module named 'neuro_workflow'"
**Solution:** Use `uv run python` instead of system python

### Missing physio JSON sidecars
**Cause:** gephysio analysis processing failures (now caught and logged)

**Solution:** Check reconciliation.json for warnings about failed physio processing

## SLURM/Singularity Notes

### Running bids-validator via SLURM
```bash
sbatch /tmp/run_validators.sbatch
```

### Singularity Images
- BIDS Validator: `/home/groups/russpold/singularity_images/bids-validator_1.14.6.simg`
- neuro_workflow: `/home/groups/russpold/singularity_images/neuro_workflow.sif` (rebuild after code changes)

### Rebuilding Container After Code Changes
```bash
sbatch --wrap="apptainer build --fakeroot --force /home/groups/russpold/singularity_images/neuro_workflow.sif /home/users/logben/neuro_workflow/neuro_workflow.def" \
    --partition=russpold --mem=8G --time=00:30:00
```

## Important: Data Organization

### BIDS Output Structure
```
/scratch/users/logben/discovery_bids/
/scratch/users/logben/validation_bids/
/scratch/users/logben/excluded_bids/
```

Each contains:
- `sourcedata/reconciliation.json` - Subject session mapping and warnings
- `sourcedata/bidsify_log.json` - Download logs
- `sourcedata/session_timestamps.tsv` - Session-level timestamps for audit/reproducibility

### Behavioral Data Locations
- In-scanner: `/oak/.../sourcedata/behavioral_data/`
- Out-of-scanner: `/oak/.../sourcedata/out_scanner_behavior/`
- Survey/Demographics: `/oak/.../sourcedata/survey_data/`
- mTurk: `/oak/.../mTurk/`
- Excluded subjects: `/oak/.../excluded_sourcedata/`

## Git Commit Pattern
When completing a phase:
```bash
git add <files>
git commit -m "feat|fix|refactor: <description>

<detailed explanation if needed>

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

## Last Updated
2026-04-08 - Simplified bidsify pipeline (sequential processing, config consolidation, no .bidsignore generation)


## Codebase Cleanup (March 17, 2026)

### Archive Organization
All legacy documents (30+ design iterations, audit reports, validator outputs) have been archived to `docs/archived/` with subdirectories:
- `design-iterations/` - Historical planning documents
- `audit-reports/` - Resolution reports and status updates
- `validator-outputs/` - BIDS validator output files

See `docs/archived/README.md` for archive index and guidance on when to reference archived docs.

### Current Authoritative Documents
The workflow is now documented in a small set of authoritative references:
1. **`docs/WORKFLOW.md`** - Single source of truth for complete Flywheel→BIDS→Behavioral→Events→Preprocessing pipeline
2. **`docs/ARCHITECTURE.md`** - Package structure, module reference, data flows, architectural decisions
3. **`docs/CLAUDE.md`** (this file) - Project conventions and guidelines
4. **`docs/SCAN-NOTES.md`** - Active scan status and special handling notes

### Logs Organization
Logs have been moved to `logs/` directory with `.gitignore` to prevent bloat:
- `logs/bidsify_logs/` - Bidsify execution logs
- `logs/build_logs/` - Container build logs
- `logs/validator_logs/` - BIDS validator outputs

### Key Principles After Cleanup
- **No hardcoded lists:** All subject lists, aliases, thresholds in JSON config files
- **Reproducibility:** Same config → same results, verifiable in git
- **Simplicity:** Follow WORKFLOW.md for entire pipeline; refer to ARCHITECTURE.md only when understanding internals
- **Audit trail:** All decisions encoded in JSON config files

### April 2026 Simplification
Further cleanup removed unused modules (physio_trimming, trimming_orchestrator, exclusions_manifest, behavioral_trimming, bold_trimming, integration, bids_validation). Pipeline configuration consolidated into `config/pipeline_config.json`. The bidsify pipeline is now fully sequential with no parallel processing. See "Bidsify Pipeline (April 8, 2026)" section above for details.

**Last updated:** 2026-04-08
