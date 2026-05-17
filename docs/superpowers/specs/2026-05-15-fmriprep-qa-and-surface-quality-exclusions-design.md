# fmriprep QA + surface-quality exclusions — design

**Date:** 2026-05-15
**Status:** Draft, ready for review
**Scope:** Sub-project A of the next-week work plan. Run the existing `qa_report` on the validation cohort (discovery already done), identify subjects with high pre-fix Euler defects, attempt one round of SynthStrip + recon-all rerun + fmriprep re-derive + lev1 (surface only) + prep-mshbm redo, then encode unfixable subjects as exclusions and regenerate `EXCLUSIONS.md` to reflect every auto-exclude (motion, behavioral, surface) in one place.

Subsequent sub-projects (deferred):
- B. XCP-D evaluation
- C. Full surface-space lev1 rerun for the whole cohort (with the new fmriprep outputs from this sub-project as inputs for fixed subjects)
- D. Bayesian prevalence on lev1 contrasts overlaid on MSHBM dlabels

---

## Goals

1. Produce QA reports for both cohorts at canonical, BIDS-adjacent paths.
2. Triage subjects with pre-fix Euler defects above threshold; attempt to fix; iterate **once**.
3. Update `qc_decisions.tsv` to exclude unfixable subjects.
4. Recompile exclusions; regenerate `EXCLUSIONS.md` to mirror every auto-exclude decision (motion, behavioral, qc_decisions/surface_quality).
5. Clearly report which subjects were fixed vs. not, with quantitative pre/post counts.

## Non-goals

- New automated `surface_quality.py` generator (manual review via `qc_decisions.tsv` is sufficient at N=46).
- Second-round fix attempts (manual FreeSurfer edits, etc.) — out of scope.
- MNI- and T1w-space lev1 reruns — needed eventually, deferred to a separate sub-project.
- XCP-D evaluation — sub-project B.

---

## Output locations (BIDS-compliant — under derivatives)

| Cohort | qa_html output | Re-QA after fix |
|---|---|---|
| discovery | `/scratch/users/logben/discovery_bids/derivatives/qa_reports/` | `/scratch/users/logben/discovery_bids/derivatives/qa_reports_post_fix/` |
| validation | `/scratch/users/logben/validation_bids/derivatives/qa_reports/` | `/scratch/users/logben/validation_bids/derivatives/qa_reports_post_fix/` |

QA reports are derivatives, so they live under `derivatives/`. This keeps BIDS validation status intact (the root BIDS dir stays clean). Discovery's existing `qa_html_discovery` will be regenerated under the new canonical path during this sub-project.

## Pinned versions (no bumps)

- fmriprep: **25.2.4** (current — do NOT upgrade)
- FreeSurfer: **8.1.0** (current — do NOT upgrade)
- SynthStrip: ship with FreeSurfer 8.1.0

The fix attempt uses the SAME fmriprep + FreeSurfer versions as the original recon. We're investigating whether a different SKULL STRIP (SynthStrip vs the default FreeSurfer skull strip used by recon-all) improves the segmentation, not whether a newer tool version helps.

## Thresholds

- **Pre-fix Euler holes > 100** → triggers a fix attempt (SynthStrip + recon-all rerun → fmriprep re-derive).
- **Post-fix Euler holes > 100** → exclude via `qc_decisions.tsv` with reason `surface_quality: NNN pre-fix → NNN post-fix Euler defects (fix attempt failed)`.
- **Mean FD, %TRs above thresh, std_dvars** — already encoded in `motion.py` generator; no threshold change. Just ensure they appear in `EXCLUSIONS.md`.

## Components

### 0. Diagnose existing recon for high-hole subjects (do this FIRST)

Before attempting any fix, investigate WHY the existing recon produced bad surfaces. `scripts/diagnose_high_hole_subjects.py`:

