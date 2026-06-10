# sub-s03 T1w replacement + fmriprep rerun — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substitute sub-s03's bad ses-13 T1w with a known-good conversion of the same DICOM, then rerun fmriprep on s03 end-to-end so a fresh FreeSurfer recon and all BOLD-derived outputs are computed against the good anatomical.

**Architecture:** Single NIfTI replacement in the scratch BIDS dataset, then a vanilla fmriprep rerun. No FS transplant, no sed substitution, no code changes — just an artifact swap and a job submission.

**Tech Stack:** bash, datalad/git-annex (for unlocking BIDS files if needed), apptainer (for fmriprep), nibabel (verification), SLURM (russpold partition).

**Spec:** `docs/superpowers/specs/2026-05-20-sub-s03-import-oak-t1w-and-freesurfer-design.md`

---

## File map

**Modified on scratch BIDS dataset (artifact replacement, not code):**
- `/scratch/users/logben/discovery_bids/sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz` — replace NIfTI content with the good conversion

**Deleted from scratch fmriprep dir (stale outputs):**
- `/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03/`
- `/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03_*.html`
- `/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_ses-13/`
- `/scratch/users/logben/work/fmriprep_discovery_25.2.4/single_subject_s03_wf/` (if present)

No git-tracked files are modified.

---

## Task 1: Preflight checks

- [ ] **Step 1.1: Confirm source T1w exists and matches expected checksum**

```bash
ls -la /oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/sub-s03/ses-05/anat/sub-s03_ses-05_run-1_T1w.nii.gz
md5sum /oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/sub-s03/ses-05/anat/sub-s03_ses-05_run-1_T1w.nii.gz
```
Expected: file exists, md5 = `9bf100862c69489d71d6e19a1cbc228e`.

If md5 differs, STOP — the source file changed and the plan assumptions need updating.

- [ ] **Step 1.2: Determine whether scratch ses-13 T1w is git-annexed**

```bash
ls -la /scratch/users/logben/discovery_bids/sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz
```
Expected: shows whether file is a symlink (annexed) or a real file.

If output shows `-> .git/annex/objects/...`, the file is annexed → we need `datalad unlock` in Task 2. If output shows a regular file, plain `cp` overwrite is fine.

- [ ] **Step 1.3: Snapshot current QA metrics for before/after comparison**

```bash
cp /scratch/users/logben/discovery_bids/derivatives/qa_reports/cohort.tsv \
   /tmp/cohort_before_s03_t1w_replace.tsv
cat /tmp/cohort_before_s03_t1w_replace.tsv
```
Expected: 5 rows; sub-s03 row shows `fs_euler_mean=-163`, `scans_flagged_outputs=57`.

---

## Task 2: Replace the ses-13 T1w

- [ ] **Step 2.1: Unlock the BIDS file if annexed**

If Step 1.2 showed the file is a symlink into `.git/annex`:
```bash
cd /scratch/users/logben/discovery_bids
module load uv
uv run datalad unlock sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz
```
Expected: `unlock(ok): ...`.

If file was already a regular file, skip this step.

- [ ] **Step 2.2: Overwrite the ses-13 T1w NIfTI**

```bash
cp /oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/sub-s03/ses-05/anat/sub-s03_ses-05_run-1_T1w.nii.gz \
   /scratch/users/logben/discovery_bids/sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz
```
Expected: silent success.

- [ ] **Step 2.3: Verify md5 matches expected**

```bash
md5sum /scratch/users/logben/discovery_bids/sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz
```
Expected: `9bf100862c69489d71d6e19a1cbc228e`.

If md5 differs, STOP — the cp may have been interrupted; re-run Step 2.2.

