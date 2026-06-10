# Design: neuro_workflow Simplification + Full Provenance

- **Date:** 2026-06-09
- **Status:** Approved (brainstorming complete; ready for implementation planning)
- **Author:** Logan Bennett (with Claude / Fable 5)
- **Supersedes / builds on:** `docs/REFACTOR-PLAN.md` (2026-05-31, conservative read-only cleanup), `docs/RSE-PRINCIPLES.md`

## 1. Context

`neuro_workflow` is a mature research-fMRI orchestrator (~15K source LOC / 109 modules, ~16K test LOC / 127 files) chaining **Flywheel → BIDS → events → exclusions → fMRIPrep → lev1 GLM → lev2 group inference**, plus downstream MSHBM, XCP-D, Bayesian prevalence mapping, and an iProc preprocessing fork.

The architecture is sound where it counts (Protocol+registry pipeline/exclusion patterns; a reference-quality provenance core in `core/exclusions.py`; scientifically locked lev1 modeling — SPM HRF, +TR/2 slice-timing, single-source dummy-scan handling, VIF/rank guards, the float32 contrast-save fix). The problems are **structural sprawl and a provenance chain that fragments after the exclusions stage**, not correctness bugs.

A read-only 10-agent codebase map (2026-06-09, run `wf_b636e8b8-c5c`) established the current state and these three high-severity issues:

1. **Provenance breaks after exclusions.** lev1/lev2/MSHBM jobs record no machine-readable run metadata (no fMRIPrep version, exclusions SHA, task-YAML version, code SHA, uv.lock). lev2 discovers inputs by glob + a `_desc-belowMinRuns` filename substring. **BIDS→lev2 is not reproducible from git alone.**
2. **Two unreconciled exclusion ledgers.** Hand-authored `docs/EXCLUSIONS.md` (~18 discovery entries, last touched 2026-04-14) vs machine lockfiles (`data/exclusions/discovery_lock.json`, 13 entries, all qa_decisions). No reverse-link; no single query answers "why is sub-X_ses-Y excluded?"
3. **`scripts/` is a dumping ground.** 34 files mixing ~3–4 real drivers with an iProc fork (~1,000 LOC), an MSHBM cluster (~1,100), and a prevalence-dashboard cluster (~1,600). 8 scripts are untracked in git — including the controller running *right now* (`iproc_tedana_scatter.py`): data-loss risk.

**Operational constraint:** an iProc tedana SLURM drip controller (job `28601240`) is mid-campaign (~3–4 days). It calls `scripts/iproc_tedana_scatter.py` and `scripts/iproc_scatter.py` from this checkout. Those files must NOT be physically moved/deleted until the controller is idle.

## 2. Goals / Non-Goals

**Goals**
- Slim the core repo to one clear narrative: **Flywheel → lev2**. Everything downstream/alternative is extracted.
- Make BIDS→lev2 **re-derivable in a fresh directory** with identical exclusions/config (multiverse-ready), with machine-readable provenance on every output.
- Collapse the two exclusion ledgers into **one committed source of truth** that generates `.bidsignore` + `EXCLUSIONS.md` and answers per-scan "why excluded?".
- Make task lists, contrast formulas, and **all thresholds** versioned per-dataset config (a multiverse variant = a config edit).
- Deduplicate pipeline boilerplate and split the 376-line `cli.py`.
- Add an **end-to-end synthetic simulation** (planted-contrast BIDS→lev1→lev2) for fast testing and demos.
- A **fail-loud** test suite (no tautological security theater); easy onboarding.

**Non-Goals (this spec)**
- Scientific/behavioral changes. The structural refactor is **behavior-preserving**; correctness fixes are a *separate, test-backed audit workstream* (§9).
- Touching the running iProc campaign or its scripts until idle.
- Building the simulation for surface/MSHBM stages (volumetric MNI core only; external-binary stages stubbed via the command seam).