For each subject with pre-fix holes > 100:
1. Read `$SUBJECTS_DIR/<fs_subj>/scripts/recon-all.log` — scan for warnings, retries, anomalies.
2. Read `$SUBJECTS_DIR/<fs_subj>/scripts/recon-all-status.log` — confirm clean termination.
3. Check skull-strip QC: load `brainmask.mgz` + `T1.mgz` snapshots (if `freesurfer.png` exists from fmriprep's reports). Note any obvious skull-strip failures.
4. Read fmriprep work-dir `fmriprep_25_2_wf/sub-X_*_wf/anat_fit_wf/` for SDC/recon warnings if available.
5. Summarize per-subject in `docs/SURFACE-DIAGNOSIS.md`: likely root cause (motion / bad skull strip / anatomical anomaly / unknown), evidence pointers.

This step gates the SynthStrip rerun decision — if diagnosis reveals a non-skull-strip issue (e.g., motion artifact in T1w), SynthStrip won't help and we exclude immediately rather than burn compute on a doomed fix attempt.

### 1. Validation qa_report run

```
uv run python scripts/qa_report.py \
    --fmriprep-dir /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4 \
    --output-dir /scratch/users/logben/validation_bids/qa_html
```

Also re-run for discovery at the new canonical path (replaces `qa_html_discovery`).

### 2. Surface-quality triage helper

`scripts/triage_surface_quality.py` — reads `cohort.tsv` from both cohorts' qa_html dirs, prints a markdown table of subjects with `pre_fix_holes > THRESHOLD` (default 100). Output: stdout + optional `--write-md PATH`.

Columns: subject, lh_holes, rh_holes, mean_holes, recommendation.

### 3. SynthStrip + recon-all rerun helper (conditional on diagnosis)

Only run for subjects whose diagnosis (Component 0) suggests skull-stripping is the likely cause. `scripts/synthstrip_recon_all.sbatch` — per-subject sbatch:
1. `mri_synthstrip -i T1w.nii.gz -o brain_synthstrip.nii.gz` — alternative skull strip (FreeSurfer 8.1.0 ships SynthStrip).
2. `recon-all -all -i brain_synthstrip.nii.gz -subjid <SUBJ>_fix -sd <NEW_SD>` — full recon with the better skull strip. SAME FreeSurfer version (8.1.0) as the original.
3. Output to `<bids_root>/derivatives/freesurfer_fix/sub-X_ses-N/` (separate from the original FreeSurfer dir; parallel reconstruction, not an overwrite).
4. After completion: run `mris_euler_number` on `lh.orig.nofix` and `rh.orig.nofix` of the new recon and log the new hole counts. This is the fix-verification metric — used in Component 5's re-QA and the SURFACE-FIX-STATUS table.

### 4. fmriprep re-run for fixed subjects

`uv run neuro-run submit fmriprep <cohort> --version 25.2.4 ...` filtered to the fix-list subjects, with `--fs-subjects-dir` pointing at `derivatives/freesurfer_fix/`. Output to `derivatives/fmriprep_25.2.4_post_fix/` so we don't clobber existing outputs while iterating.

Per-subject runtime estimate: ~3-6h (anat-cached portions skipped).

### 5. Re-QA on fixed fmriprep outputs

```
uv run python scripts/qa_report.py \
    --fmriprep-dir /scratch/users/logben/<cohort>_bids/derivatives/fmriprep_25.2.4_post_fix \
    --output-dir /scratch/users/logben/<cohort>_bids/qa_html_post_fix \
    --subjects <fix-list>
```

### 6. Conditional propagation: lev1 (surface only) + prep-mshbm

For each subject confirmed fixed:
- `uv run neuro-run submit lev1 <cohort> --space surface ...` filtered to that subject, pointing at `fmriprep_25.2.4_post_fix`.
- `uv run neuro-run submit prep-mshbm <cohort> ...` similarly.
- MNI/T1w lev1 reruns are explicitly deferred.

### 7. qc_decisions.tsv updates

Append rows for unfixable subjects:
```
sub-sXX    -    -    -    exclude    surface_quality: 324 pre-fix → 310 post-fix (fix failed)
```

### 8. compile-exclusions

Re-run for both cohorts. Updates `~/.neuro_workflow/exclusions/{discovery,validation}/compiled_exclusions.json` (committed lockfiles).

### 9. EXCLUSIONS.md regeneration

`scripts/render_exclusions_md.py` (new):
- Reads `compiled_exclusions.json` for both cohorts.
- Groups by source (`motion`, `behavioral`, `qa_decisions`).
- Within each source, lists scan-level and subject-level exclusions with reason strings.
- Output: replaces existing `docs/EXCLUSIONS.md` with auto-generated content (commented as such; manual notes preserved in a separate trailing section).

### 10. Fix-status report

`scripts/render_surface_fix_status.py` (new): produces `docs/SURFACE-FIX-STATUS.md` table:

| Subject | Pre-fix LH/RH/Mean | Post-fix LH/RH/Mean | Decision |
|---|---|---|---|
| sub-s03 | 184/140/162 | 12/8/10 | KEEP (fixed) |
| sub-sXX | 220/195/207 | 198/170/184 | EXCLUDE (fix failed) |

Surfaces the diagnostic outcome of every fix attempt.

---

## Data flow

```
[both cohorts] fmriprep_25.2.4 → qa_report → derivatives/qa_reports/ (cohort.tsv, cohort.html, subjects/*.html)
                                                ↓
                                triage_surface_quality.py
                                  → candidate-list (pre-fix holes > 100)
                                                ↓
                              diagnose_high_hole_subjects.py
                                  → SURFACE-DIAGNOSIS.md
                                  → fix-list (skull-strip suspected)
                                  → straight-exclude list (other causes)
                                                ↓
                          synthstrip_recon_all.sbatch (per fix-list subject)
                                  → freesurfer_fix/
                                                ↓
                          fmriprep rerun --fs-subjects-dir freesurfer_fix/
                                  → fmriprep_25.2.4_post_fix/
                                                ↓
                                qa_report --fmriprep-dir fmriprep_25.2.4_post_fix
                                  → qa_html_post_fix
                                                ↓
                  render_surface_fix_status.py → docs/SURFACE-FIX-STATUS.md
                                  ↓ (per subject)
                  ┌─────────────┴──────────────┐
              fixed (≤100)             unfixed (>100)
                  ↓                           ↓
        lev1 surface rerun         qc_decisions.tsv row
        prep-mshbm rerun           "exclude, surface_quality:..."
                                            ↓
                              compile-exclusions both cohorts
                                            ↓
                        compiled_exclusions.json (committed)
                                            ↓
                      render_exclusions_md.py → docs/EXCLUSIONS.md
```

## Tests

- `tests/scripts/test_triage_surface_quality.py` — synthetic cohort.tsv with mixed hole counts, assert correct subjects flagged at threshold.
- `tests/scripts/test_render_exclusions_md.py` — synthetic `compiled_exclusions.json`, assert markdown output groups by source and includes counts/reasons.
- `tests/scripts/test_render_surface_fix_status.py` — synthetic pre/post cohort.tsv pairs, assert status table reflects KEEP vs EXCLUDE per threshold.

Operational verification (post-merge, manual):
- Run validation qa_report; spot-check 2-3 subject pages.
- Run triage; confirm flagged subjects match manual scan.
- Run SynthStrip + recon-all on one fix candidate; confirm `recon-all.log` finishes; compare new vs old hole count.
- Spot-check `docs/EXCLUSIONS.md` reflects current motion + behavioral exclusions plus any new surface ones.

---

## Open questions / decisions deferred

1. **Threshold tuning** — using 100 from Reuter/Rosen. If discovery's QA reveals subjects clustered around the threshold, may revisit.
2. **What "fixed" means quantitatively** — using post-fix holes ≤ 100. Could tighten to ≤ 50 if reviewer prefers conservative; revisit after first cohort run.
3. **EXCLUSIONS.md format** — generator output replaces the current hand-maintained version. Existing manual notes go in a `## Manual notes (preserved across regenerations)` section that the generator leaves alone.

## Scope discipline

- Don't add new exclusion sources beyond what we know is needed.
- Don't redesign `motion.py` or `behavioral.py` generators; they already exist and work.
- Don't refactor `qa_report.py` internals; just run it and consume its existing outputs.
- Don't propagate MNI/T1w lev1 — that's a separate sub-project.
