# sub-s03 rescue T1w integration — design

**Date:** 2026-05-15
**Status:** Draft, ready for review
**Scope:** Sub-project I1. Integrate the rescue T1w from Flywheel session 25210 (acquired 2022-05-24 because the original SagMPRAGE produced FreeSurfer surfaces with 162 mean Euler defects) into sub-s03's BIDS dataset as ses-13, .bidsignore the two stale T1ws, re-run fmriprep on sub-s03 only, verify the new surfaces are clean, then propagate downstream to lev1-surface and prep-mshbm.

Also resolves the 14-vs-12 session count discrepancy for sub-s03: 14 Flywheel sessions → 1 reassigned to s10 (22752) → 1 misclassified as excluded (25210, the rescue T1w) → 12 in BIDS. After this fix, BIDS will have 13 sessions for sub-s03.

Subsequent sub-projects (deferred):
- I2. Cohort-wide Flywheel↔BIDS audit for the other 45 subjects.
- I4. Bidsify code hardening to surface candidate-exclude sessions for human review before they're skipped.

---

## Goals

1. Phase 1 (audit): produce a markdown report comparing sub-s03's Flywheel sessions and acquisitions against current BIDS contents. Confirm what ses-25210 actually contains (T1w only vs other scans). Surface any other discrepancies for sub-s03.
2. Phase 2 (integrate): un-exclude session 25210 in `pipeline_config.json`, re-run bidsify for sub-s03 only, .bidsignore the stale T1ws (ses-01 MPRAGEPromo, ses-05 SagMPRAGE), re-run fmriprep on sub-s03, verify new surface quality, and re-run lev1-surface + prep-mshbm for sub-s03.
3. Document the fix path with quantitative pre/post hole counts in `docs/SURFACE-FIX-STATUS.md` (created by the prior sub-project, append a row).

## Non-goals

