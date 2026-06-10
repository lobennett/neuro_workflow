# Design Spec — iProc fork ↔ upstream scientific audit

**Date:** 2026-06-01
**Author:** Logan Bennett (+ Claude)
**Status:** Approved design; awaiting spec review before execution.

## Goal

Verify that the iProc fork running on Sherlock (`lobennett/iProc`, branch
`container-and-bids-tooling`, HEAD `7546347`) is **scientifically faithful** to
its upstream parent (`harvard-nrg/iProc`). The intent was to make the **minimal
edits necessary** to run upstream's pipeline on our multi-echo data on Sherlock
**without changing anything scientifically**. This audit + code review confirms
whether that held, flags every divergence, and gives a concrete path back to
upstream behavior where a divergence was not strictly required to run.

## Key facts (verified 2026-06-01)

- Remotes: `origin=lobennett/iProc`, `upstream=harvard-nrg/iProc`.
- Fork branched from upstream at merge-base **`0ae6246`**; upstream `main` has
  since advanced to **`c2cd261`** (merged PR #10 `bugfix/gh-5-hardcode`).
- **Multi-echo + tedana already exist in upstream `main`** (`bandpass_ME.sbatch`,
  `run_tedana.py`, `NUMECHOS`) — ME is NOT a fork invention, so "match upstream
  science" is achievable on the ME path too.
- **Direction 1 (fork edits, `0ae6246..HEAD`):** 38 files, +3071/−152. ~2,500
  added lines are net-new infra (`bids_setup/`, `container/`). Science-bearing
  *modifications* are small/focused: `iproc/steps.py` (+43), `compute_T1_MNI_warp.sh`,
  the fieldmap set (`fmap_from_bids.py` +118, `fm_unw*.sh`), `fs6_project_to_surf.sh`,
  `calculate_nuisance_params.sh`, combine/warp sbatches.
- **Direction 2 (upstream since fork-point, `0ae6246..upstream/main`):** 29 files,
  +866/−570. Upstream heavily revised the SAME core files — `steps.py` (+421),
  `iProc.py`, the `p4` combiners, `csvHandler`, and the same `fs6_project_to_surf.sh`,
  `calculate_nuisance_params.sh`, `fm_unwarp_and_mc_to_midvol.sh`. **Overlap is the
  crux:** files changed in both directions must be reconciled (are fork and upstream
  scientifically equivalent, or did upstream fix something the fork handles differently?).

## Scoping decisions (from brainstorming)

- **Disposition (B):** report + remediation. Each finding classified, and each
  `possible-divergence` gets a recommendation: keep-justified, or revert-toward-upstream
  **with the exact minimal patch**.
- **Baseline (C):** both directions, reported separately — fork edits vs the
  fork-point (clean attribution of *what we changed*) AND upstream fixes since the
  fork-point that we lack (*what upstream changed that we don't have*).
- **Depth (A):** tiered. Exhaustive line-by-line on science-bearing diffs; light
  "could this change the data?" pass on pure infra — **with a hard promotion rule:**
  any infra edit touching paths-to-data, masks, configs, or templates is promoted to
  deep review (e.g. `MASKSDIR → codedir/mni_masks`).
- **Verification (B):** static reasoning as the spine, plus cheap read-only empirical
  spot-checks on decisive cases (wrapper matrix equality, NUMVOL == `.par` length,
  rsync→mv output-set identity, rendered command-string diff for a real s10 scan).
- **Execution (Approach 2):** orchestrated Workflow with adversarial verification.

## Design

### §1 Decomposition (fan-out units)

~12 science-bearing units, each reviewed in **both** directions, plus a light infra sweep:

1. `steps.py` — core orchestration (fork +43; upstream +421 reconciliation)
2. T1→MNI registration — `compute_T1_MNI_warp.sh` (FNIRT→affine, FLIRT search range,
   `fslswapdim` removal, `T1_2_MNI152_2mm` config) — top divergence suspect
3. Fieldmap — `fmap_from_bids.py`, `fm_unw.sh`, `fm_unwarp_and_mc_to_midvol.sh`,
   `fmap_*_topup*.sh` (GE handling, dims warn-not-fail)
4. Motion-correction / midvol target — `fm_unwarp_and_mc_to_midvol.sh`,
   `create_upsampled_midvol_target.sh`
5. Combine / apply-warp — `combine_warps_parallel{,_ME}.sbatch` (rsync→mv)
6. Nuisance + bandpass — `calculate_nuisance_params.sh`, `nuisance_regress`,
   `bandpass{,_ME}`, `wholebrain_only_regress`
7. Tedana / multi-echo — `run_tedana.py`, ME steps
8. Surface projection — `fs6_project_to_surf{,_ME}.sh` (changed in both directions — reconcile)
9. NUMVOL / cfg / per-scan volume count — `steps.py` NUMVOL + `iProc_p4_*` + `csvHandler`
10. Masks & data paths (promoted infra) — `MASKSDIR`, mask/template paths
11. FSL hex-float wrappers (promoted) — `flirt_wrapper.sh`, `convert_xfm_wrapper.sh`
    → must yield numerically-identical transforms
12. BIDS ingestion vs upstream XNAT — `bids_setup/`, `func/anat_from_bids.py`,
    `iproc/bids` → does it feed the *same* data (echoes, ordering, TR, EchoTimes, units)?

Light infra sweep (deep only if promoted): `container/`, sbatch resource defaults,
docs, `modules_rocky8/modwrap`, `.gitignore`.

### §2 Per-unit method

Each agent: (a) `git diff`/`git show` the unit's files in both directions against the
refs (read-only — never the working tree); (b) classify every hunk as
`infrastructure` / `scientifically-equivalent` / `possible-divergence` /
`upstream-fix-we-lack`; (c) for overlap files, explicitly reconcile fork-version vs
upstream-version; (d) run the unit's decisive read-only spot-check.

### §3 Adversarial verification

Every `possible-divergence` and `upstream-fix-we-lack` is handed to an independent
skeptic agent prompted to **refute** it (prove it is actually equivalent/harmless)
before it may enter the report. This is the "nothing changed scientifically" guarantee.

### §4 Deliverable

`docs/audits/2026-06-01-iproc-scientific-audit.md`:
- Verdict: is the fork scientifically faithful to upstream? where not?
- **Direction-1 table:** each fork edit → class + severity + keep-justified **or**
  revert-with-minimal-patch.
- **Direction-2 table:** each upstream fix we lack → scientific relevance +
  backport-or-not + the cherry-pick/patch.
- Overlap reconciliation (files changed in both directions).
- Empirical spot-check results.
- **Minimal-edits target:** the smallest change set truly required to run on Sherlock
  vs. the set that touched science.

### §5 Guardrails

Strictly read-only. The running tedana campaign uses this exact tree, so agents diff via
git refs only and never edit/move/delete anything in `/scratch/users/logben/iProc`.
Applying any remediation patch/revert is deferred until after the campaign finishes.

## Out of scope

- Applying the remediation patches (deferred to post-campaign).
- Full empirical re-run of a subject through unmodified-upstream (compute-heavy; the
  registration edits are known to differ, so it would mostly reconfirm the expected delta).
- Auditing upstream feature branches not merged into `main` (`feature/ahpxue-minor_fix`,
  `feature/gh-8-nofmap`) unless a Direction-2 finding points to one.

## Success criteria

A reviewer can read the report and know, for every fork edit, whether it is infra,
scientifically equivalent, or a divergence — and for each divergence, exactly how to
revert to upstream behavior or why keeping it is justified; plus which upstream fixes
since the fork-point are worth backporting.