## 3. Decisions (decision record)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Scope boundary | **Core only.** Extract iProc, MSHBM, prevalence, parcellation-reliability, XCP-D out (full extraction, not quarantine). |
| D2 | Provenance depth | **Level B.** Run-manifest sidecar + BIDS `dataset_description.json` + per-output input manifest → BIDS→lev2 re-derivable. |
| D3 | Two-ledger fix | **Single generated source.** One committed compiled exclusions source; `.bidsignore` + `EXCLUSIONS.md` auto-generated; add `exclusions query`. |
| D4 | Behavior vs fixes | **Structure now, audit separately.** Behavior-preserving structure + provenance + tests; scientific fixes are a follow-on workstream. |
| D5 | Simulation reach | **E2E synthetic chain** with command-wrapper shims (FSL/wb/surf stubbable). |
| D6 | Config reach | **Tasks + contrasts + thresholds** all in versioned per-dataset config. |
| D7 | Consolidation | **Dedupe via base classes** (`ContainerPipeline`, `LocalAnalysisPipeline`) + split `cli.py`. |
| D8 | Timing | **Isolated worktree now**; commit untracked scripts first; defer physical iProc-script move until controller idle. |

## 4. Target structure & extraction boundary (D1)

Core repo end state:
```
src/neuro_workflow/
  core/            acquisition, slurm, exclusions, + provenance.py (NEW), + cmd.py (NEW command seam)
  bidsify/         Flywheel → BIDS
  events/          behavioral → events.tsv (+ QC)
  exclusions/      generators + single committed compiled source
  pipelines/       base.py + ContainerPipeline + LocalAnalysisPipeline;
                   fmriprep, freesurfer, qsiprep, happy, fsqc, lev1, lev2
  qa/              metrics + report
  analysis/
    core/ io/      shared helpers
    lev1/ lev2/
  cli/             cli.py split into per-subsystem handler modules
  config/          versioned per-dataset config (tasks, contrasts, thresholds)
  testing/         synthetic.py data factory (NEW)
scripts/           ONLY true drivers (trim_bold, reconcile_sessions, migrate_behavioral,
                   migrate_archive, check_tr, fmriprep_preflight, qa_report,
                   render_exclusions_md, lev1_outliers, run_*.sbatch, synthstrip/surface QA)
tests/             unit + tests/e2e/ (NEW)
docs/              consolidated
external/          iProc, PrecisionNetworkMapping (submodules)
```

**Extracted to a sibling network-analysis repo (D1):**

| Component | Today | Destination |
|---|---|---|
| iProc preproc tooling | `scripts/iproc_*` (4) | `external/iProc` fork (script move **deferred** until controller idle) |
| MSHBM | `analysis/mshbm/` (14), `pipelines/{mshbm,prep_mshbm}`, `scripts/mshbm_*` (7), templates | network-analysis repo (uses `external/PrecisionNetworkMapping`) |
| XCP-D | `pipelines/xcpd.py`, `scripts/xcpd_preflight.py`, `templates/xcpd.sbatch` | network-analysis repo |
| Prevalence + parcellation reliability | `analysis/prevalence/` (9), `analysis/parcellation_reliability/` (3), `scripts/prevalence_*` (6) | network-analysis repo |

**Deleted outright:** `src/neuro_workflow/behavioral_archive/` (empty), root `subjects_*.txt` (11, superseded by `config/pipeline_config.json`), committed PDFs (`docs/DuEtAl2025Neuron.pdf`, `docs/HBM-43-3311.pdf` → `.gitignore` + `docs/REFERENCES.md`).

**Verified NOT dead (keep):** `analysis/lev1/processing/imaging.py` (`cast_nifti_to_float32`, load-bearing, fixes the uint8 quantization bug); `scripts/render_exclusions_md.py` (already reads the committed lockfile).

## 5. Provenance model (D2)

**`core/provenance.py`** generalizes the `core/exclusions.py` lockfile pattern into `write_run_manifest(output_dir, stage, args, inputs)`, writing `run-manifest.json` with: `code_sha`(+`dirty`), `uv_lock_hash`, tool/container versions used, `exclusions_source_sha`+path, `config_version` (hash of resolved config), full CLI args, ISO timestamp, host + SLURM job id, and an **input manifest** (input file paths + sizes + hashes).

**lev1/lev2 outputs become BIDS derivatives:** `dataset_description.json` (`GeneratedBy` name/version/code-URL+sha, `SourceDatasets`) + the per-output input manifest. lev2 stops inferring exclusions from a filename substring and reads its inputs' manifests instead.

**Clean-tree enforcement:** stamping/compiling on a dirty tree warns loudly; `--allow-dirty` to override.

**Guarantee:** from a fresh clone + committed config + committed exclusions source, re-run flywheel→lev2 and verify each output's manifest matches.

## 6. Single exclusions source + flywheel→BIDS provenance (D3)