- Cohort-wide Flywheel↔BIDS audit (I2).
- Bidsify code refactors / hardening (I4).
- MNI/T1w-space lev1 reruns for sub-s03 (same scope decision as sub-project A — deferred).
- Reprocessing any of the other 4 discovery subjects (they're already clean).

---

## Output locations

| Artifact | Path |
|---|---|
| Audit report | `docs/AUDIT-sub-s03.md` |
| Updated config | `config/pipeline_config.json` (edit s03/25210 entry) |
| Updated BIDS | `/scratch/users/logben/discovery_bids/sub-s03/ses-13/anat/*_T1w.nii.gz` |
| Updated .bidsignore | `/scratch/users/logben/discovery_bids/.bidsignore` (append stale T1w paths) |
| New fmriprep outputs | `/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03/` (overwrite) |
| Re-QA report | `/scratch/users/logben/discovery_bids/derivatives/qa_reports/` (re-render after fmriprep) |
| Fix-status table | `docs/SURFACE-FIX-STATUS.md` (append sub-s03 row) |

## Pinned versions

- fmriprep: **25.2.4** (no bump).
- FreeSurfer: whatever fmriprep 25.2.4's apptainer image bundles (7.3.2 per the prior recon logs). Same as the rest of the cohort.

---

## Components

### Phase 1: Audit

#### 1. `scripts/audit_subject_flywheel_vs_bids.py`

New script. Inputs: subject ID, BIDS dir, Flywheel project name. Output: markdown report.

For the given subject:
1. Connect to Flywheel via `flywheel.Client()` (the existing bidsify code's pattern).
2. List subject's sessions in Flywheel, accounting for subject aliases from `pipeline_config.json` (e.g., `s29-2 → s29`).
3. For each session, list acquisitions (label, timestamp, file types).
4. Walk `<bids_dir>/<subject>/ses-*/` and list scans.
5. Cross-reference using session timestamps to map Flywheel sessions → BIDS session numbers.
6. Emit a markdown table with one row per Flywheel session showing: Flywheel session label, timestamp, BIDS session (or "EXCLUDED" / "MISSING"), acquisition counts (n_T1w, n_T2w, n_BOLD, n_fieldmap), notes.
7. Highlight rows where bidsified count < Flywheel count for any scan type.

Driven by `pipeline_config.json` for aliases and session overrides.

### Phase 2: Integrate

#### 2. `config/pipeline_config.json` edit

Change s03/25210 entry from `{"exclude": true, "reason": "Empty/test session..."}` to `{"note": "Rescue T1w session — original SagMPRAGE produced bad recon (162 Euler defects); this session re-acquires the anat"}`. Drop the `exclude` field entirely so bidsify processes it normally.

The audit (Phase 1) confirms what acquisitions are in 25210; if it has only a T1w, no other config changes needed. If it has additional scans, the existing bidsify machinery will pick them up.

#### 3. Bidsify rerun for sub-s03 only

```bash
uv run neuro-run submit bidsify discovery --subjects s03 --overwrite --time 02:00:00 --mem-gb 16
```

Existing `--subjects` flag produces a suffixed metadata file (e.g., `reconciliation_rerun-s03.json`) to avoid overwriting full-run logs (per CLAUDE.md). After completion:
- Expect `<bids>/sub-s03/ses-13/` to appear (chronologically — bidsify sorts by Flywheel timestamp).
- Verify the rescue T1w lives at `<bids>/sub-s03/ses-13/anat/sub-s03_ses-13_*_T1w.nii.gz`.
- Verify trim_bold.py was re-run on any BOLD scans (sub-s03's other sessions should have already been trimmed; ses-13 BOLDs if any need trimming).

#### 4. `.bidsignore` update

Append to `/scratch/users/logben/discovery_bids/.bidsignore`:

```
sub-s03/ses-01/anat/*MPRAGEPromo*
sub-s03/ses-05/anat/*SagMPRAGE*
```

These hide the stale T1ws from fmriprep so it auto-selects the ses-13 rescue T1w. Per `docs/EXCLUSIONS.md` convention (sample-specific .bidsignore entries), document this addition in the EXCLUSIONS.md notes section.

#### 5. fmriprep rerun for sub-s03 only

Wipe stale outputs first to ensure a clean recon (the FreeSurfer subjects dir is keyed by `sub-X_ses-N` and we want to redo with the new ses-13 T1w):

```bash
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_*
rm -rf /scratch/users/logben/work/fmriprep_discovery_25.2.4/fmriprep_25_2_wf/sub_s03_*
```

Submit:

```bash
uv run neuro-run submit fmriprep discovery --version 25.2.4 \
    --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage:den-41k fsnative T1w func" \
    --fmriprep-args "--use-syn-sdc --me-output-echos --bold2anat-init t2w" \
    --array-throttle 1 --time 12:00:00
```

The dataset's `subjects_file` should be temporarily limited to just s03 (e.g., a one-line `subjects_phase1_s03.txt` already exists per memory). Alternatively, add an ephemeral `discovery_s03_rescue` dataset entry to `~/.neuro_workflow/datasets.json` pointing at a single-subject file.

Per-subject runtime estimate: ~6-12h (full recon, not anat-cached, because the T1w changed).

#### 6. Re-QA on the new fmriprep output

```bash
sbatch --wrap='module load uv && cd /home/users/logben/neuro_workflow && uv run python scripts/qa_report.py \
    --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
    --output-dir /scratch/users/logben/discovery_bids/derivatives/qa_reports \
    --subjects sub-s03 --no-reliability-movies' \
    -J qa_s03_rescue -p russpold -t 01:00:00 --mem=16G \
    -o /scratch/users/logben/discovery_bids/derivatives/qa_reports/qa_s03_rescue-%j.out
```

Inspect `cohort.tsv`; the sub-s03 row should now show `fs_holes_mean` in single digits or low teens (matching the other 4 discovery subjects).

#### 7. Append sub-s03 row to `docs/SURFACE-FIX-STATUS.md`

```
| Subject | Pre mean holes | Post mean holes | Decision |
|---|---|---|---|
| sub-s03 | 162 | <new> | KEEP (rescue T1w from ses-13) |
```

If post holes > 100, fall back to the exclusion path from sub-project A: add sub-s03 to `qc_decisions.tsv` and recompile.

#### 8. Downstream propagation for sub-s03

If hole count is good (≤ ~30):

```bash
# lev1 surface (single subject)
uv run neuro-run submit lev1 discovery --subjects s03 \
    --space surface --time 06:00:00 ...
# prep-mshbm (single subject)
uv run neuro-run submit prep-mshbm discovery --subjects s03 \
    --rest-only --include-task-bold --surface-fwhm 2 \
    --output-dir /scratch/users/logben/mshbm_inputs_discovery_v8_s03_rescue \
    --time 12:00:00
```

MNI/T1w lev1 reruns are explicitly deferred to a future sub-project.

---

## Data flow

```
audit_subject_flywheel_vs_bids.py s03
  → docs/AUDIT-sub-s03.md (human review; confirm ses-25210 has the rescue T1w)
                                              ↓
pipeline_config.json: s03/25210 exclude=false
                                              ↓
neuro-run submit bidsify discovery --subjects s03 --overwrite
  → discovery_bids/sub-s03/ses-13/anat/*_T1w.nii.gz (new)
                                              ↓
discovery_bids/.bidsignore: append stale T1w paths
                                              ↓
wipe fmriprep_25.2.4/sub-s03 + freesurfer/sub-s03_* + work/.../sub_s03_*
                                              ↓
neuro-run submit fmriprep discovery --subjects s03
  → fmriprep_25.2.4/sub-s03 (full recon with ses-13 T1w)
                                              ↓
qa_report --subjects sub-s03 → confirm fs_holes_mean ≤ ~30
                                              ↓
  ┌─ if holes good ─┐                    ┌─ if still bad ─┐
lev1 surface rerun                    qc_decisions.tsv exclude
prep-mshbm rerun                      compile-exclusions
                                              ↓
                                docs/SURFACE-FIX-STATUS.md (append sub-s03 row)
```

---

## Tests

`tests/scripts/test_audit_subject_flywheel_vs_bids.py`:

1. `test_audit_module_imports` — smoke.
2. `test_audit_resolves_subject_aliases` — given a config with `s29-2 → s29`, the audit queries Flywheel for both labels. (Mock the Flywheel client.)
3. `test_audit_flags_session_in_fw_not_in_bids` — mock FW with 3 sessions, BIDS with 2; audit report flags the missing one.
4. `test_audit_marks_excluded_per_config` — sessions in config with `exclude: true` show as EXCLUDED in the report, not MISSING.

No code changes to bidsify, fmriprep, lev1, or prep-mshbm pipelines — they all support `--subjects` filtering already.

**Operational verification** (post-merge, manual):
1. Run audit on sub-s03 — eyeball the report, confirm ses-25210 has T1w content.
2. Run bidsify with `--subjects s03 --overwrite`; verify ses-13 dir appears.
3. Submit fmriprep, wait ~12h.
4. Run qa_report; confirm hole count.
5. If good: submit lev1-surface + prep-mshbm.

---

## Risk handling

1. **Audit reveals ses-25210 has NO T1w**: misunderstanding of the user's instruction; pause and reconfirm before proceeding.
2. **bidsify fails on ses-13** (e.g., physio sidecar missing or trim_bold collision): inspect bidsify logs; may need a one-off fix; not a pattern bug to file.
3. **New fmriprep recon still has high holes**: fall back to the exclusion path (sub-project A's design). Document the failed fix attempt.
4. **fmriprep takes longer than the 12h walltime**: bump time, resubmit. Anat workflow is the longest; ~8-15h is normal.
5. **Other sub-s03 sessions affected** (because bidsify rebuilt): use `--overwrite` cautiously — verify the other 12 sessions still have their existing BOLD scans after the rerun. The audit should confirm pre/post bidsify state.

## Out-of-scope reminders

- Don't touch the other 4 discovery subjects.
- Don't change fmriprep version, FreeSurfer version, or any preprocessing flags.
- Don't extend the audit to other subjects (that's I2).
- Don't refactor bidsify module code (that's I4).

---

## Open questions / decisions deferred

1. **Documentation of the .bidsignore additions**: append a section to `docs/EXCLUSIONS.md` under "Manual notes" or via the auto-generator from sub-project A. Both can co-exist.
2. **Audit format**: markdown table is the choice for now; if the report turns out to need machine-parseable form (e.g., for I2 cohort-wide), revisit.
3. **fmriprep auto-T1w selection priority**: fmriprep picks the most recent T1w by default. After .bidsignore-ing the older two, only ses-13's remains — auto-selection is unambiguous. Confirmed by inspection of fmriprep's behavior.
