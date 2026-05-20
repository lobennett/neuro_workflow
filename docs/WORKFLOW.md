# Pipeline: Flywheel to BIDS

**Last updated:** 2026-04-11

Exact commands to reproduce the BIDS datasets from Flywheel. Each step depends on the previous one.

---

## Prerequisites

```bash
module load uv          # Required for all uv run commands
```

- Flywheel API credentials configured
- Write access to `/scratch/users/logben/`
- Write access to `/oak/stanford/groups/russpold/data/network_grant/sourcedata/`
- Container image: `/home/groups/russpold/singularity_images/neuro_workflow.sif`

## Step 1: Pull from Flywheel (bidsify)

Downloads NIfTI, sidecar JSON, and physio from Flywheel. Does NOT trim volumes.

```bash
# Discovery (5 subjects)
uv run neuro-run submit bidsify discovery \
  --output-dir /scratch/users/logben/discovery_bids --overwrite

# Validation (41 subjects)
uv run neuro-run submit bidsify validation \
  --output-dir /scratch/users/logben/validation_bids --overwrite
```

To re-run a single subject without overwriting metadata:
```bash
uv run neuro-run submit bidsify validation \
  --output-dir /scratch/users/logben/validation_bids \
  --subjects s286 --overwrite --time 02:00:00 --mem-gb 16
# Metadata written to suffixed files (e.g., reconciliation_rerun-s286.json)
```

**Config:** `config/pipeline_config.json` (subject lists, session overrides, aliases)
**Output:** NIfTI/JSON/physio in BIDS layout + `sourcedata/reconciliation.json`

## Step 2: Trim 7 dummy BOLD volumes

Removes first 7 volumes from every `*_bold.nii.gz` and writes `NumberOfVolumesDiscardedByUser: 7` to sidecar JSON. Idempotent (safe to run multiple times).

```bash
uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids
uv run python scripts/trim_bold.py /scratch/users/logben/validation_bids
```

Or via SLURM for large datasets:
```bash
sbatch --partition=russpold --mem=16G --time=08:00:00 \
  --wrap="module load uv && uv run python scripts/trim_bold.py /scratch/users/logben/validation_bids"
```

**After trimming:** Use `--dummy-scans 0` in fMRIPrep.

## Step 3: Reconcile behavioral data

Read-only analysis matching BIDS functional scans to raw behavioral CSVs. Produces a TSV manifest for review.

```bash
uv run python scripts/reconcile_sessions.py \
  --raw-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --bids-dir /scratch/users/logben/discovery_bids \
  --scan-notes docs/SCAN-NOTES.md \
  --output config/manifests/reconciliation_discovery.tsv

uv run python scripts/reconcile_sessions.py \
  --raw-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --bids-dir /scratch/users/logben/validation_bids \
  --scan-notes docs/SCAN-NOTES.md \
  --output config/manifests/reconciliation_validation.tsv
```

**Output:** TSV with columns: subject, session, task, status, action, dest_session, dest_run, raw_path, bold_path, same_task_other_sessions, notes

## Step 4: Review manifest

Open the TSV manifests. Every row with `action=pending` must be resolved:

- `copy` — behavioral file matches BOLD scan, migrate it
- `copy` + `dest_session` override — behavioral file is in wrong raw session, remap
- `copy` + `dest_run=2` — short scan is run-1, good scan is run-2
- `skip` — rest scans, behavioral without BOLD, session offset artifacts
- `irreconcilable` — BOLD exists but no behavioral data; add to `.bidsignore`

Cross-reference `docs/SCAN-NOTES.md` and `docs/EXCLUSIONS.md` for context.

For subjects with split/skipped BIDS sessions (s321, s1445, s1326, s1391, s1258), apply +1 session offset from the split point onward.

## Step 5: Update .bidsignore

Add irreconcilable and prematurely ended scans. Every entry has an inline comment with the reason.

```bash
# Example entry format:
# s300 ses-08 flanker: behavioral lost in server crash, makeup in ses-09
sub-s300/ses-08/func/sub-s300_ses-08_task-flanker_run-*_echo-*_bold.*
```

Use `scripts/check_tr.sh` to identify scans with unexpected TR counts:
```bash
bash scripts/check_tr.sh /scratch/users/logben/discovery_bids /scratch/users/logben/validation_bids
```

