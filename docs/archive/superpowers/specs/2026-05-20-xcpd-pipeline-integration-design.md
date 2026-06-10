# XCP-D pipeline integration

**Date:** 2026-05-20
**Author:** logben
**Status:** Approved (user 2026-05-20)

## Problem

We need to run XCP-D 26.0.2 post-fmriprep denoising on the discovery (minus
s03) and validation cohorts. Gracie Grimsrud has the canonical flag set in
`/oak/.../grimsrud/projects/pfm_compare/code/fmriprep_xcpd/run_xcpd.sh`, but
all of her 10+ attempts failed — primarily out-of-memory at 192 GB on the
multi-session subjects, plus one BIDS-validation failure. We want to add
XCP-D as a first-class pipeline in `neuro_workflow` so we can submit it
through the standard `neuro-run` CLI and reuse the existing dataset
registry, sbatch templating, and exclusion machinery.

## Goal

Add an `xcpd` pipeline class + sbatch template to `neuro_workflow` that
runs XCP-D 26.0.2 with Gracie's flag set, sized correctly for our 12-13
session subjects, with resume-on-timeout via nipype work-dir caching. First
batch: 4 discovery subjects (s10/s19/s29/s43) + 41 validation subjects.
sub-s03 joins later once its fmriprep rerun completes.

Out of scope: downstream MSHBM/lev1 integration changes that consume XCP-D
outputs. (Separate work.)
Out of scope: investigating WHY Gracie's flag set causes OOM at 192 GB —
we sidestep by allocating 384 GB on bigmem.

## Constraints

- Run XCP-D 26.0.2 with **identical flags** to Gracie's `run_xcpd.sh` (user
  requirement).
- Submit through `neuro-run submit xcpd <dataset>` (standard CLI surface;
  no bespoke sbatch).
- Use `bigmem` partition (24h wall cap) at **384 GB per job** to avoid
  Gracie's OOM failures. Resume via nipype work-dir caching for any
  subject that exceeds 24h compute time.
- Array throttle = 8 (balances wall-clock vs lab-queue etiquette).
- Skip sub-s03 — its fmriprep rerun is still running. Add it later.

## Approach

### Component 1 — XCP-D pipeline module

New file `src/neuro_workflow/pipelines/xcpd.py`, mirroring the existing
`fmriprep.py` / `qsiprep.py` pattern:

- `XcpdPipeline` class implementing the `Pipeline` Protocol from
  `base.py`
- `name = "xcpd"`, `template_name = "xcpd.sbatch"`,
  `docker_uri = "docker://pennlinc/xcp_d"`
- `default_resources = {"nthreads": 16, "mem_per_cpu_gb": 24, "time":
  "1-00:00:00"}` (16 CPUs × 24 GB ≈ 384 GB total)