**One committed source per dataset:** `data/exclusions/<dataset>_exclusions.json` — the full resolved scan-level ledger (committed; not the ephemeral `~/.neuro_workflow` copy). Each entry:
```
{ key: "sub-XX_ses-YY_task-ZZ_run-N", action: "exclude|trim|force-include",
  source: "collection|tr-percent|motion|behavioral-qc|surface-quality|qa-manual",
  reason: "...", metrics: {...}, provenance: {generator, sha, timestamp} }
```
Static `.bidsignore`-derived data-collection exclusions become first-class entries (`source: "collection"`), unifying the two ledgers (the 13-vs-18 discrepancy disappears — one list).

**Generated artifacts:** `neuro-run exclusions render-bidsignore` and `render-md` write `.bidsignore` / `EXCLUSIONS.md`, each stamped `DO NOT EDIT — generated from <source>@<sha>`. A **fail-loud consistency test** asserts on-disk files equal rendered output.

**Query:** `neuro-run exclusions query sub-s10 [ses-05] [task-goNogo]` prints every stage that excluded/trimmed the scan and why.

**Flywheel→BIDS rename provenance:** the reconciliation manifest + the 5 split-session offsets (s321 ses-02, s1445 ses-02, s1326 ses-03, s1391 ses-06, s1258 ses-07) are codified into a committed `session_map` that events/lev1 **read** (today they live only in `SCAN-NOTES.md` prose and assume sequential numbering). `neuro-run provenance query sub-s321` surfaces the FW-session→BIDS-session mapping + offset reason.

## 7. Config-as-code + dedupe (D6, D7)

**Config-as-code (`config/`):**
- `config/tasks/*.yaml` — regressors **and contrast formulas**, with **load-time contrast validation** (symbolic parser: every contrast references declared regressors and is well-formed → fails at load, not nilearn runtime).
- `config/datasets/<dataset>.yaml` — subject list, `session_map`/offsets, `BASE_TASKS`/`DUAL_TASKS` (de-hardcoded from `pipelines/lev1.py`), and **all thresholds** (motion FD/prop, behavioral omission/RT/stop-acc, lev1 VIF combined/strict). `events/qc.py`, `confounds.py`, the outlier generator read from here.
- `config_version` hash recorded in every run-manifest. **Multiverse = a new `config/datasets/<variant>.yaml`** → whole pipeline reruns into a new output tree, fully stamped, zero code edits.

**Dedupe (behavior-preserving):**
- `ContainerPipeline` base absorbs the ~300 LOC duplicated `build_context` across fmriprep/freesurfer/qsiprep/happy/fsqc; concrete pipelines declare only image + command + resource defaults. `LocalAnalysisPipeline` base for lev1/lev2 (job-list + exclusions-file + provenance stamping).
- `cli.py` (376 LOC) → `cli/` package (parser assembly + dispatch + per-subsystem handler modules). **Identical command surface + byte-identical rendered sbatch**, guaranteed by a byte-stability test.

## 8. Simulation, tests, docs (D5)

**Simulation (E2E synthetic chain):**
- `core/cmd.py` — single `run_command()` seam for all external binaries (FSL `randomise`, `wb_command`, `mri_surf2surf`, container calls). `--simulate` mode records the command and synthesizes plausible outputs.
- `testing/synthetic.py` — factory for tiny fake NIfTIs (few voxels × few volumes), events with a **planted contrast**, synthetic `confounds.tsv`.
- `tests/e2e/` — drives bidsify→events→exclusions→lev1→lev2 in volumetric MNI on synthetic data and **asserts lev2 recovers the planted effect** where expected.

**Test policy (fail-loud):** collapse the ~11 tautological pipeline tests into one render+byte-stability meta-test; add the real lev2 group-stat test (today: 1×35 lines), the synthetic e2e, contrast-validation tests, the exclusions render==on-disk consistency test, and a split-session→correct-numbering test. Smaller, higher-signal suite + new high-value coverage; accept the coverage-number dip on deleted tautologies.

**Docs / onboarding** — consolidate to: `README.md` (flywheel→lev2 onboarding narrative + quickstart incl. simulate), `WORKFLOW.md` (regenerated), `EXCLUSIONS.md` (generated), `SCAN-NOTES.md`, `ARCHITECTURE.md` (regenerated), `REFERENCES.md` (PDF pointers), new `PROVENANCE.md` (manifest/derivatives model + fresh-dir re-derivation). Archive the 34 superpowers plan/spec pairs under `docs/superpowers/archive/` + index; fold the 3 one-line stubs (`AUDIT-sub-s03.md`, `SURFACE-*.md`) into a living `SUBJECT-STATUS.md`; merge `PIPELINE.md`/`RUNBOOK.md` into `WORKFLOW.md`; extracted-fork docs move with their code.

