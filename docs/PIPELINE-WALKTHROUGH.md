# End-to-End Pipeline Walkthrough (Flywheel → second-level models)

**Last updated:** 2026-06-30

A complete, copy-pasteable demonstration of running the *entire* pipeline from a live
Flywheel pull through second-level (group) models, producing fresh, version-controlled,
read-only BIDS datasets on Oak. Every command is shown in the order it is run, with
**what it does** and **why**.

This is the *narrated walkthrough*. Related docs, and when to use each:

| Doc | Use it for |
|-----|-----------|
| **this file** | The full ordered recipe, start to finish, with explanations |
| `docs/WORKFLOW.md` | Terse stage reference (Steps 1–14) |
| `docs/RUNBOOK.md` | How each SLURM job is launched (partitions, resources, binds) |
| `docs/EXCLUSIONS-FLOW.md` | How the 5 exclusion sources compile into the lockfile |
| `docs/PROVENANCE.md` | Run-manifest schema + clean-tree policy |
| `docs/CONFIG.md` | `pipeline_config.json`, `thresholds.yaml`, `battery.yaml` schemas |
| `docs/superpowers/specs/2026-06-30-flywheel-to-lev2-oak-reexecution-design.md` | Design + rationale for the Oak re-execution |
| `docs/superpowers/plans/2026-06-30-flywheel-to-lev2-oak-reexecution.md` | Task-by-task implementation plan |

---

## 0. Mental model

The pipeline has one **reproducible core** and a set of **regenerable derivatives**:

- **Core (version-controlled):** the raw BIDS tree + the compiled **exclusion lockfile**.
  The exclusion set is keyed `sub_ses_task-T_run` and is *path-independent* — it is the
  scientific ground truth for "which scans/contrasts enter analysis."
- **Derivatives (regenerable, not version-controlled):** fMRIPrep, lev1, lev2 outputs.
  fMRIPrep is not byte-reproducible; that is accepted.

Exclusions are computed at **three stages** as their evidence appears, so the recipe
commits and gates at each:

1. **Pre-fMRIPrep** (knowable right after BIDS): `behavioral`, `collection`, `qa_decisions`.
2. **After fMRIPrep**: `motion` (from confounds).
3. **After lev1**: `lev1_outlier` (from cohort QC / VIF).

After each recompile, a **diff-gate** (`scripts/exclusion_gate.py`) compares the new set
against a frozen reference and **halts on any undeliberate change** — so exclusions only
change with evidence + sign-off.

---

## 1. Conventions (every shell)

```bash
module load uv                       # required for every `uv run` command
cd /scratch/users/logben/neuro_workflow_refactor   # the code checkout (git branch: repro-harness-2026-06)
```

- **Never run Python / pytest on the login node** (Sherlock policy). Offload to a job
  (`sbatch`) or a compute shell: `srun -p dev -t 00:15:00 --mem=4G /bin/bash -lc '...'`.
- **git-annex is not on the login PATH by default; datalad's bundled Python is broken here.**
  For any annex operation, put the binary on PATH and use raw git-annex:
  ```bash
  export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
  ```
- **Flywheel auth** lives in `~/.config/flywheel/user.json`. If it expires you get
  `ApiException (403) Api key is expired`; refresh the `key` field with a fresh API key
  from the Flywheel profile page.
- **Cohorts:** `discovery` (5 subj), `validation` (41 subj) are analysis cohorts;
  `excluded` (11 subj) is BIDS-only (no fMRIPrep/lev1/lev2). The three are independent —
  run them in parallel through Part B; only fMRIPrep (Part C) contends for compute.
- **Dataset naming:** the pipeline resolves the subject *roster* by the sample name
  (`discovery`/`validation`/`excluded`, from `pipeline_config.json`), and resolves *paths*
  by the registered dataset name. On Oak we register `<cohort>_oak`.
- **No-overwrite rule:** nothing pre-existing on Oak is touched; the new datasets live
  under a fresh `bids/` parent.

Paths used throughout:

