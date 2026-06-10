# Pipeline: Flywheel to BIDS and Analysis

**Last updated:** 2026-06-09

Exact commands to reproduce the BIDS datasets and run the analysis pipeline from Flywheel. Each stage depends on the previous one.

---

## Prerequisites

```bash
module load uv          # Required for all uv run commands
```

- Flywheel API credentials configured (`~/.config/flywheel/user.json` or `FW_API_KEY`)
- Write access to `/scratch/users/logben/`
- Write access to `/oak/stanford/groups/russpold/data/network_grant/sourcedata/`
- Container image: `/home/groups/russpold/singularity_images/neuro_workflow.sif`

---

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

To re-run a single subject without overwriting full-run metadata:
```bash
uv run neuro-run submit bidsify validation \
  --output-dir /scratch/users/logben/validation_bids \
  --subjects s286 --overwrite --time 02:00:00 --mem-gb 16
# Metadata written to suffixed files (e.g., reconciliation_rerun-s286.json)
```

**Config:** `config/pipeline_config.json` (subject lists, session overrides, aliases)
**Output:** NIfTI/JSON/physio in BIDS layout + `sourcedata/reconciliation.json`

---

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

---

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

---

## Step 4: Review manifest

Open the TSV manifests. Every row with `action=pending` must be resolved:

- `copy` — behavioral file matches BOLD scan, migrate it
- `copy` + `dest_session` override — behavioral file is in wrong raw session, remap
- `copy` + `dest_run=2` — short scan is run-1, good scan is run-2
- `skip` — rest scans, behavioral without BOLD, session offset artifacts
- `irreconcilable` — BOLD exists but no behavioral data; add to `.bidsignore`

Cross-reference `docs/SCAN-NOTES.md` and `docs/EXCLUSIONS.md` for context.

For subjects with split/skipped BIDS sessions (s321, s1445, s1326, s1391, s1258), apply +1 session offset from the split point onward.

---

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

To regenerate `.bidsignore` from the compiled exclusions source:
```bash
uv run neuro-run exclusions render-bidsignore discovery --output /scratch/users/logben/discovery_bids/.bidsignore
uv run neuro-run exclusions render-bidsignore validation --output /scratch/users/logben/validation_bids/.bidsignore
```

To regenerate the Markdown exclusions table:
```bash
uv run neuro-run exclusions render-md discovery --output docs/EXCLUSIONS.md
```

Note: ingestion of the static collection-exclusion tables into the compiled single source is in progress (see PR5c).

---

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

---

## Step 7: Validate

```bash
# BIDS validator
singularity run -B /scratch/users/logben \
  /home/groups/russpold/singularity_images/bids-validator_1.14.6.simg \
  /scratch/users/logben/discovery_bids

# Verify 1-1 behavioral matching (every non-rest, non-bidsignored BOLD has behavioral)
# Use reconciliation TSVs: zero pending rows, all copy/skip/irreconcilable
```

---

## Step 8: Generate event files

```bash
uv run neuro-run events create discovery
uv run neuro-run events qc discovery
```

Onsets are adjusted by 7 × 1.49 s = 10.43 s for the trimmed dummy volumes. Negative-onset rows are filtered out.

---

## Step 9: Compile exclusions

Generates and compiles all exclusion sources (behavioral QC, motion) into the dataset-level JSON that lev1 consumes.

```bash
# Generate behavioral exclusions from events QC
uv run neuro-run exclusions generate behavioral discovery
uv run neuro-run exclusions generate behavioral validation

# Compile all sources into the compiled JSON
uv run neuro-run exclusions compile discovery
uv run neuro-run exclusions compile validation

# Inspect the compiled result
uv run neuro-run exclusions show discovery

# Query a specific scan
uv run neuro-run exclusions query discovery --subject s10 --session 03 --task goNogo
```

---

## Step 10: Preprocessing (fMRIPrep)

```bash
uv run neuro-run submit fmriprep discovery
uv run neuro-run submit fmriprep validation
```

Use `--dummy-scans 0` in the fmriprep sbatch template (volumes were already trimmed in Step 2).

---

## Step 11: Post-processing (FreeSurfer, QSIPrep, Happy, fsqc)

```bash
uv run neuro-run submit freesurfer discovery
uv run neuro-run submit qsiprep discovery
uv run neuro-run submit happy discovery
uv run neuro-run submit fsqc discovery
```

---

## Step 12: Motion exclusions

After fMRIPrep is complete, generate motion-based exclusions from confounds TSVs:

```bash
uv run neuro-run exclusions generate motion discovery
uv run neuro-run exclusions compile discovery
```

Motion thresholds are set in `config/thresholds.yaml` (`motion.fd_threshold`, `motion.proportion_fd_threshold`, `motion.proportion_dvars_threshold`). See `docs/CONFIG.md`.

---

## Step 13: First-level GLM (lev1)

```bash
uv run neuro-run submit lev1 discovery
uv run neuro-run submit lev1 validation
```

Each subject run emits:
- `<output_dir>/run-manifest.json` — full provenance record (code SHA, tool versions, config version, input file hashes)
- `<output_dir>/dataset_description.json` — BIDS derivative metadata

To permit running against an uncommitted working tree (prints a warning; `code_dirty=true` in manifest):
```bash
uv run neuro-run submit lev1 discovery --allow-dirty
```

---

## Step 14: Second-level group stats (lev2)

```bash
uv run neuro-run submit lev2 discovery
```

Lev2 reads the `run-manifest.json` from each lev1 subject directory and records an `input_provenance` block in its own manifest, so the full provenance chain is traceable. See `docs/PROVENANCE.md`.

---

## Key files

| File | Purpose |
|------|---------|
| `config/pipeline_config.json` | Subject lists, session overrides, Flywheel aliases |
| `config/thresholds.yaml` | Study-level QC/motion/VIF thresholds (config-as-code) |
| `config/manifests/reconciliation_*.tsv` | Reviewed behavioral-BOLD matching manifests |
| `docs/EXCLUSIONS.md` | Why every scan is in .bidsignore |
| `docs/SCAN-NOTES.md` | Raw data collection notes per subject |
| `docs/CONFIG.md` | Schema and usage for thresholds.yaml and battery.yaml |
| `docs/PROVENANCE.md` | Run-manifest schema and clean-tree policy |
| `scripts/trim_bold.py` | Trim 7 dummy BOLD volumes (idempotent) |
| `scripts/reconcile_sessions.py` | Match BIDS scans to raw behavioral CSVs |
| `scripts/migrate_behavioral.py` | Copy behavioral to BIDS sourcedata per manifest |
| `scripts/check_tr.sh` | Check for scans with unexpected TR counts |

---

## Samples

| Sample | Subjects | BIDS directory | Behavioral |
|--------|----------|---------------|------------|
| Discovery | 5 (s03, s10, s19, s29, s43) | `/scratch/users/logben/discovery_bids` | `sourcedata/in_scanner_behavior/` |
| Validation | 41 | `/scratch/users/logben/validation_bids` | `sourcedata/in_scanner_behavior/` |
| Excluded | 11 | `/scratch/users/logben/excluded_bids` | Not processed |