- `add_cli_args`:
  - `--version` (XCP-D version, e.g. `26.0.2`)
  - `--fmriprep-version` (which fmriprep derivatives to read; default `25.2.4`)
  - `--xcpd-args` (passthrough for ad-hoc additions, default ""; we
    hard-code Gracie's flags as base)
  - `--fs-license`
  - Resource overrides (`--nthreads`, `--mem-per-cpu-gb`, `--time`,
    `--array-throttle`)
  - `--partition` (default `bigmem`)
- `build_context` returns:
  - `image_path` = `<image_dir>/xcpd_<version>.sif`
  - `work_dir` = `$SCRATCH/work/xcpd_<dataset>_<version>/`
  - `output_dir` = `<bids_dir>/derivatives/xcp_d_<version>/`
  - `log_dir` = `<output_dir>/logs/`
  - `fmriprep_dir` = `<bids_dir>/derivatives/fmriprep_<fmriprep_version>/`
    (input to XCP-D; defaults to `fmriprep_25.2.4` — user-overridable)
  - Standard subjects_file, partition, mail, etc.

Add one import line to `src/neuro_workflow/cli.py` to trigger
auto-registration.

### Component 2 — sbatch template

New file `src/neuro_workflow/templates/xcpd.sbatch`, mirroring
`fmriprep.sbatch`:

```bash
#!/bin/bash
#SBATCH -J xcpd_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_subjects}%{array_throttle}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

subject=$(sed "${{SLURM_ARRAY_TASK_ID}}q;d" {subjects_file} | tr -d '\r')

XCPD_IMG="{image_path}"
mkdir -p "{work_dir}/sub-${{subject}}"
mkdir -p "{output_dir}/sub-${{subject}}"

apptainer run --cleanenv \
  -B {fmriprep_dir}:/data:ro \
  -B {output_dir}:/out \
  -B {work_dir}:/work \
  -B {fs_license}:/opt/freesurfer/license.txt \
  "$XCPD_IMG" \
  /data /out participant \
  --participant-label "$subject" \
  -w /work/sub-${{subject}} \
  --mode abcd \
  --despike \
  --fd-thresh 0.3 \
  --input-type fmriprep \
  --warp-surfaces-native2std \
  --combine-runs \
  --linc-qc \
  --min-time 150 \
  --min-coverage 0.5 \
  --band-stop-min 12 --band-stop-max 20 --motion-filter-type notch \
  --omp-nthreads 3 \
  --nprocs {nthreads} \
  --smoothing 0 \
  --motion-filter-order 4 \
  {xcpd_args} \
  -vv

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
```

Notable design choices:
- Per-subject work subdir under `{work_dir}` so multiple array tasks don't
  collide
- Input mount is the **fmriprep derivatives dir**, not the BIDS root (XCP-D
  consumes fmriprep outputs)
- No auto-cleanup of work dir on success — preserves nipype cache for
  resume (in case a follow-up job needs the same work)

### Component 3 — Container

XCP-D 26.0.2 already exists at
`/oak/stanford/groups/russpold/shared/containers/xcp_d-26.0.2.sif`
(1.8 GB).

Symlink it into the lab's standard `image_dir`
(`/home/groups/russpold/singularity_images/`) as `xcpd_26.0.2.sif` so the
pipeline finds it via `<image_dir>/xcpd_<version>.sif` (matches the
existing fmriprep/qsiprep convention).

### Component 4 — Dataset registrations

Use the existing `subjects_phase1_s03.txt`-style pattern to register two
XCP-D datasets:

- `discovery_xcpd`: bids_dir = `/scratch/users/logben/discovery_bids`,
  subjects_file = `subjects_discovery_xcpd.txt` (4 lines: s10, s19, s29,
  s43). Output goes to `<bids_dir>/derivatives/xcp_d_26.0.2/`. Excludes s03
  pending its fmriprep rerun.
- `validation_xcpd`: bids_dir = `/scratch/users/logben/validation_bids`,
  subjects_file = `subjects_validation_xcpd.txt` (41 lines).

Both registered via `uv run neuro-run register dataset xcpd ...`.

After s03 finishes its fmriprep rerun, add it back: `echo s03 >>
subjects_discovery_xcpd.txt` and resubmit.

## Data flow

```
fmriprep derivatives (existing)         XCP-D 26.0.2 container
        │                                       │
        └─────────────► neuro-run submit ◄──────┘
                              │
                              ▼
                  Array of 4+41 = 45 SLURM jobs
                              │
                              ▼
                  bigmem nodes, 384 GB, throttle 8
                              │
                              ▼
       <bids_dir>/derivatives/xcp_d_26.0.2/sub-<S>/...
                              │
                              ▼
              If subject times out @ 24h: resubmit
              (nipype reads cached work dir, skips done nodes)
```

## Files to create / modify

| File | Change |
|---|---|
| `src/neuro_workflow/pipelines/xcpd.py` | New (~120 lines) |
| `src/neuro_workflow/templates/xcpd.sbatch` | New (~50 lines) |
| `src/neuro_workflow/cli.py` | Add one import line for auto-registration |
| `tests/pipelines/test_xcpd.py` | New tests for pipeline class + template render (~80 lines) |
| `subjects_discovery_xcpd.txt` | New 4-line file (s10/s19/s29/s43) |
| `subjects_validation_xcpd.txt` | New 41-line file |
| `/home/groups/russpold/singularity_images/xcpd_26.0.2.sif` | Symlink to oak `xcp_d-26.0.2.sif` |
| `docs/WORKFLOW.md` | Add XCP-D as Step 10 (post-fmriprep) |

## Resume protocol

Each XCP-D job creates `$SCRATCH/work/xcpd_<dataset>_<version>/sub-<S>/`.
If the job times out at 24h:

1. The SLURM job exits non-zero (TIMEOUT state)
2. The work dir is preserved (we never `rm` it)
3. Resubmit the dataset; the SLURM array re-runs failed indices
4. nipype detects existing cached node outputs and skips them
5. Repeat until job exits 0

This matches what Gracie did manually — we just make it routine via the
work-dir-preservation policy.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| 384 GB still not enough memory | Resubmit with `--mem-per-cpu-gb 32` (= 512 GB total) on the affected subject only; the resource overrides in `add_cli_args` make this a one-flag retry |
| `--combine-runs` causes runaway memory on a specific subject | Drop the flag for that subject (override via `--xcpd-args` or a per-subject branch). Not part of initial submission — only if observed. |
| Container image not at expected path | Symlink step in this plan creates it; pipeline `build_context` raises clear error if missing |
| BIDS validation in XCP-D refuses our derivatives | We already verified `dataset_description.json` exists in both discovery + validation fmriprep dirs. If XCP-D still complains, add `--skip-bids-validation` or generate the minimal sidecar |
| Wall-clock too long despite throttle 8 | Bump throttle to 12 mid-run by editing the array directive on subsequent resubmits |
| Output dir conflicts with concurrent jobs (multiple subjects writing to same dir) | XCP-D writes to `<output>/sub-<S>/...` which is per-subject; no conflict |

## Testing

- Unit test: `tests/pipelines/test_xcpd.py`
  - `XcpdPipeline.build_context()` produces the expected dict shape
  - Template rendering substitutes all placeholders with no left-over `{...}`
  - CLI arg parsing accepts standard resource overrides
- Operational test: submit on one validation subject first (sub-s76 or
  similar) as a sanity check that BIDS validation passes and XCP-D starts
  cleanly. If OK within ~5 min wall, submit the rest of the cohort. (Not
  the same as a "smoke test for runtime profiling" — just a "does it
  start at all" check.)
- Cohort submission via standard `neuro-run submit xcpd discovery_xcpd`
  and `neuro-run submit xcpd validation_xcpd`.

## Success criteria

- `neuro-run submit xcpd discovery_xcpd --version 26.0.2 ...` submits 4
  jobs, throttle 8, all on bigmem 384 GB
- All 45 subjects (4 discovery + 41 validation) eventually exit 0
- Outputs land at `<bids_dir>/derivatives/xcp_d_26.0.2/sub-<S>/...`
- Each subject has expected XCP-D output files (denoised BOLD, connectivity
  matrices, QC HTML)
- The two new datasets are registered and re-usable for sub-s03 once its
  fmriprep finishes