Document all exclusions in `docs/EXCLUSIONS.md`.

## Step 6: Migrate behavioral data

Copies behavioral CSVs to BIDS sourcedata, renaming to BIDS convention. Only rows with `action=copy` are processed.

```bash
uv run python scripts/migrate_behavioral.py \
  --manifest config/manifests/reconciliation_discovery.tsv \
  --raw-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --output-dir /oak/stanford/groups/russpold/data/network_grant/sourcedata \
  --sample discovery --strict

uv run python scripts/migrate_behavioral.py \
  --manifest config/manifests/reconciliation_validation.tsv \
  --raw-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned \
  --output-dir /oak/stanford/groups/russpold/data/network_grant/sourcedata \
  --sample validation --strict
```

**Output:** `sourcedata/in_scanner_behavior/sub-{subject}/ses-{session}/beh/` + `migration_report.json`

## Step 7: Validate

```bash
# BIDS validator
singularity run -B /scratch/users/logben \
  /home/groups/russpold/singularity_images/bids-validator_1.14.6.simg \
  /scratch/users/logben/discovery_bids

# Verify 1-1 behavioral matching (every non-rest, non-bidsignored BOLD has behavioral)
# Use reconciliation TSVs: zero pending rows, all copy/skip/irreconcilable
```

## Step 8: Generate event files

```bash
# (TBD — uses src/neuro_workflow/events/)
# Onsets adjusted by 7 * 1.49s = 10.43s for trimmed dummy volumes
# Negative onset rows filtered out
```

## Step 9: Preprocessing (fMRIPrep)

```bash
uv run neuro-run submit fmriprep discovery --dummy-scans 0
```

## Step 10. XCP-D post-fMRIPrep denoising

Once fMRIPrep is complete for a subject, run XCP-D 26.0.2 to produce
denoised BOLD + connectivity outputs. Uses the canonical flag set from
the lab's PFM-compare project (Gracie Grimsrud's `run_xcpd.sh`).

Per-subject resources: bigmem partition, 384 GB (16 cpus x 24 GB), 24 h
walltime cap. Throttle the array to 8 concurrent jobs to be polite to the
lab queue.

```bash
uv run neuro-run submit xcpd discovery_xcpd --version 26.0.2
uv run neuro-run submit xcpd validation_xcpd --version 26.0.2
```

bigmem QOS caps account submissions at 20 queued+running. For the
41-subject validation cohort, submit progressively as discovery jobs
drain -- `/scratch/users/logben/xcpd_progressive_submit.sh` is a watcher
that polls every 10 minutes and submits the next sub-array when slots
open.

Outputs land at `<bids_dir>/derivatives/xcp_d_26.0.2/sub-<S>/`.

If a subject times out at 24 h, simply resubmit -- nipype reads its cached
work dir at `$SCRATCH/work/xcpd_<dataset>_26.0.2/sub-<S>/` and resumes.

---

## Key files

| File | Purpose |
|------|---------|
| `config/pipeline_config.json` | Subject lists, session overrides, Flywheel aliases |
| `config/manifests/reconciliation_*.tsv` | Reviewed behavioral-BOLD matching manifests |
| `docs/EXCLUSIONS.md` | Why every scan is in .bidsignore |
| `docs/SCAN-NOTES.md` | Raw data collection notes per subject |
| `scripts/trim_bold.py` | Trim 7 dummy BOLD volumes (idempotent) |
| `scripts/reconcile_sessions.py` | Match BIDS scans to raw behavioral CSVs |
| `scripts/migrate_behavioral.py` | Copy behavioral to BIDS sourcedata per manifest |
| `scripts/check_tr.sh` | Check for scans with unexpected TR counts |

## Samples

| Sample | Subjects | BIDS directory | Behavioral |
|--------|----------|---------------|------------|
| Discovery | 5 (s03, s10, s19, s29, s43) | `/scratch/users/logben/discovery_bids` | `sourcedata/in_scanner_behavior/` |
| Validation | 41 | `/scratch/users/logben/validation_bids` | `sourcedata/in_scanner_behavior/` |
| Excluded | 11 | `/scratch/users/logben/excluded_bids` | Not processed |