- [ ] **Step 2.4: Verify NIfTI loads and has expected orientation**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run python -c "
import nibabel as nib
img = nib.load('/scratch/users/logben/discovery_bids/sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz')
print('shape:', img.shape)
print('voxel_size:', img.header.get_zooms())
"
```
Expected: shape `(512, 512, 230)`, voxel `(0.5, 0.5, 0.8)`.

- [ ] **Step 2.5: Re-save under git-annex if it was originally annexed**

If Step 2.1 ran `datalad unlock`:
```bash
cd /scratch/users/logben/discovery_bids
module load uv
uv run datalad save -m "Update s03 ses-13 T1w" sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz
```
Expected: `save(ok): ...`.

Otherwise skip.

---

## Task 3: Wipe stale s03 fmriprep outputs

- [ ] **Step 3.1: List what's about to be deleted (sanity check)**

```bash
ls -d /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03 2>/dev/null
ls /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03_*.html 2>/dev/null
ls -d /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_ses-13 2>/dev/null
ls -d /scratch/users/logben/work/fmriprep_discovery_25.2.4/single_subject_s03_wf 2>/dev/null
```
Expected: paths printed (from the prior bad rerun).

- [ ] **Step 3.2: Delete fmriprep subject output dir + HTML reports**

```bash
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03
rm -f  /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03_anat.html
rm -f  /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03_ses-*_func.html
```
Expected: silent success.

- [ ] **Step 3.3: Delete the stale FreeSurfer subject (recon-all will re-create)**

```bash
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_ses-13
```
Expected: silent success.

- [ ] **Step 3.4: Delete the stale work dir for s03 if it exists**

```bash
WORKDIR=/scratch/users/logben/work/fmriprep_discovery_25.2.4/single_subject_s03_wf
if [[ -d "$WORKDIR" ]]; then
  rm -rf "$WORKDIR"
  echo "Removed $WORKDIR"
else
  echo "No s03 work dir found at $WORKDIR — skipping"
fi
```
Expected: prints status.

- [ ] **Step 3.5: Verify clean state**

```bash
ls /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/ | grep -E "^sub-s03"
ls /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/ | grep s03
```
Expected: first command returns empty (no sub-s03 entries); second returns empty (no FS subjects for s03).

---

## Task 4: Submit fmriprep rerun for sub-s03

- [ ] **Step 4.1: Create subjects file**

```bash
echo "s03" > /tmp/subjects_s03_only.txt
cat /tmp/subjects_s03_only.txt
```
Expected: prints `s03`.

- [ ] **Step 4.2: Confirm BIDS-view symlink dir is current**

The fmriprep preflight builds a `derivatives/fmriprep_25.2.4_input/` view that respects `.bidsignore`. Since we only changed file content (same path), the existing symlink should still resolve to the new T1w. Verify:

```bash
ls -la /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input/sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz
md5sum /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input/sub-s03/ses-13/anat/sub-s03_ses-13_acq-SagMPRAGE_run-1_T1w.nii.gz
```
Expected: symlink resolves to the BIDS path; md5 = `9bf100862c69489d71d6e19a1cbc228e`.

If the view dir or symlink is missing, rebuild it:
```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run python scripts/fmriprep_preflight.py discovery
```

- [ ] **Step 4.3: Confirm `.bidsignore` does NOT bidsignore the ses-13 T1w**

```bash
cat /scratch/users/logben/discovery_bids/.bidsignore | grep -i s03
```
Expected: lines for ses-01 MPRAGEPromo and ses-05 SagMPRAGE; nothing for ses-13.

- [ ] **Step 4.4: Preview the rendered sbatch (do not submit yet)**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run neuro-run show fmriprep discovery \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb 24 --time 7-00:00:00 \
  --array-throttle 1 \
  --subjects-file /tmp/subjects_s03_only.txt
```
Expected: prints sbatch script. Verify:
- `--array=1-1%1` (one subject)
- `--cpus-per-task=8`, `--mem-per-cpu=24G`, `--time=7-00:00:00`
- Binds include `fmriprep_25.2.4_input:/data` and `discovery_bids/derivatives:/out`

If anything looks wrong, STOP and investigate.

- [ ] **Step 4.5: Submit the job**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run neuro-run submit fmriprep discovery \
  --version 25.2.4 \
  --bids-dir-override /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_input \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage6 fsnative T1w func" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k" \
  --nthreads 8 --mem-per-cpu-gb 24 --time 7-00:00:00 \
  --array-throttle 1 \
  --subjects-file /tmp/subjects_s03_only.txt
