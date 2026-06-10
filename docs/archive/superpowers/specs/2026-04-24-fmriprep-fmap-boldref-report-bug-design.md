# Design: Reproduce and Fix fMRIPrep Fieldmap↔BOLD Reference Report Bug

Date: 2026-04-24
Owner: logben
Status: Approved (sections 1–6), pending spec-file review

## Problem

In the fMRIPrep 25.2.0 report for sub-s8, the figure "Alignment between the anatomical
reference of the fieldmap and the BOLD reference" renders correctly for ses-01 but is
visibly corrupt in ses-03. The only relevant difference between the two sessions' fieldmap
acquisitions is the number of slices:

- ses-01 fmap: `num_slices: 60` (acquired 2025-08-05)
- ses-03 fmap: `num_slices: 51` (acquired 2025-08-19)

Hypothesis: the coregistration is actually correct; only the reportlet rendering path
handles a slice-count mismatch between `reference` (BOLD ref) and `moving` (fieldmap
magnitude) badly. The fix, if so, is localized to the report-generation workflow in
`fmriprep`, `sdcflows`, or `niworkflows`.

## Goals

1. Reproduce the broken alignment figure in the latest fmriprep release (25.2.5, March 10 2026).
2. Demonstrate that the underlying coregistration is correct (fsleyes overlay with
   fmriprep's own `from-fmap_to-boldref` transform applied).
3. File a GitHub issue against the correct upstream repo (`fmriprep`, `sdcflows`, or
   `niworkflows`, TBD after root-cause).
4. Submit a minimal PR with a unit test covering the buggy path.
5. Keep the production `neuro_workflow` codebase clean: only land changes that are
   generally useful (the `--output-dir` flag on the fmriprep pipeline), not one-off
   scripts.

## Non-Goals

- Re-running fmriprep on all rdoc subjects or sessions.
- Modifying the production `derivatives/fmriprep_25.2.0` on Oak.
- Investigating whether the 51-vs-60 slice fieldmap acquisition itself was a scanner-protocol
  error. That is a separate scan-protocol question, outside the scope of this fix.

## Approach (A): Reproduce → file issue → investigate → PR

Selected over (B) "code-first" and (C) "file issue against old run" because nipreps
maintainers expect reproduction on latest before triaging.

## Section 1 — Sample registration + BIDS filter

1. Add `subjects_rdoc.txt` at repo root containing one line: `s8` (committed).
2. Register dataset:
   ```
   uv run neuro-run add-dataset rdoc \
     --bids-dir /oak/stanford/groups/russpold/data/rdoc_grant/rdoc_fmri_bids \
     --subjects-file subjects_rdoc.txt \
     --partition russpold \
     --mail-user logben@stanford.edu
   ```
3. BIDS filter file at `config/bids_filters/rdoc_s8_stroop.json` (committed):
   ```json
   {
     "fmap": {"session": ["01", "03"]},
     "bold": {"session": ["01", "03"], "task": "stroop"},
     "t1w": {"session": "01"}
   }
   ```
   Task choice: `stroop` — shortest at 243 TRs in both sessions.

## Section 2 — Output layout + FreeSurfer reuse

- Output root (scratch, throwaway): `/scratch/users/logben/fmriprep_bug_repro/`
- Output derivatives: `/scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5`
- Work dir: `/scratch/users/logben/fmriprep_bug_repro/work`
- FreeSurfer reuse: both 25.2.0 and 25.2.5 ship FreeSurfer 7.3.2 build 20220804 (verified
  via the 25.2.0 and 25.2.4 SIFs; CHANGES show no FS bump between 25.2.0 and 25.2.5).
  Copy (not symlink):
  ```
  cp -r /oak/.../fmriprep_25.2.0/sourcedata/freesurfer \
        /scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sourcedata/
  ```

## Section 3 — `--output-dir` flag on fmriprep pipeline

The existing `fmriprep.sbatch` template hardcodes derivatives path inside the BIDS bind
mount. Add a new CLI flag to allow writing elsewhere.

**Python change** (`src/neuro_workflow/pipelines/fmriprep.py`):

```python
# add_cli_args:
parser.add_argument("--output-dir", default=None,
    help="Output derivatives root (default: <bids_dir>/derivatives)")

# build_context:
if args.output_dir:
    output_host = args.output_dir
    output_bind_line = f"-B {output_host}:/out \\"
    output_container = "/out"
else:
    output_host = f"{dataset_config['bids_dir']}/derivatives"
    output_bind_line = ""
    output_container = "/data/derivatives"
log_dir = f"{output_host}/fmriprep_{args.version}/logs"
```

**Template change** (`src/neuro_workflow/templates/fmriprep.sbatch`):

- Add `{output_bind_line}` line next to `{config_bind_line}`.
- Change `/data/derivatives/fmriprep_{fmriprep_version}` →
  `{output_container}/fmriprep_{fmriprep_version}`.

**Default behavior unchanged** when `--output-dir` not passed (existing discovery/validation
pipelines keep producing identical sbatch).

**Tests:** add `tests/pipelines/test_fmriprep.py` with two render tests — one with
`--output-dir`, one without — asserting the rendered sbatch has the correct bind line
and derivatives path.

## Section 4 — Pre-pull image + submission

Pre-pull the 25.2.5 image from a compute node (avoids login-node flakiness):
```
sbatch -p russpold --mem=8G --time=00:30:00 \
  --wrap "apptainer pull /home/groups/russpold/singularity_images/fmriprep_25.2.5.sif docker://nipreps/fmriprep:25.2.5"
```

Submit the reproduction job:
```
uv run neuro-run submit fmriprep rdoc \
  --version 25.2.5 \
  --output-dir /scratch/users/logben/fmriprep_bug_repro \
  --bids-filter-file config/bids_filters/rdoc_s8_stroop.json \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsnative func anat" \
  --fmriprep-args "--notrack --skip-bids-validation" \
  --time 04:00:00 --mem-per-cpu-gb 8 --nthreads 8
```

`--notrack` opts out of telemetry. `--skip-bids-validation` skips the validator (the BIDS
dataset has already been validated upstream; this avoids burning time on it for a repro run).

## Section 5 — Draft issue + alignment verification

Draft stored at `work/fmriprep_issue_draft.md` (gitignored). Not filed until user approves.

**Real-alignment verification procedure** (two-step because exact output filenames depend
on what fmriprep emits):

1. Inventory:
   ```
   ls /scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sub-s8/ses-03/{fmap,func,xfm}/
   ls /scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sub-s8/ses-01/{fmap,func,xfm}/
   ```
   Expected outputs: `desc-coreg_boldref.nii.gz`, `desc-magnitude_fieldmap.nii.gz`, and an
   xfm like `from-fmap_to-boldref_mode-image_xfm.txt`. Fill exact filenames into step 2
   after inventory.

2. Apply the published transform and overlay in fsleyes:
   ```
   apptainer exec /home/groups/russpold/singularity_images/neuro_workflow.sif \
     antsApplyTransforms -d 3 \
       -i <fmap_magnitude.nii.gz> \
       -r <boldref.nii.gz> \
       -t <from-fmap_to-boldref_xfm> \
       -o /tmp/mag_in_boldref_space.nii.gz

   fsleyes <boldref.nii.gz> /tmp/mag_in_boldref_space.nii.gz \
     -cm red-yellow -a 50
   ```
   Screenshot both ses-01 and ses-03 overlays. If edges match in both, the coregistration
   itself is correct and the defect is in the reportlet, not the pipeline.

**Issue body will contain:**
- Title: "Fieldmap-to-BOLD alignment reportlet is corrupt when fieldmap has different slice count than BOLD reference"
- Reproduction steps (BIDS filter inline, fmriprep invocation)
- JSON sidecar diff (51 vs 60 slices)
- Two screenshots of the SVG reportlet (ses-01 good, ses-03 corrupt)
- Two fsleyes overlay screenshots (both sessions show correct alignment)
- Env info: fmriprep 25.2.5, FreeSurfer 7.3.2 build 20220804, Apptainer

## Section 6 — PR workflow

**Pre-work:**
1. `module load gh/2.88.1 && gh repo fork nipreps/fmriprep --clone=false`
2. Clone fork to `/scratch/users/logben/fmriprep_fork/`
3. Read `CONTRIBUTING.md` + `.github/PULL_REQUEST_TEMPLATE.md`, match their norms.
4. Branch `fix/fmap-boldref-report-<short-desc>` off `main` (exact name after root-cause).

**Investigation:**
- Likely reportlet locations (to be verified before writing code): `fmriprep/workflows/fieldmap/*`,
  `sdcflows/workflows/outputs.py`, `sdcflows/interfaces/reportlets.py`,
  `niworkflows/interfaces/reportlets/registration.py`.
- If root cause is in `sdcflows` or `niworkflows`, the issue + PR go to that repo instead.
  This branch decision happens after investigation, not now.
- grep for the reportlet class, trace how it handles mismatched slice counts between
  `reference` and `moving_image`, isolate the bug.

**Fix + test:**
- Write a unit test exercising the buggy path (small synthetic NIfTIs with mismatched slice
  counts → assert reportlet produces a sane SVG).
- Apply the minimal fix.
- Run the relevant test file locally before pushing.

**PR submission:**
- Draft PR description at `work/fmriprep_pr_description.md` first; user approves before
  any `gh pr create`.
- `git push -u fork <branch>`
- `gh pr create --repo <target-repo> --base main` with `Fixes #<issue-number>` and
  before/after reportlet screenshots.

## Risks & Open Questions

- **Output dir semantics inside the container.** If `--output-dir` points at a host path
  that's also reachable via the BIDS bind mount (unlikely here since scratch and Oak are
  different mounts), the two bind lines would both exist but `/out` takes precedence. Not
  a real risk for this use case.
- **FreeSurfer copy size.** `sourcedata/freesurfer/sub-s8/` can be several GB; scratch has
  capacity but confirm before `cp -r`.
- **Root cause may be in upstream repo.** Decided to defer the `fmriprep` vs `sdcflows` vs
  `niworkflows` branch decision until after investigation.
- **25.2.5 image pull.** First-ever pull on this system; if it fails, fall back to `25.2.4`
  for the repro and note the version deviation in the issue.

## Deliverables

1. `subjects_rdoc.txt` (committed)
2. `config/bids_filters/rdoc_s8_stroop.json` (committed)
3. `src/neuro_workflow/pipelines/fmriprep.py` — add `--output-dir` flag
4. `src/neuro_workflow/templates/fmriprep.sbatch` — plumb output bind + path
5. `tests/pipelines/test_fmriprep.py` — render tests for both modes
6. `work/fmriprep_issue_draft.md` (local only, gitignored)
7. `work/fmriprep_pr_description.md` (local only, gitignored)
8. (Eventually) GitHub issue + PR on the correct upstream repo