## 9. Phased PR sequence

Each PR is independently mergeable and behavior-preserving (except the deliberate config/provenance additions). Executed in an isolated git worktree off `main`.

| PR | Content | Controller-safe |
|----|---------|-----------------|
| 0 | Protect: `git add` the 8 untracked scripts; create worktree/branch | yes |
| 1 | Prune (`behavioral_archive`, `subjects_*.txt`, PDFs→gitignore) + extract MSHBM/prevalence/parcellation/XCP-D to sibling repo | yes (iProc scripts deferred) |
| 2 | Dedupe: `ContainerPipeline`/`LocalAnalysisPipeline` + `cli/` split + meta-test | yes |
| 3 | Config-as-code + contrast validation + thresholds externalized | yes |
| 4 | Provenance: `core/provenance.py` + manifests + BIDS derivatives + clean-tree enforcement; lev2 reads input manifests | yes |
| 5 | Single exclusions source + render/query + `session_map` + consistency test | yes |
| 6 | Simulation: `core/cmd.py` + `testing/synthetic.py` + e2e + lev2 test + collapse tautologies | yes |
| 7 | Docs/onboarding consolidation + `PROVENANCE.md` | yes |
| — | iProc-script extraction | **after controller idle** |

## 10. Scientific-audit follow-on (separate spec, D4)

A distinct, test-backed workstream after the structural refactor: contrast-formula correctness across all 8 base tasks; **session-offset enforcement end-to-end** (split-session subject → correct BIDS numbering through lev1); trim/salvage handling (verify trimmed events are monotonic; decide reduced-power output tagging; confirm lev1 honors or documents `get_trim_info`); the dummy-scan consistency seam (7-dummy assumption, no double-adjust); threshold defensibility/sensitivity; the stale `surface_data.py` subject-level anat fallback (~line 506) under per-session fMRIPrep; QA-vs-fMRIPrep FD agreement.

## 11. Success criteria

- A fresh clone + `config/datasets/<dataset>.yaml` + committed exclusions source reproduces BIDS→lev2; each output carries a `run-manifest.json` that round-trips.
- `neuro-run exclusions query <scan>` answers "why excluded?" for any scan; `.bidsignore` and `EXCLUSIONS.md` are generated and the consistency test passes.
- A multiverse variant is a single new `config/datasets/*.yaml` with no code edits.
- `uv run pytest` passes, including the synthetic e2e (planted-contrast recovery) and the real lev2 test; the tautological pipeline tests are gone.
- `scripts/` contains only core drivers; `behavioral_archive`, root `subjects_*.txt`, and committed PDFs are gone; core `analysis/` holds only lev1/lev2/core/io.
- A new contributor can follow `README.md` from Flywheel to lev2.

## 12. Risks & mitigations

- **Disrupting the running iProc controller** → defer all iProc-script moves until idle; PR0 commits the untracked scripts first so nothing is lost; work in a worktree so the live checkout's scripts are untouched.
- **Silent behavior change during dedupe** → byte-stability test on rendered sbatch + identical CLI surface; behavior-preserving commits reviewed independently.
- **Extraction breakage** → extract downstream subsystems with their tests; the core e2e (BIDS→lev2) does not depend on extracted code, so a green e2e proves the core still works.
- **Scope creep into science** → correctness changes are explicitly out (§10); if a structural change would alter results, stop and route it to the audit workstream.

## 13. Open items (resolve during planning, not blocking approval)

- **Destination repo(s) for extracted downstream code.** D1 says "sibling network-analysis repo," but whether MSHBM + prevalence + XCP-D land in one new repo, in the existing `network_lev1_residuals` repo, or as separate submodules is not yet pinned. To be decided at PR1 planning. (iProc → `external/iProc` is the only firm destination.)
- **Cross-dependency edges at extraction.** Extracted subsystems may import core helpers (`analysis/core`, `analysis/io`, `core/*`). PR1 must enumerate and cut/redirect these import edges; the green core e2e is the proof the core no longer depends on extracted code.
- **`external/iProc` submodule** is planned but its creation/commit state must be confirmed before PR1 (the iProc fork fixes are noted as deferred elsewhere).
- **Whether PRs land on `main` or accumulate on a long-lived refactor branch** before a single merge — to be decided with the worktree setup in PR0.
