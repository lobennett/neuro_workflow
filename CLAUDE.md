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
- `pyproject.toml` - Project configuration and dependencies

## Bidsify Updates (March 14, 2026)

### Changes Made to run.py
1. **Reduced parallel workers**: 16 → 4 to avoid Flywheel API rate limiting
2. **Safe sidecar patching**: Added `_safe_patch_sidecar()` with retry logic (3 attempts)
3. **Better error logging**: All failures now logged with full context
4. **Duplicate anatomical handling**: Marks duplicate T1w/T2w/etc. in same session for .bidsignore
5. **Duplicate DWI handling**: Marks duplicate diffusion scans in same session for .bidsignore
6. **Improved physio error handling**: Physio failures now generate warnings instead of silent skips

### Example Scenarios Handled
- **s19 with multiple T1w (SagMPRAGE_T1w)**: First kept, subsequent ones marked for .bidsignore
- **s956 missing TR/Units metadata**: Now logs detailed errors and retry attempts
- **s480 3D BOLD files**: Detected and marked for .bidsignore
- **Physiological recordings without JSON**: Failed conversions now captured in warnings

## Running Bidsify

### Command Pattern
```bash
uv run python -m neuro_workflow.cli bidsify <sample> \
    --output-dir <bids_output> \
    [--subjects <list>] \
    [--skip-validation] \
    [-v]
```

### Example: Run validation sample with automatic BOLD validation
```bash
uv run python -m neuro_workflow.cli bidsify validation \
    --output-dir /scratch/users/logben/validation_bids \
    -v
```

## BOLD Validation System

Validation runs automatically after bidsify completes (no flag needed):
- Analyzes all BOLD files for issues (3D, missing TR, short scans)
- Generates `.bids-validation/analysis.json` with detailed results
- Updates `.bidsignore` with problematic scans
- Can be skipped with `--skip-validation` if needed

## Testing Changes
```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/ -v
uv run pytest tests/bids_validation/ -v  # Specific test suite
```

## Common Issues and Solutions

### "ModuleNotFoundError: No module named 'neuro_workflow'"
**Solution:** Use `uv run python` instead of system python

### JSON patching failures on s956, s1267, s1351
**Causes:**
- Corrupted JSON files from Flywheel extraction
- Concurrent writes from parallel processing
- Flywheel API timeouts

**Solution:** Rerun bidsify with updated run.py (now has retry logic)

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
- `.bidsignore` - Files to exclude from validation
- `.bids-validation/analysis.json` - BOLD analysis results
- `sourcedata/reconciliation.json` - Subject session mapping and warnings
- `sourcedata/bidsify_log.json` - Download logs

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
2026-03-14 - Added bidsify improvements (reduced parallelism, retry logic, duplicate handling)


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
5. **`docs/TR-BASED-SHORT-SCAN-DETECTION.md`** - Technical reference for BOLD validation approach

### Logs Organization
Logs have been moved to `logs/` directory with `.gitignore` to prevent bloat:
- `logs/bidsify_logs/` - Bidsify execution logs
- `logs/build_logs/` - Container build logs
- `logs/validator_logs/` - BIDS validator outputs

### Key Principles After Cleanup
- **No hardcoded lists:** All subject lists, aliases, thresholds in JSON config files
- **Reproducibility:** Same config → same results, verifiable in git
- **Simplicity:** Follow WORKFLOW.md for entire pipeline; refer to ARCHITECTURE.md only when understanding internals
- **Audit trail:** All decisions encoded in JSON + exclusions.json manifests

**Last updated:** 2026-03-17