```
Expected: `Submitted batch job <JID>`. Record `<JID>`.

- [ ] **Step 4.6: Confirm the job is in the queue**

```bash
squeue -u logben
```
Expected: the new fmriprep job is listed as `PD` or `R`.

---

## Task 5: Monitor fmriprep run

**Blocking on SLURM — track over ~48 h.**

- [ ] **Step 5.1: Periodic check-ins until completion**

```bash
squeue -u logben | grep <JID>
sacct -j <JID> --format=JobID,State,ExitCode,Elapsed
```

- [ ] **Step 5.2: Once complete, confirm exit code 0**

```bash
sacct -j <JID> --format=JobID,State,ExitCode,Elapsed,MaxRSS
```
Expected: `State=COMPLETED`, `ExitCode=0:0`. Note total Elapsed (expect ~48 h).

If `FAILED`, inspect the log:
```bash
ls -tr /home/users/logben/neuro_workflow/logs/ | tail -5
tail -200 <log_path>
```

---

## Task 6: Verify the rerun produced clean surfaces + complete outputs

- [ ] **Step 6.1: Confirm aseg.stats holes are good**

```bash
grep -iE "Holes" /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_ses-13/stats/aseg.stats | head
```
Expected:
```
# Measure lhSurfaceHoles, ..., prior to fixing, 5, unitless     # or similar small number
# Measure rhSurfaceHoles, ..., prior to fixing, 8, unitless
# Measure SurfaceHoles, ..., prior to fixing, 13, unitless
```
Total holes should be ≤ 20. If still > 100, the substitution didn't take or the new T1w also produces bad surfaces — investigate.

- [ ] **Step 6.2: Confirm preproc BOLD is 327 TRs (trimmed convention)**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run python -c "
import nibabel as nib
img = nib.load('/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03/ses-02/func/sub-s03_ses-02_task-cuedTS_run-1_desc-preproc_bold.nii.gz')
print('shape:', img.shape)
"
```
Expected: shape last dim = 327. If different, STOP.

- [ ] **Step 6.3: Confirm required output spaces are present for one scan**

```bash
ls /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03/ses-02/func/ \
  | grep "task-cuedTS_run-1" | sort
```
Expected file list includes:
- `*_desc-preproc_bold.nii.gz` (T1w native)
- `*_space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz`
- `*_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz`
- `*_space-T1w_desc-preproc_bold.nii.gz`
- `*_hemi-L_space-fsaverage6_bold.func.gii` + `*_hemi-R_*`
- `*_hemi-L_space-fsnative_bold.func.gii` + `*_hemi-R_*`
- `*_space-fsLR_den-91k_bold.dtseries.nii`
- `*_desc-confounds_timeseries.tsv`

Missing any of these means an `--output-spaces` mismatch; investigate.

- [ ] **Step 6.4: Re-run QA cohort report**

```bash
sbatch scripts/run_qa_report.sbatch \
  --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
  --output-dir /scratch/users/logben/discovery_bids/derivatives/qa_reports
```
Expected: `Submitted batch job <QA_JID>`. ~5 h runtime with reliability movies.

- [ ] **Step 6.5: Once QA completes, diff against baseline**

```bash
diff /tmp/cohort_before_s03_t1w_replace.tsv \
     /scratch/users/logben/discovery_bids/derivatives/qa_reports/cohort.tsv
```
Expected: only the sub-s03 row differs. The new s03 row should show:
- `fs_euler_mean` close to `-13.0` (was `-163.0`)
- `fs_holes_mean` close to `6.5` (was `82.5`)
- `scans_flagged_outputs` = `0` (was `57`)
- `outlier` = `False` (was `True`)

If the new values don't show this improvement, investigate.

---

## Task 7: Commit the spec + plan

- [ ] **Step 7.1: Commit the spec and plan files (no other doc changes)**

```bash
cd /home/users/logben/neuro_workflow
git add docs/superpowers/specs/2026-05-20-sub-s03-import-oak-t1w-and-freesurfer-design.md \
        docs/superpowers/plans/2026-05-20-sub-s03-import-oak-t1w-and-freesurfer.md \
        scripts/audit_flywheel_t1w.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
plan: replace sub-s03 ses-13 T1w and rerun fmriprep

The bidsified ses-13 T1w produces 165 FreeSurfer holes; a known-good
conversion of the same scan exists elsewhere on disk and produces 13.
Plan: replace the NIfTI content in place, wipe stale fmriprep outputs
for s03, rerun fmriprep end-to-end.

Adds scripts/audit_flywheel_t1w.py — a Flywheel inventory tool for
anatomical acquisitions per subject (used to confirm the available
T1w acquisitions for s03 during planning).
EOF
)"
```
Expected: commit succeeds.

- [ ] **Step 7.2: Verify clean working tree**

```bash
git status
```
Expected: `nothing to commit, working tree clean` (or only unrelated unstaged files).

---

## Success criteria (recap from spec)

- fmriprep completes with exit 0 for sub-s03
- `aseg.stats` for `sub-s03_ses-13` shows ≤ 20 total surface holes
- All expected output spaces present (no `scans_flagged_outputs` flag)
- BOLD outputs at 327 TRs (trimmed convention preserved)
- QA cohort dashboard shows s03 no longer an outlier

Once these are met, downstream s03 reruns (lev1-surface, prep-mshbm) become
unblocked — they are scoped separately and not part of this plan.
