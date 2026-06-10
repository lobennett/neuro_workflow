# Claude Code Guidelines for neuro_workflow

## Python Execution
**CRITICAL: Always use `uv run python` when executing Python scripts in this project.**

```bash
# WRONG
python scripts/trim_bold.py /scratch/users/logben/discovery_bids

# CORRECT
uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids
```

**Why:** This project uses `uv` for dependency management. Using system python will fail to find dependencies.

## Project Structure

### Key Directories
- `src/neuro_workflow/` - Main package (bidsify pipeline, events, CLI, analysis, QA)
- `scripts/` - Standalone post-bidsify scripts
- `tests/` - Test suite
- `docs/` - Documentation (6 authoritative files)
- `config/` - Configuration, thresholds, and reviewed manifests

### Authoritative Documentation
1. **`docs/WORKFLOW.md`** - Reproducible pipeline: Flywheel to lev2 (Steps 1-14)
2. **`docs/EXCLUSIONS.md`** - Every .bidsignore entry with reason and cross-references
3. **`docs/SCAN-NOTES.md`** - Raw data collection notes per subject
4. **`docs/ARCHITECTURE.md`** - Package structure and module reference
5. **`docs/PROVENANCE.md`** - Run-manifest schema, dataset_description, clean-tree policy
6. **`docs/CONFIG.md`** - thresholds.yaml and battery.yaml schema and usage

### Scripts
- **`scripts/trim_bold.py`** -- Trim 7 dummy volumes from BOLD NIfTIs. Idempotent (checks sidecar for `NumberOfVolumesDiscardedByUser`). Atomic writes (temp file + rename). Skips corrupt files.
- **`scripts/reconcile_sessions.py`** -- Read-only: match BIDS functional scans to raw behavioral CSVs. Produces TSV manifest with cross-session context and SCAN-NOTES annotations.
- **`scripts/migrate_behavioral.py`** -- Consumes reviewed manifest, copies behavioral CSVs to BIDS sourcedata with BIDS naming. Supports `dest_run` for multi-run cases.
- **`scripts/check_tr.sh`** -- Compare each scan's TR count against the expected (mode) for its task. Flags deviations.

### Config
- `config/pipeline_config.json` - Subject lists, session overrides, Flywheel aliases
- `config/thresholds.yaml` - Study-level QC/motion/VIF thresholds (loaded by `core/thresholds.py`)
- `config/manifests/reconciliation_discovery.tsv` - Reviewed behavioral-BOLD manifest (discovery)
- `config/manifests/reconciliation_validation.tsv` - Reviewed behavioral-BOLD manifest (validation)

### Forked-out repos
MSHBM, prevalence analysis, parcellation reliability, and XCP-D are NOT in this repo. They live in the separate `network_analysis` repository (`github.com/lobennett/network_analysis`).

## Pipeline Overview

See `docs/WORKFLOW.md` for exact commands. Summary:

```bash
# 1. Pull from Flywheel
uv run neuro-run submit bidsify discovery --output-dir /scratch/users/logben/discovery_bids --overwrite

# 2. Trim 7 dummy BOLD volumes (idempotent)
uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids

# 3. Reconcile behavioral data (read-only, produces TSV manifest)
uv run python scripts/reconcile_sessions.py \
  --raw-dir /oak/.../behavioral_data/raw_cleaned \
  --bids-dir /scratch/users/logben/discovery_bids \
  --scan-notes docs/SCAN-NOTES.md \
  --output config/manifests/reconciliation_discovery.tsv

# 4. Review manifest (resolve pending rows)
# 5. Update .bidsignore (document in docs/EXCLUSIONS.md)
#    Generate: uv run neuro-run exclusions render-bidsignore discovery --output <bids_dir>/.bidsignore

# 6. Migrate behavioral data
uv run python scripts/migrate_behavioral.py \
  --manifest config/manifests/reconciliation_discovery.tsv \
  --raw-dir /oak/.../behavioral_data/raw_cleaned \
  --output-dir /oak/.../sourcedata \
  --sample discovery --strict

# 7. Validate
# 8. Generate event files
uv run neuro-run events create discovery
uv run neuro-run events qc discovery

# 9. Compile exclusions (behavioral QC)
uv run neuro-run exclusions generate behavioral discovery
uv run neuro-run exclusions compile discovery

# 10. fMRIPrep (--dummy-scans 0 already set in template)
uv run neuro-run submit fmriprep discovery

# 11. Motion exclusions (after fMRIPrep)
uv run neuro-run exclusions generate motion discovery
uv run neuro-run exclusions compile discovery

# 12. First-level GLM
uv run neuro-run submit lev1 discovery
# Each run emits run-manifest.json + dataset_description.json (see docs/PROVENANCE.md)
```

### Re-running a single subject

When `--subjects` is specified, metadata files get a suffix (e.g., `reconciliation_rerun-s286.json`) to avoid overwriting the original full-run logs.

```bash
uv run neuro-run submit bidsify validation \
  --output-dir /scratch/users/logben/validation_bids \
  --subjects s286 --overwrite --time 02:00:00 --mem-gb 16
```

## Three Samples

| Sample | Subjects | BIDS directory |
|--------|----------|---------------|
| discovery | 5 (s03, s10, s19, s29, s43) | `/scratch/users/logben/discovery_bids` |
| validation | 41 | `/scratch/users/logben/validation_bids` |
| excluded | 11 | `/scratch/users/logben/excluded_bids` |

## Behavioral Data

Migrated in-scanner behavioral CSVs live at:
```
/oak/stanford/groups/russpold/data/network_grant/sourcedata/in_scanner_behavior/sub-{subject}/ses-{session}/beh/
```

Session offset subjects (split/skipped BIDS sessions creating +1 offset):
- s321 (ses-02), s1445 (ses-02), s1326 (ses-03), s1391 (ses-06), s1258 (ses-07)

These are handled in the reconciliation manifests by remapping `dest_session`.

## Testing
```bash
uv run pytest tests/ --ignore=tests/analysis -q   # Core suite (~570 tests)
uv run pytest tests/scripts/ -v                    # Scripts tests only
uv run pytest tests/ -v                            # Full suite (includes analysis/lev1)
```

## SLURM/Container

### Rebuilding Container After Code Changes
```bash
sbatch --wrap="apptainer build --fakeroot --force \
  /home/groups/russpold/singularity_images/neuro_workflow.sif \
  /home/users/logben/neuro_workflow/neuro_workflow.def" \
  --partition=russpold --mem=8G --time=00:30:00
```

### Singularity Images
- neuro_workflow: `/home/groups/russpold/singularity_images/neuro_workflow.sif`
- BIDS Validator: `/home/groups/russpold/singularity_images/bids-validator_1.14.6.simg`

## Common Issues

### "ModuleNotFoundError: No module named 'neuro_workflow'"
Use `uv run python` instead of system python.

### Missing physio JSON sidecars
Check `sourcedata/reconciliation.json` for warnings about failed gephysio processing.

### Corrupt NIfTI after SLURM kill
`trim_bold.py` uses atomic writes (temp file + rename) and skips corrupt files with an error log. Re-download the affected subject via `neuro-run submit bidsify` with `--subjects`.

## Git Commit Pattern
```bash
git add <files>
git commit -m "feat|fix|refactor: <description>

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

## Last Updated
2026-06-09
