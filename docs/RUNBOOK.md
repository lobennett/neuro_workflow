# RUNBOOK: launching jobs through neuro_workflow on Sherlock/SLURM

Operational, copy-pasteable reference for how every stage is launched. All paths are
absolute. Anything not directly verifiable from the code is marked **[VERIFY]**.

> **HARD CONSTRAINT — a controller is running right now.** A SLURM controller job runs
> `cd /home/users/logben/neuro_workflow && uv run python scripts/iproc_tedana_scatter.py submit ...`
> every 10 minutes (the iProc tedana scatter, subject s10). Do **not** edit, move, rename,
> or delete files in this repo while it runs. The controller imports **only the Python
> standard library** (`argparse, csv, logging, re, subprocess, sys, pathlib, getpass` —
> verified at the top of `scripts/iproc_tedana_scatter.py`); it does **not** import
> `neuro_workflow`. So package-level work cannot break it — but the `.venv` and `uv`
> must keep resolving, and `scripts/iproc_tedana_scatter.py` itself must stay byte-for-byte
> intact and runnable. See the iProc section for what is and isn't safe to touch.

---

## 0. Environment setup (do this first, every shell)

Claude Code / interactive shells auto-load via `~/.bashrc`:

```bash
module use $HOME/modulefiles
module load uv/0.9.5 claude-code
```

For running pipelines you only need `uv` on PATH. On a fresh login or inside an sbatch
script the standard PATH does **not** include `uv` or `gh` — you must `module load` first:

```bash
module load uv          # required before any `uv run` command
```

**CRITICAL:** always invoke Python through `uv run` (or `uv --directory <repo> run`) so
project dependencies resolve from the `.venv`. Plain `python scripts/foo.py` will fail with
`ModuleNotFoundError: No module named 'neuro_workflow'`.

```bash
# WRONG
python scripts/trim_bold.py /scratch/users/logben/discovery_bids
# CORRECT
uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids
```

The console entry point `neuro-run` (declared in `pyproject.toml` `[project.scripts]` →
`neuro_workflow.cli:main`) is invoked as `uv run neuro-run ...`.

---

## 1. The `neuro-run` submit pattern (how a pipeline becomes an sbatch job)

`neuro-run` is a thin CLI. The submit path (`src/neuro_workflow/cli.py::cmd_submit`) is:

1. **Look up the pipeline** in the registry by name (`get_pipeline(name)`). All pipeline
   classes self-register at import time; `cli.py` imports each module explicitly
   (`cli.py:19-30`) so the registry is fully populated and visible in code review.
2. **Parse pipeline-specific args** with a second-pass `ArgumentParser` built by the
   pipeline's `add_cli_args()`. Anything after `<pipeline> <dataset>` is forwarded here.
3. **Load the dataset config** (unless the pipeline sets `requires_dataset = False`, which
   bidsify does). Config comes from `~/.neuro_workflow/datasets.json`, keyed by dataset
   name, holding `bids_dir`, `subjects_file`, and optional `partition`, `mail_user`,
   `image_dir`, `templateflow_dir`.
4. **Ensure the container image** if the pipeline declares a `docker_uri`
   (`core/image.py::ensure_image`): looks for `<image_dir>/<pipeline>_<version>.sif`, and
   if absent runs `apptainer pull <image_dir>/<name>_<version>.sif docker://...:<version>`.
5. **Build the template context** — `pipeline.build_context(dataset, config, args)` returns
   a plain dict. This is where subject/job lists are written to disk, resources resolved,
   and log dirs created.
6. **Render the sbatch template** — `core/slurm.py::render_template` reads
   `src/neuro_workflow/templates/<template_name>` and does Python `str.format(**ctx)`.
   (Note: it is `str.format`, not Jinja — `{name}` placeholders, and any literal brace in
   bash is escaped as `{{` / `}}` in the template.)