```bash
OAK=/oak/stanford/groups/russpold/data/network_grant
BIDSROOT=$OAK/bids                       # new datasets: $BIDSROOT/{discovery,validation,excluded}
RAW_CLEANED=$OAK/_archive_someone_plz_clean/behavioral_data/raw_cleaned   # read-only behavioral source
STAGE=/scratch/users/logben/oak_reexec   # scratch staging (subjects files, logs, gate reports)
```

---

## 2. Part A — One-time setup (no heavy compute)

### A1. Freeze the determinism anchors (commit into the code repo)

**What:** commit the Flywheel inventory snapshots and the QC-decisions reference, and
freeze the current validated compiled-exclusion sets as the gate reference.
**Why:** the snapshots are the deterministic replay anchor; the frozen reference is what
the exclusion diff-gate compares against.

```bash
git add data/repro/fw_inventory_discovery.json data/repro/fw_inventory_validation.json \
        config/manifests/qc_decisions.tsv
cp ~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json  data/exclusions/discovery_reference_compiled.json
cp ~/.neuro_workflow/exclusions/validation/compiled_exclusions.json data/exclusions/validation_reference_compiled.json
git add data/exclusions/discovery_reference_compiled.json data/exclusions/validation_reference_compiled.json
git commit -m "chore(repro): freeze snapshots + compiled-exclusion gate references"
```

### A2. Pin the Flywheel SDK

**What:** pin `flywheel-sdk` to the locked version in `pyproject.toml`.
**Why:** a rebuilt container must not silently upgrade the SDK and change pull behavior.

```bash
# edit pyproject.toml: flywheel-sdk>=17.0  ->  flywheel-sdk==21.5.0
uv lock                                   # confirm no resolution change
git add pyproject.toml uv.lock && git commit -m "build: pin flywheel-sdk"
```

### A3. Verify the container can reach Oak

**What / why:** `bidsify.sbatch` binds `-B /oak:/oak`; confirm the container sees Oak
(Sherlock does not guarantee an `/oak` auto-mount).

```bash
apptainer exec -B /oak:/oak /home/groups/russpold/singularity_images/neuro_workflow.sif \
  ls $OAK/ | head
```

### A4. Create + register the Oak datasets

**What:** create three git-annex datasets on Oak and register them in the machine-local
dataset registry.
**Why:** BIDS holds ~150 MB NIfTIs → git-annex (MD5E), not plain git. Registration lets
`neuro-run` resolve each dataset's path.

```bash
export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
mkdir -p $BIDSROOT
for c in discovery validation excluded; do
  git -C $BIDSROOT/$c init -q
  cp /scratch/users/logben/discovery_bids/.gitattributes $BIDSROOT/$c/.gitattributes   # annex.largefiles policy
  git -C $BIDSROOT/$c annex init "oak-$c"
  git -C $BIDSROOT/$c add .gitattributes && git -C $BIDSROOT/$c commit -q -m "init: git-annex BIDS dataset"
done

# subjects files (add-dataset requires one) generated from the roster
mkdir -p $STAGE
for c in discovery validation excluded; do
  python3 -c "import json;cfg=json.load(open('config/pipeline_config.json'));s=cfg['samples']['$c'];ids=list(s.keys()) if isinstance(s,dict) else s;open('$STAGE/subjects_$c.txt','w').write(chr(10).join(ids)+chr(10))"
  uv run neuro-run add-dataset ${c}_oak --bids-dir $BIDSROOT/$c --subjects-file $STAGE/subjects_$c.txt
done
```

> **datalad note:** the plan calls for `datalad create`/`datalad save`, but datalad is
> unusable on this system (broken bundled Python). We use **raw git-annex** everywhere
> instead (`git init`+`git annex init`; `git annex add`+`git commit`) — same end state.

---

## 3. Part B — Flywheel → BIDS (per cohort) → commit #1

Do `discovery` first as a pilot, verify, then `validation` and `excluded` (parallelizable).
Below uses `discovery`; substitute the cohort + Oak path for the others.

### B1. Drift Gate — capture fresh inventory + diff vs committed snapshot