7. **Submit** — `core/slurm.py::submit_sbatch` writes the rendered script to a temp
   `*.sbatch` file, runs `sbatch <tmpfile>`, prints the temp path and the job id, and
   `sys.exit(1)` on a non-zero `sbatch` return.

Two non-submitting commands help you inspect before you fire:

```bash
# List registered datasets and their bids_dir
uv run neuro-run show --list

# Render and PRINT the sbatch script without submitting (same context build, no sbatch)
uv run neuro-run show <pipeline> <dataset> [pipeline args...]
```

`submit` prints the full rendered script under `--- Generated sbatch script ---` before
submitting, so you always see exactly what ran.

### Registering a dataset (one-time, prerequisite for every pipeline except bidsify)

```bash
uv run neuro-run add-dataset discovery \
  --bids-dir /scratch/users/logben/discovery_bids \
  --subjects-file /home/users/logben/neuro_workflow/subjects_discovery.txt \
  --partition russpold \
  --image-dir /home/groups/russpold/singularity_images \
  --templateflow-dir /home/groups/russpold/templateflow \
  --mail-user logben@stanford.edu      # optional; enables #SBATCH --mail-* lines
```

Stored in `~/.neuro_workflow/datasets.json`. The `subjects_file` is a plain text file, one
subject label per line (bare `s03` or `sub-s03` depending on stage — see per-stage notes).
The canonical cohort membership lives in `config/pipeline_config.json` under `samples`; the
`subjects_*.txt` files at the repo root are operational scratch derived from it (most are
gitignored via `/subjects_*.txt`).

### Resource overrides and array throttling

Every pipeline exposes `--nthreads`, `--mem-gb` (or `--mem-per-cpu-gb`), `--time`; unset
values fall back to the pipeline's `default_resources` (`base.py::resolve_resources`).
Preprocessing pipelines (fmriprep, xcpd) additionally take `--array-throttle N` →
`#SBATCH --array=1-N_subjects%N` to cap concurrent array tasks.

---

## 2. Per-stage launch

Below, each stage shows the submit command, where the template renders the work, and where
outputs + logs land. Cohorts: `discovery` (5 subjects: s03, s10, s19, s29, s43) and
`validation` (41 subjects). BIDS roots: `/scratch/users/logben/{discovery,validation}_bids`.

### 2.1 bidsify (Flywheel → BIDS) — `templates/bidsify.sbatch`

Single job (no array). `requires_dataset = False`: takes `--output-dir` directly, not a
registered dataset. Runs inside the project container.

```bash
uv run neuro-run submit bidsify discovery \
  --output-dir /scratch/users/logben/discovery_bids \
  --overwrite

# Re-run one subject (produces suffixed metadata, e.g. reconciliation_rerun-s286.json):
uv run neuro-run submit bidsify validation \
  --output-dir /scratch/users/logben/validation_bids \
  --subjects s286 --overwrite
```

- Container: `/home/groups/russpold/singularity_images/neuro_workflow.sif` (the
  `{container}` placeholder). **[VERIFY]** exact path/flags in `pipelines/bidsify.py`.
- Inner command: `apptainer run "$CONTAINER" bidsify <sample> --output-dir ... <extra_args>`.
- **Outputs:** the BIDS tree under `--output-dir`. **Logs:** `{log_dir}/%x-%j.out|.err`
  (the `bidsify_<sample>` job name; log dir set by the pipeline context). **[VERIFY]**
- FW credential: `FW_API_KEY` lives in `.env` (gitignored). **[VERIFY]** how it reaches the
  container env.

After bidsify, the post-BIDS steps run **outside** SLURM as direct CLI calls:
`uv run python scripts/trim_bold.py <bids_dir>` (trim 7 dummy volumes; idempotent), then
`uv run neuro-run events create|qc|trim <dataset>`.

### 2.2 fmriprep — `templates/fmriprep.sbatch`

Array job, one task per subject, throttled. `--version` is **required** (no default; the
build errors out without it). Pulls/uses `<image_dir>/fmriprep_<version>.sif`.

```bash
uv run neuro-run submit fmriprep discovery \
  --version 25.2.4 \
  --output-spaces "MNI152NLin6Asym:res-2 fsaverage6" \
  --array-throttle 8 \
  --fmriprep-args "--dummy-scans 0"
```

- Array: `#SBATCH --array=1-<n_subjects>%<array_throttle>`; the running subject is picked by
  `sed "${SLURM_ARRAY_TASK_ID}q;d" <subjects_file>`.
- Defaults: 8 cpus, `--mem-per-cpu 8G` (→ `--mem_mb` = nthreads×mem×1000×0.9), `5-00:00:00`.
- Binds `/data` (bids), `/templateflow`, `/work`. `--bids-dir-override` lets `/data` point
  at a symlink BIDS view (used with `scripts/fmriprep_preflight.py`) while derivatives still
  go to the registered `bids_dir`.
- Work dir: `$SCRATCH/work/fmriprep_<dataset>_<version>` (cleaned per-subject on success).
- **Outputs:** `<bids_dir>/derivatives/fmriprep_<version>/` by default (or under
  `--output-dir` / the override's registered derivatives).
- **Logs:** `<...>/fmriprep_<version>/logs/%x-%A-%a.out|.err`.
- Has a benign exit-1 workaround for fmriprep#3634: if the `.out` log contains
  "fMRIPrep finished successfully", exit-1 is treated as exit-0.

### 2.3 xcpd (post-fmriprep denoising) — `templates/xcpd.sbatch`

Array job, one per subject, throttled. Requires `--version` and `--fmriprep-version`
(it reads the fmriprep derivatives as `/data:ro`). Default partition for xcpd is typically
**bigmem** via the dataset config; defaults are heavier (16 cpus, 24G/cpu **[VERIFY]**).

```bash
uv run neuro-run submit xcpd discovery \
  --version 26.0.2 \
  --fmriprep-version 25.2.4 \
  --array-throttle 8 \
  --xcpd-args "--despike"
```

- Hard-coded run flags in the template: `--mode abcd --fd-thresh 0.3 --combine-runs
  --warp-surfaces-native2std --linc-qc --min-time 150 --min-coverage 0.5` + notch motion
  filter; `{xcpd_args}` are appended.
- **Outputs:** `--output-dir` (bound as `/out`), per-subject `sub-<id>/`. **[VERIFY]** the
  default output path in `pipelines/xcpd.py`.
- **Logs:** `{log_dir}/%x-%A-%a.out|.err`.
- Benign exit-1 workaround for the XCP-D 26.0.2 execsummary matplotlib bug: if the log
  contains "Reports generated successfully", exit-1 is treated as exit-0.

Preflight helper (omits T2w-only anat dirs XCP-D rejects):
`uv run python scripts/xcpd_preflight.py discovery_xcpd --fmriprep-version 25.2.4 --xcpd-version 26.0.2`.

### 2.4 lev1 (subject-level GLM array) — `templates/lev1.sbatch`

Array job over the **Cartesian product of subjects × tasks**. No container — runs the
package directly via `uv --directory <repo> run python -m neuro_workflow.analysis.lev1.run`.
Exactly one task selector is **required**: `--tasks NAME...` | `--all` | `--base-tasks`
| `--dual-tasks`. `--fmriprep-dir` is required.

```bash
uv run neuro-run submit lev1 discovery \
  --base-tasks \
  --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
  --space MNI \
  --smoothing-fwhm 5
```

- 8 base tasks: cuedTS, directedForgetting, flanker, goNogo, nBack, shapeMatching,
  spatialTS, stopSignal (+10 dual tasks under `--dual-tasks` / `--all`).
- The context writes a `job_list.txt` (one `SUBJ TASK` per line) into the results log dir;
  the array picks its line with `sed -n "${SLURM_ARRAY_TASK_ID}p" job_list.txt`.
  `#SBATCH --array=1-<n_jobs>` where `n_jobs = len(subjects) × len(tasks)` (**not** throttled).
- Defaults: 1 cpu, 64G, `2-00:00:00`.
- Optional flags forwarded to the analysis: `--residuals`, `--fc-confounds`,
  `--skip-existing`, `--skip-qc-plots`, `--threshold`, `--smoothing-fwhm`. Surface spaces
  (`surface`/`fsaverage6`/`fsLR`) trigger FreeSurfer smoothing, so the template
  `module load biology freesurfer/8.1.0`.
- **Exclusions are required.** If `--exclusions-file` is omitted it uses the compiled
  exclusions for the dataset; if none exist the build aborts telling you to run
  `neuro-run exclusions compile <dataset>` first. Subject labels here are typically bare
  (`s03`) per the subjects file. **[VERIFY]** `sub-` prefixing convention against the file.
- **Outputs:** `--results-dir` (default `<bids_dir>/derivatives/lev1`).
  **Logs:** `<results_dir>/logs/%x-%A-%a.out|.err`.

Single-subject smoke test (manual sbatch, hardcoded discovery paths):
`sbatch /home/users/logben/neuro_workflow/scripts/run_lev1_smoke.sbatch sub-s03 cuedTS`.

### 2.5 lev2 (group fixed-effects + randomise) — `templates/lev2.sbatch`

Array job over **contrasts**. No container; runs
`python -m neuro_workflow.analysis.lev2.run`. `--lev1-dirs` and `--results-dir` are
required; exactly one of `--contrasts NAME...` | `--all` | `--base-tasks` | `--dual-tasks`.

```bash
uv run neuro-run submit lev2 discovery \
  --lev1-dirs /scratch/users/logben/discovery_bids/derivatives/lev1 \
              /scratch/users/logben/validation_bids/derivatives/lev1 \
  --results-dir /scratch/users/logben/lev2_pooled \
  --all \
  --mask-threshold 0.9 \
  --num-permutations 5000
```

- Contrasts are auto-discovered by globbing
  `<lev1_dir>/sub-*/*/fixed_effects/*_stat-fixed-effects.nii.gz` and parsing the
  `task-..._contrast-...` token. Files tagged `_desc-belowMinRuns` are skipped by lev2.
  Discovered contrasts are written to `<results_dir>/logs/contrast_list.txt`, one per array
  task.
- `module load biology fsl` (randomise). Defaults: 2 cpus, 4G, `04:00:00`.
- **Outputs:** `--results-dir`. **Logs:** `<results_dir>/logs/%x-%A-%a.out|.err`.

### 2.6 prep-mshbm (surface prep) — `templates/prep_mshbm.sbatch`

Array job, one per subject. `--fmriprep-dir` and `--output-dir` required; supply exactly one
of `--rest-only` or `--glm-dir <lev1-dir>` (validated in `pipelines/prep_mshbm.py`). No
container; runs `python -m neuro_workflow.analysis.mshbm.run`.

```bash
# Rest-only variant
uv run neuro-run submit prep-mshbm discovery \
  --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
  --output-dir /scratch/users/logben/mshbm_surface_prep \
  --rest-only

# Task-residual variant
uv run neuro-run submit prep-mshbm discovery \
  --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
  --output-dir /scratch/users/logben/mshbm_surface_prep \
  --glm-dir /scratch/users/logben/discovery_bids/derivatives/lev1 \
  --residuals-space surface
```

- `#SBATCH --array=1-<n_subjects>` (one per subject; not throttled). Subject per line via
  `sed -n "${SLURM_ARRAY_TASK_ID}p" <subject_list_file>`.
- `module load biology freesurfer/8.1.0` + `biology ants/2.4.0` + `uv`. Defaults: 1 cpu,
  64G, `24:00:00` **[VERIFY]**.
- **Outputs:** `--output-dir`. **Logs:** `{log_dir}/%x-%A-%a.out|.err`. **[VERIFY]** log dir.

### 2.7 mshbm (MATLAB network mapping) — `templates/mshbm.sbatch`

**Single** job (not an array). Drives the PrecisionNetworkMapping MATLAB wrapper.
`--surface-inputs-dir` and `--output-dir` required; `--mshbm-dir` points at the PNM repo.

```bash
uv run neuro-run submit mshbm discovery \
  --surface-inputs-dir /scratch/users/logben/mshbm_surface_prep \
  --output-dir /scratch/users/logben/mshbm_maps \
  --mshbm-dir /home/users/logben/neuro_workflow/external/PrecisionNetworkMapping
```

- Context writes a 2-column, header-less CSV (`sub-XXX,<surface_dir>/`) consumed by MATLAB.
- `module load matlab`; runs `bash <mshbm_dir>/MSHBM/run_MSHBM.sh <sub_list> <output_dir> <mshbm_dir>`.
- Defaults: 1 cpu, 64G, `24:00:00` **[VERIFY]**.
- **Outputs:** `--output-dir`. **Logs:** `<output_dir>/logs/%x-%j.out|.err`.

PNM is a git submodule at `external/PrecisionNetworkMapping`. **[VERIFY]** that `lib/` is
populated; the original `~/network_glm` clone has been used for `CBIG_CODE_DIR`.

### 2.8 qa_report (cohort QA HTML + reliability movies) — `scripts/run_qa_report.sbatch`

Not a `neuro-run` pipeline — a standalone sbatch wrapper around `scripts/qa_report.py`
(which calls `neuro_workflow.qa.report.build_reports`). Submit with plain `sbatch`; args
after the script path pass through to the Python script.

```bash
sbatch /home/users/logben/neuro_workflow/scripts/run_qa_report.sbatch \
  --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
  --decisions /home/users/logben/neuro_workflow/config/manifests/qc_decisions.tsv \
  --euler-n-sigma 2.0
```

- Wrapper: `#SBATCH -p russpold`, 12h, 128G, 6 cpus; `module load uv ffmpeg/7.1 cairo`,
  prepends `~/.local/bin` to PATH for the `brm` (bold-reliability-movies) CLI. `cd`s into
  the repo and runs `uv run python scripts/qa_report.py "$@"`.
- `qa_report.py` args: `--fmriprep-dir` (required), `--output-dir` (default
  `<fmriprep-dir>/qa_html`), `--subjects`, `--decisions`, `--no-reliability-movies`,
  `--euler-n-sigma`.
- **Outputs:** the QA HTML dashboard at `<fmriprep-dir>/qa_html/` (or `--output-dir`).
  **Logs:** `logs/qa_report-%j.out|.err` **relative to the repo** (`logs/` in the repo). The
  `.err` files are currently not gitignored (see hygiene note at the end).

Related: cohort lev1 QC via `sbatch scripts/run_lev1_outliers.sbatch --lev1-dir ...`
(russpold, 1h, 16G, 2 cpus → `scripts/lev1_outliers.py`, logs to `logs/lev1_outliers-%j.*`).

### 2.9 prevalence (maps + dashboards)

Not SLURM pipelines — direct `uv run python` invocations of the untracked
`scripts/prevalence_*.py` family (they import `neuro_workflow.analysis.prevalence.*`). They
render PNG panels + DataTables `index.html` and per-instance trend TSV/figures.

```bash
# Per-instance prevalence over the 8 main task/contrast cells
uv run python /home/users/logben/neuro_workflow/scripts/prevalence_by_instance_run.py ...
# Browseable dashboard of directional prevalence cells
uv run python /home/users/logben/neuro_workflow/scripts/prevalence_dashboard.py ...
```

**[VERIFY]** exact CLI flags and output dirs per script (e.g. the existing diagnostic
dashboard at `/scratch/users/logben/prevalence_diagnostic_all44`). These are research glue,
documented only in their module docstrings.

---

## 3. Exclusions compilation (prerequisite for lev1)

```bash
uv run neuro-run exclusions generate motion discovery     # write sources/motion.json
uv run neuro-run exclusions generate qa_decisions discovery
uv run neuro-run exclusions compile discovery             # merge → compiled + lockfile
uv run neuro-run exclusions show discovery                # summary + provenance
```

- Generators: `motion`, `behavioral`, `lev1_outlier`, `qa_decisions` (registered in
  `cli.py:39-42`). `qa_decisions` reads `config/manifests/qc_decisions.tsv`.
- `compile` writes the per-dataset compiled JSON under
  `~/.neuro_workflow/exclusions/<dataset>/compiled_exclusions.json` and an auditable
  lockfile committed in-repo at `data/exclusions/<dataset>_lock.json` (records `compiled_at`,
  git SHA, and per-generator `ran_at`/`n_entries`).
- lev1 consumes the compiled file automatically unless you pass `--exclusions-file`.

---

## 4. The iProc scatter path (combine → tedana → filter)

iProc is a **separate, parallel pipeline** for subject s10, NOT wired into `neuro-run`. It
runs inside its own container with the unmodified `iProc.py` / `run_tedana.py`. The three
driver scripts only choose *which* (scan, space) each SLURM job handles and submit
idempotently; there is zero scientific divergence from canonical iProc.

Canonical tree (shared, written by all jobs):
`/scratch/users/logben/discovery_bids/derivatives/iproc`
Scatter scaffolding + logs:
`/scratch/users/logben/discovery_bids/derivatives/iproc/scatter_combine_s10`
Container + code: `/scratch/users/logben/iProc/container/iproc.sif`, `/scratch/users/logben/iProc`.

### 4.1 combine and filter — `scripts/iproc_scatter.py`

One SLURM job per task scan, all writing to disjoint per-scan output dirs (`{NAT,MNI}111/
sess/task`, `FS6/...`), so they're race-free. Stage-agnostic: the same scoped
scanlists/cfgs serve both stages; only `--stage`, memory, and the job-name prefix differ.

```bash
# 1. Generate scoped scanlists + cfgs + units_manifest.tsv (setup, once)
uv run python scripts/iproc_scatter.py generate --sub s10 \
  --canonical-root /scratch/users/logben/discovery_bids/derivatives/iproc \
  --scatter-root   /scratch/users/logben/discovery_bids/derivatives/iproc/scatter_combine_s10

# 2. Dry-run one scan for a stage
uv run python scripts/iproc_scatter.py validate --stage combine_and_apply_warp ses-01_FLANKER_009

# 3. Submit one pilot job, verify, then the rest (WAVE 2)
uv run python scripts/iproc_scatter.py submit-pilot --stage combine_and_apply_warp ses-01_FLANKER_009
uv run python scripts/iproc_scatter.py submit-rest  --stage combine_and_apply_warp

# Filter, with each scan's job afterok its matching combine job (per-scan pipeline):
uv run python scripts/iproc_scatter.py submit-rest  --stage filter_and_project --pipeline
```

- WAVE 1 processes the ses-01 midvol bold (FLANKER 009) once; WAVE 2 jobs include its row
  but skip it via iProc's existing-output check.
- Each job: `sbatch --partition russpold --time 18:00:00 --cpus-per-task 8` with a memory
  tier by volume count, wrapping `apptainer exec ... iProc.py -s <stage> --executor local`.
- **NOTE / portability bug:** `iproc_scatter.py` queries `squeue -u logben` with a hardcoded
  username (vs the sibling tedana driver's `getpass.getuser()`). On any other account its
  idempotent re-submit / afterok logic would silently misfire. **[VERIFY]** before reuse.
- **Outputs:** the canonical iProc tree. **Logs:**
  `scatter_combine_s10/logs/<label>/slurm_comb_%j.log`.

### 4.2 tedana ICA denoising — `scripts/iproc_tedana_scatter.py` (THE RUNNING CONTROLLER)

tedana sits **between** combine and filter: combine produces the three spatially-normalized
echoes (MNI111 + NAT111), tedana denoises them into
`<canonical>/mri_data/s10/<SPACE>111/<ses>/<task>_<bld3>/tedana/<ses>_bld<bld3>_desc-denoised_bold.nii.gz`,
and filter's `bandpass_ME` consumes them. 57 scans × 2 spaces (MNI, NAT) = 114 units.

**The bigmem drip-controller pattern in use.** A SLURM controller job runs this every 10
minutes:

```bash
cd /home/users/logben/neuro_workflow && \
uv run python scripts/iproc_tedana_scatter.py submit \
  --sub s10 \
  --canonical-root /scratch/users/logben/discovery_bids/derivatives/iproc \
  --scatter-root   /scratch/users/logben/discovery_bids/derivatives/iproc/scatter_combine_s10 \
  --partition russpold
```

Each `submit` pass is fully idempotent (so re-running every 10 min is safe and is the point):
- reads `units_manifest.tsv` (from the combine `generate` step);
- **skips done** units (denoised output already exists);
- **skips active** units (already in `squeue` under the `iproc_ted_` job-name prefix,
  queried by `getpass.getuser()`);
- **cleans partials**: a `tedana/` dir without the denoised file (OOM/timeout remnant) is
  removed so the retry recomputes instead of silently no-oping;
- **drips under a cap**: with `--space MNI --max-inflight 10` it submits only up to the
  partition's MaxSubmit cap (e.g. bigmem `PU=10`), counting current in-flight jobs and
  topping up the free slots; and if `sbatch` is rejected mid-cycle (cap hit on a transient
  undercount) it logs and **stops that cycle** — the next 10-minute pass tops up again. This
  is the drip: a small queue depth maintained continuously rather than a 114-job blast.

Per-job submission (`_submit_one`): `sbatch --partition russpold --time 04:00:00 --mem 120G
--cpus-per-task 8`, wrapping `apptainer exec --bind /oak:/oak,/scratch:/scratch <sif> ...
run_tedana.py --sub s10 --ses <ses> --task <task> --run <bld> --space <MNI|NAT>
--resolution 111`. Calibration: ~1h25m wall, ~110 GB peak RSS (job 26893565); `--mem 120G`
packs two jobs on a 256 GB russpold node; `--time 04:00:00` gives ~3× headroom.

Other modes:
```bash
# Status: counts done vs pending across both spaces
uv run python scripts/iproc_tedana_scatter.py list --sub s10 \
  --canonical-root /scratch/users/logben/discovery_bids/derivatives/iproc \
  --scatter-root   /scratch/users/logben/discovery_bids/derivatives/iproc/scatter_combine_s10

# One throttled SLURM array instead of the drip (array=0-(N-1)%throttle):
uv run python scripts/iproc_tedana_scatter.py submit-array --sub s10 --throttle 12
```

- **Outputs:** `tedana/` dirs in the canonical tree (above). **Logs:** per-unit at
  `scatter_combine_s10/logs/<label>/slurm_teda_<space>_%j.log|.err`; arrays at
  `scatter_combine_s10/logs/tedana_array_<tag>_%A_%a.log|.err`. None of these are in the
  repo `logs/` dir.

**Safety:** this script imports only stdlib and is the live controller. Do not touch it,
the `.venv`, `uv`, or `scripts/__init__.py` while the controller runs. Editing other,
unrelated files in the repo is fine because the controller never imports `neuro_workflow`.

### 4.3 parallel benchmarking variant — `scripts/iproc_parallel_run.py`

Research/benchmarking only (not production): mirrors the canonical iProc subject tree into a
separate parallel root (immutable inputs symlinked, outputs written only to the parallel
root, zero collision with canonical jobs) to test 3-4× speedup on 32-CPU nodes.

```bash
uv run python scripts/iproc_parallel_run.py --sub s10 \
  --canonical-root /scratch/users/logben/discovery_bids/derivatives/iproc \
  --parallel-root  /scratch/users/logben/discovery_bids/derivatives/iproc_parallel
```

---

## 5. Where things write (quick reference)

| Stage | Submit | Outputs | Logs |
|---|---|---|---|
| bidsify | `neuro-run submit bidsify` (container, 1 job) | `--output-dir` BIDS tree | `{log_dir}/bidsify_<sample>-%j.*` **[VERIFY]** |
| fmriprep | `neuro-run submit fmriprep` (array%throttle) | `<bids>/derivatives/fmriprep_<ver>/` | `<...>/fmriprep_<ver>/logs/%x-%A-%a.*` |
| xcpd | `neuro-run submit xcpd` (array%throttle) | `--output-dir` | `{log_dir}/%x-%A-%a.*` |
| lev1 | `neuro-run submit lev1` (array subj×task) | `--results-dir` (def `<bids>/derivatives/lev1`) | `<results>/logs/%x-%A-%a.*` |
| lev2 | `neuro-run submit lev2` (array per contrast) | `--results-dir` | `<results>/logs/%x-%A-%a.*` |
| prep-mshbm | `neuro-run submit prep-mshbm` (array per subj) | `--output-dir` | `{log_dir}/%x-%A-%a.*` |
| mshbm | `neuro-run submit mshbm` (1 MATLAB job) | `--output-dir` | `<output>/logs/%x-%j.*` |
| qa_report | `sbatch scripts/run_qa_report.sbatch` | `<fmriprep>/qa_html/` | repo `logs/qa_report-%j.*` |
| iproc combine/filter | `iproc_scatter.py submit-rest` | canonical iProc tree | `scatter_combine_s10/logs/<label>/slurm_comb_%j.log` |
| iproc tedana | `iproc_tedana_scatter.py submit` (drip, 10-min) | canonical `.../tedana/...` | `scatter_combine_s10/logs/<label>/slurm_teda_<space>_%j.*` |
| prevalence | `uv run python scripts/prevalence_*.py` | per-script **[VERIFY]** | n/a (foreground) |

---

## 6. Notes, gotchas, and what is safe to delete now

- **Templates are `str.format`, not Jinja.** A literal bash brace must be doubled
  (`${{SLURM_ARRAY_TASK_ID}}`) in the `.sbatch` template. Renaming a context key without
  updating the template (or vice versa) raises `KeyError` at render time.
- **lev1 needs exclusions compiled first**; lev2 auto-discovers contrasts and skips
  `_desc-belowMinRuns` files; xcpd needs fmriprep done; tedana needs combine done.
- **fMRIPrep / XCP-D benign exit-1**: both templates grep the success string and convert
  exit-1 → exit-0. Re-verify the success string when bumping versions.
- **Repo `logs/` hygiene:** `logs/*.err` from `run_qa_report.sbatch` / `run_lev1_outliers.sbatch`
  are currently untracked and not covered by `logs/.gitignore` (which ignores `*.out` but
  not `*.err`). These repo logs are stale SLURM stdout/stderr and are **safe to delete now**:
  the running tedana controller writes to `/scratch/.../scatter_combine_s10/logs`, never to
  the repo `logs/` dir (verified in `iproc_tedana_scatter.py`). Likewise `.pytest_cache/`,
  stray `*.pyc`, and `work/` exploration scratch are safe to delete — none are referenced by
  the controller, the installed package, or the `.venv`. **Do not delete anything during a
  read-only window; this is guidance for a maintenance pass.**
- **Do NOT delete or move**: `scripts/iproc_tedana_scatter.py` (live controller),
  `pyproject.toml` / `src/neuro_workflow/` (package importability), the `.venv`, or
  `scripts/__init__.py`.
- **Username portability**: `iproc_tedana_scatter.py` correctly uses `getpass.getuser()`;
  `iproc_scatter.py` hardcodes `logben` in its `squeue` calls. **[VERIFY]** before running
  the combine/filter scatter under a different account.