**What:** query Flywheel for the current project inventory and compare it (roster-scoped,
with `session_overrides`/`subject_aliases` applied) against the committed snapshot.
**Why:** BIDS `ses-NN` is derived by ascending session timestamp — a new/removed session
could **renumber** sessions and invalidate every exclusion key. The gate catches that
before any write. (Needs the login node's internet; compute nodes can't reach Flywheel.)

```bash
uv run --extra bidsify python scripts/capture_fw_inventory.py discovery \
  --out $STAGE/fw_inventory_discovery_fresh.json
```

Then compare committed vs fresh **after** applying alias-merge + overrides + timestamp
sort, per roster subject. Any renumbering of an existing `ses-NN` → **STOP and review**.
An *additive* latest-timestamp session (e.g. s03's `25210` rescue-T1) is benign (it
appends as the new highest `ses-NN`; nothing renumbers).

> `session_overrides`/`subject_aliases` are nested under the `flywheel` key in
> `config/pipeline_config.json` (e.g. `s29/22424` is `exclude:true`; `s03/22752` is
> `reassign_to:s10`).

### B2. bidsify (live pull → Oak) + trim

**What:** pull NIfTI/JSON/physio from Flywheel into BIDS on Oak, then remove the 7 dummy
volumes from every BOLD.
**Why:** the live pull is the Flywheel→BIDS step being reproduced; trimming is done
post-bidsify (bidsify never trims) so fMRIPrep runs with `--dummy-scans 0`.

```bash
uv run neuro-run submit bidsify discovery \
  --output-dir $BIDSROOT/discovery --overwrite --time 04:00:00 --mem-gb 16

# verify no silent per-subject failures before continuing
grep -ril "Failed to process" $BIDSROOT/discovery/sourcedata/logs/ || echo "OK: no failures"

# trim (heavy I/O over all BOLD — run as a job, idempotent via sidecar check)
sbatch -p normal -t 01:30:00 --mem=16G -c 4 -J trim_disc \
  -o $STAGE/logs/trim_discovery-%j.log \
  --wrap "module load uv && cd $PWD && uv run python scripts/trim_bold.py $BIDSROOT/discovery"
```

### B3. Reconcile behavioral ↔ BOLD (reuse the reviewed manifest)

**What:** re-derive the behavioral↔BOLD matching manifest and diff it against the
committed, human-reviewed manifest.
**Why:** `reconcile_sessions.py` resets human decisions to `pending`; you **reuse** the
committed manifest and only review genuinely-new pending rows.

```bash
uv run python scripts/reconcile_sessions.py \
  --raw-dir "$RAW_CLEANED" --bids-dir $BIDSROOT/discovery \
  --scan-notes docs/SCAN-NOTES.md \
  --output $STAGE/reconciliation_discovery_fresh.tsv
# diff cols 1-6 vs config/manifests/reconciliation_discovery.tsv; new `pending` rows => STOP + review
```

### B4. Migrate behavioral into the dataset's own sourcedata

**What / why:** copy the reviewed behavioral CSVs into *this dataset's* self-contained
`sourcedata/in_scanner_behavior` (reading the read-only raw tree), so the shared Oak
`sourcedata/` is never rewritten.

```bash
uv run python scripts/migrate_behavioral.py \
  --manifest config/manifests/reconciliation_discovery.tsv \
  --raw-dir "$RAW_CLEANED" \
  --output-dir $BIDSROOT/discovery/sourcedata \
  --sample discovery --strict
```

### B5. Events + behavioral QC

**What:** build `_events.tsv` for every non-rest task (onsets shifted +10.43 s for the 7
trimmed dummy vols, non-monotonic tails truncated), then run behavioral QC.
**Why:** events feed lev1; QC produces the `behavioral-qc` exclusion source.

```bash
uv run neuro-run events create discovery_oak --behavioral-dir $BIDSROOT/discovery/sourcedata/in_scanner_behavior
uv run neuro-run events qc     discovery_oak --behavioral-dir $BIDSROOT/discovery/sourcedata/in_scanner_behavior
```

### B6. Validate

```bash
apptainer run -B /oak:/oak /home/groups/russpold/singularity_images/bids-validator_1.14.6.simg \
  $BIDSROOT/discovery 2>&1 | tail -30      # expect 0 errors
```

### B7. Compile pre-fMRIPrep exclusions → gate → render → commit #1

**What:** generate the collection + qa_decisions sources, compile (behavioral + collection
+ qa_decisions only — motion/lev1_outlier don't exist yet), gate against the reference,
render `.bidsignore`, and make the first git-annex commit.
**Why:** this freezes the raw BIDS + the *pre-fMRIPrep* portion of the exclusion set —
"the state at the Flywheel→BIDS point."

```bash
uv run neuro-run exclusions generate collection    discovery_oak
uv run neuro-run exclusions generate qa_decisions   discovery_oak --decisions-tsv config/manifests/qc_decisions.tsv
uv run neuro-run exclusions compile discovery_oak

# GATE each pre-fMRIPrep source against the frozen reference (exit 0 = no drift)
for src in behavioral-qc collection qa_decisions; do
  uv run python scripts/exclusion_gate.py \
    --new ~/.neuro_workflow/exclusions/discovery_oak/compiled_exclusions.json \
    --reference data/exclusions/discovery_reference_compiled.json \
    --source $src --report $STAGE/gate_discovery_$src.md || echo "DRIFT in $src — review $STAGE/gate_discovery_$src.md"
done

# render + place the (partial) .bidsignore (.bidsignore is git-only per .gitattributes → plain copy is safe)
uv run neuro-run exclusions render-bidsignore discovery_oak --output $STAGE/discovery.bidsignore
cp $STAGE/discovery.bidsignore $BIDSROOT/discovery/.bidsignore

# commit #1 (git-annex; annexes NIfTIs, plain-git for text)
export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
git -C $BIDSROOT/discovery annex add . ; git -C $BIDSROOT/discovery add .bidsignore sourcedata
git -C $BIDSROOT/discovery commit -m "commit #1: raw BIDS + pre-fMRIPrep exclusions"
git add data/exclusions/discovery_oak_lock.json && git commit -m "chore(exclusions): discovery_oak lockfile (pre-fMRIPrep)"
```

> The **excluded** cohort stops here (BIDS-only): run B1–B7, no fMRIPrep/lev1/lev2.

---

## 4. Part C — fMRIPrep → motion gate → commit #2

### C1. Submit fMRIPrep against the FULL BIDS

**What:** preprocess all subjects (fMRIPrep 25.2.4) as a SLURM array; write derivatives to
scratch staging, then rsync to Oak.
**Why:** run against the **full** BIDS (not the `.bidsignore` view) so *excluded* scans
still get confounds — the motion generator needs them. Work-dir stays on `$SCRATCH`
(Sherlock policy). Production resources (24 CPU / ~160 GB) are required; the template
defaults (8 CPU / 64 GB) OOM against the observed ~113 GB peak.

```bash
uv run neuro-run submit fmriprep discovery_oak \
  --version 25.2.4 \
  --output-dir $STAGE/discovery/derivatives \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage:den-41k fsnative T1w func" \
  --fmriprep-args "--cifti-output 91k --bold2anat-init t2w --subject-anatomical-reference first-lex" \
  --nthreads 24 --mem-per-cpu-gb 7 --time 2-00:00:00 --array-throttle 4
```

> `--array-throttle 4` is "medium" — leaves russpold headroom for other campaigns; raise
> once the node is free. Median runtime ≈ 24 h/subject.

### C2. Stage derivatives to Oak + build the filtered views

**What:** rsync fMRIPrep output into the Oak dataset, then build the `.bidsignore`-filtered
symlink views used downstream (XCP-D, etc.).

```bash
rsync -avP $STAGE/discovery/derivatives/fmriprep_25.2.4 $BIDSROOT/discovery/derivatives/   # via DTN for large transfers
uv run python scripts/build_xcpd_view.py discovery_oak --fmriprep-version 25.2.4
```

### C3. Motion exclusions → gate → commit #2

```bash
uv run neuro-run exclusions generate motion discovery_oak --fmriprep-version 25.2.4
uv run neuro-run exclusions compile discovery_oak
uv run python scripts/exclusion_gate.py \
  --new ~/.neuro_workflow/exclusions/discovery_oak/compiled_exclusions.json \
  --reference data/exclusions/discovery_reference_compiled.json \
  --source motion --report $STAGE/gate_discovery_motion.md            # exit 3 => review FD/DVARS evidence + sign off

uv run neuro-run exclusions render-bidsignore discovery_oak --output $STAGE/discovery.bidsignore
cp $STAGE/discovery.bidsignore $BIDSROOT/discovery/.bidsignore
git -C $BIDSROOT/discovery add .bidsignore && git -C $BIDSROOT/discovery commit -m "commit #2: + motion exclusions"
git add data/exclusions/discovery_oak_lock.json && git commit -m "chore(exclusions): + motion"
```

---

## 5. Part D — lev1 (surface) → lev1_outlier gate → commit #3

### D1. First-level GLM (8 base tasks)

**What / why:** fit surface lev1 for the 8 base tasks (dual tasks have placeholder configs
and are out of scope). Scan-level + per-contrast exclusions are honored from the compiled
lockfile; `min_runs=2` tags below-floor fixed-effects `_desc-belowMinRuns`.

```bash
uv run neuro-run submit lev1 discovery_oak \
  --base-tasks --space fsaverage6 --within-subject-threshold 1.0 \
  --residuals --min-runs 2 --time 2-00:00:00
```

### D2. Cohort QC → lev1_outlier exclusions → gate → commit #3 (final lockfile)

```bash
uv run neuro-run submit qa lev1 discovery_oak --output-dir $STAGE/qa_lev1_discovery   # produces lev1_outliers.csv
uv run neuro-run exclusions generate lev1_outlier discovery_oak \
  --lev1-outliers-csv $STAGE/qa_lev1_discovery/lev1_outliers.csv
uv run neuro-run exclusions compile discovery_oak                    # now all 5 sources, single clean SHA

uv run python scripts/exclusion_gate.py \
  --new ~/.neuro_workflow/exclusions/discovery_oak/compiled_exclusions.json \
  --reference data/exclusions/discovery_reference_compiled.json \
  --source lev1_outlier --report $STAGE/gate_discovery_lev1_outlier.md
uv run python scripts/exclusion_gate.py \
  --new ~/.neuro_workflow/exclusions/discovery_oak/compiled_exclusions.json \
  --reference data/exclusions/discovery_reference_compiled.json \
  --report $STAGE/gate_discovery_full.md                             # full-set gate; exit 3 => review + sign off

uv run neuro-run exclusions render-bidsignore discovery_oak --output $STAGE/discovery.bidsignore
uv run neuro-run exclusions render-md        discovery_oak --output $STAGE/discovery_EXCLUSIONS.md
cp $STAGE/discovery.bidsignore      $BIDSROOT/discovery/.bidsignore
cp $STAGE/discovery_EXCLUSIONS.md   $BIDSROOT/discovery/EXCLUSIONS.md
git -C $BIDSROOT/discovery add .bidsignore EXCLUSIONS.md && git -C $BIDSROOT/discovery commit -m "commit #3: FINAL exclusion set (all 5 sources)"
git add data/exclusions/discovery_oak_lock.json && git commit -m "chore(exclusions): discovery_oak FINAL lockfile"
```

---

## 6. Part E — lev2 (group models)

**What / why:** second-level group stats per base-task contrast. Surface uses a seeded
sign-flip permutation (reproducible); volume uses FSL randomise (verify seed support).
Both drop `_desc-belowMinRuns` inputs.

```bash
uv run neuro-run submit lev2 discovery_oak --space surface --num-permutations 5000 --seed 0 --time 04:00:00
uv run neuro-run submit lev2 discovery_oak --space volume  --num-permutations 5000 --time 04:00:00
rsync -avP $STAGE/discovery/derivatives/lev2_* $BIDSROOT/discovery/derivatives/       # if staged to scratch
```

---

## 7. Part F — Reproduce certification

**What:** re-point the reproduction harness at the Oak datasets and confirm it PASSes all
three diffs (filenames / exclusion set / lev2-eligible).
**Why:** this is the machine-checked proof that the Oak datasets reproduce from the frozen
snapshot + real inputs.

```bash
uv run python scripts/reproduce_cohort.py discovery \
  --bids-root $BIDSROOT/discovery \
  --lev1-outliers-csv $STAGE/qa_lev1_discovery/lev1_outliers.csv \
  --out $STAGE/reproduce_discovery.md            # exit 0 + first line "PASS"; exit 2 = prereq missing; exit 1 = divergence
```

---

## 8. Part G — Finalize (lock + read-only)

**What:** commit the final state, lock the annex (collapse working copies to symlinks),
then drop write bits — **in that order** (chmod last, or the save/lock cannot write).
**Why:** produces the immutable, backed-up dataset. Do this for all three cohorts.

```bash
export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
for c in discovery validation excluded; do
  git -C $BIDSROOT/$c annex add . ; git -C $BIDSROOT/$c commit -m "finalize: full reproducible state" || true
  git -C $BIDSROOT/$c annex lock . || true
  find $BIDSROOT/$c -type f -exec chmod a-w {} + 2>/dev/null || true
  find $BIDSROOT/$c -type d -exec chmod a-w {} + 2>/dev/null || true
done
```

Record the run (live-pull date, code SHA, final lockfile SHA + per-source counts, every
gate outcome, the reproduce PASS line, dataset commit SHAs) in
`docs/REEXECUTION-RUN-LOG.md`.

---

## 9. Command index

| Stage | Command | Produces |
|-------|---------|----------|
| Drift Gate | `capture_fw_inventory.py <cohort>` + roster-scoped timeline diff | drift verdict |
| bidsify | `neuro-run submit bidsify <sample> --output-dir <oak>` | raw BIDS on Oak |
| trim | `scripts/trim_bold.py <bids>` | 7-vol-trimmed BOLD + sidecars |
| reconcile | `scripts/reconcile_sessions.py …` | behavioral↔BOLD manifest (diff vs committed) |
| migrate | `scripts/migrate_behavioral.py …` | `<bids>/sourcedata/in_scanner_behavior` |
| events | `neuro-run events create/qc <ds> --behavioral-dir …` | `_events.tsv` + behavioral-qc source |
| validate | `bids-validator … <bids>` | 0 errors |
| exclusions | `neuro-run exclusions generate/compile/render-bidsignore/render-md <ds>` | sources → compiled + lockfile → `.bidsignore`/`EXCLUSIONS.md` |
| gate | `scripts/exclusion_gate.py --new … --reference … [--source …]` | drift report; exit 3 on change |
| fMRIPrep | `neuro-run submit fmriprep <ds> --version 25.2.4 --nthreads 24 --mem-per-cpu-gb 7 …` | `derivatives/fmriprep_25.2.4` |
| views | `scripts/build_xcpd_view.py <ds> --fmriprep-version 25.2.4` | `fmriprep_*_input` / `xcp_d_*_input` |
| lev1 | `neuro-run submit lev1 <ds> --base-tasks --space fsaverage6 --residuals --min-runs 2` | `derivatives/lev1_surface` |
| cohort QC | `neuro-run submit qa lev1 <ds> --output-dir …` | `lev1_outliers.csv` |
| lev2 | `neuro-run submit lev2 <ds> --space surface|volume --num-permutations 5000` | group stat maps |
| reproduce | `scripts/reproduce_cohort.py <cohort> --bids-root <oak>` | PASS/FAIL certificate |

## 10. Notes

- **Single subject:** add `--subjects sXX` to `bidsify` (metadata written to `_rerun-sXX`
  suffixed files so full-run logs are not clobbered).
- **Config lives in code:** subject rosters/aliases/overrides in
  `config/pipeline_config.json`; thresholds (motion FD/DVARS, VIF) in
  `config/thresholds.yaml`; task battery + contrasts in
  `src/neuro_workflow/analysis/task_config/`.
- **Dual tasks** (10 `*W*` tasks) have placeholder YAMLs → no lev1/lev2 until real
  regressor/contrast configs are authored (documented follow-on).
- **Tests:** `srun -p dev -t 00:15:00 --mem=4G /bin/bash -lc 'module load uv && cd <repo> && uv run pytest tests/ -q'`.
