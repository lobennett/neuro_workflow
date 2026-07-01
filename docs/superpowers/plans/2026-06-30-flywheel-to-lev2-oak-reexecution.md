# Flywheel→lev2 Re-execution to Oak — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-execute the pipeline end-to-end (live Flywheel → BIDS → fMRIPrep → lev1 surface → lev2) into fresh, version-controlled, read-only datalad datasets on Oak, with exclusions gated for zero silent drift at each stage.

**Architecture:** A staged linear run with a datalad commit and an exclusion diff-gate at each stage where new exclusion evidence appears (BIDS → +motion after fMRIPrep → +lev1_outlier after lev1). A small amount of enabling code (Phase 0) makes paths retargetable and adds the gate; Phases 1–6 are operational SLURM stages verified by gates, not unit tests.

**Tech Stack:** Python 3.12 + `uv`; `neuro-run` CLI; SLURM (russpold/normal); Apptainer (fMRIPrep 25.2.4, neuro_workflow.sif); git-annex 8 / datalad; pytest.

**Design doc:** `docs/superpowers/specs/2026-06-30-flywheel-to-lev2-oak-reexecution-design.md`

**Working checkout:** `/scratch/users/logben/neuro_workflow_refactor`, branch `repro-harness-2026-06`. All `uv run` / `git` commands run from there. `module load uv` first. NEVER run Python on the login node — offload to `sbatch` or `sh_dev`.

---

## Conventions used throughout

- **Cohorts:** analysis cohorts = `discovery`, `validation`. `excluded` is a **BIDS-only** cohort (Phases 0/1/6 only).
- **Oak dataset roots (new, non-colliding):**
  - `OAK_DISC=/oak/stanford/groups/russpold/data/network_grant/bids/discovery`
  - `OAK_VAL=/oak/stanford/groups/russpold/data/network_grant/bids/validation`
  - `OAK_EXC=/oak/stanford/groups/russpold/data/network_grant/bids/excluded`
- **Raw behavioral (read-only source):** `/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned` (call it `$RAW_CLEANED`).
- **Scratch derivative staging root:** `/scratch/users/logben/oak_reexec/<cohort>/derivatives` (compute writes here; rsync to Oak).
- **NO-OVERWRITE GUARDRAIL:** never write to `/oak/.../network_grant/{discovery_BIDS_20250402,validation_BIDS,sourcedata}` or any pre-existing Oak tree. Only the three new `bids/{...}` roots are written.
- **git-annex on the login node is unavailable** and the group datalad module is broken. Any `datalad`/`git annex` operation on a BIDS dataset runs inside a SLURM job (or `sh_dev`) using the user-local `datalad` (`~/.local/bin/datalad`) with `/share/software/user/open/git-annex/8.20210622` on `PATH`.
- **Code repo commits** (the `neuro_workflow_refactor` worktree) are plain git — normal `git add <path> && git commit` is safe here (NOT an annex repo).

---

## File Structure

**Code created:**
- `scripts/exclusion_gate.py` — the per-stage exclusion diff-gate (new/reference compiled-exclusions keyset diff, source-scoped, non-zero exit on drift).
- `tests/scripts/test_exclusion_gate.py` — unit tests for the gate.
- `tests/scripts/test_reproduce_cohort_paths.py` — unit tests for the reproduce_cohort `--bids-root` retarget.

**Code modified:**
- `scripts/reproduce_cohort.py` — add `_resolve_cohort_paths(cohort, bids_root=None, lev1_outliers_csv=None)` + `--bids-root` / `--lev1-outliers-csv` CLI flags.
- `src/neuro_workflow/templates/bidsify.sbatch` — add `-B /oak:/oak` to the `apptainer run` line.

**Docs/data created:**
- `data/exclusions/{discovery,validation}_reference_compiled.json` — frozen copy of the current validated compiled exclusion set (the gate's reference).
- `docs/REEXECUTION-RUN-LOG.md` — the executability-proof run log + provenance manifest.

**Untracked artifacts committed (Phase 0):**
- `data/repro/fw_inventory_{discovery,validation}.json`, `config/manifests/qc_decisions.tsv`, and the lev1_outliers reference CSVs.

---

## Phase 0 — Pre-flight & enabling code (no heavy compute)

### Task 0.1: Commit the untracked determinism artifacts

**Files:**
- Modify (git-track): `data/repro/fw_inventory_discovery.json`, `data/repro/fw_inventory_validation.json`, `config/manifests/qc_decisions.tsv`

- [ ] **Step 1: Inspect what is untracked**

Run: `cd /scratch/users/logben/neuro_workflow_refactor && git status --porcelain data/repro config/manifests`
Expected: shows `??` for `data/repro/fw_inventory_*.json` and any untracked reference inputs.

- [ ] **Step 2: Stage and commit the snapshots + qc decisions**

```bash
cd /scratch/users/logben/neuro_workflow_refactor
git add data/repro/fw_inventory_discovery.json data/repro/fw_inventory_validation.json config/manifests/qc_decisions.tsv
git commit -m "chore(repro): commit Flywheel inventory snapshots + qc_decisions reference

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Freeze the current validated compiled exclusion set as the gate reference**

The committed lockfiles are provenance-only; the enumerated set lives at `~/.neuro_workflow/exclusions/<cohort>/compiled_exclusions.json`. Copy each into the repo as the gate reference.

```bash
cd /scratch/users/logben/neuro_workflow_refactor
cp ~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json data/exclusions/discovery_reference_compiled.json
cp ~/.neuro_workflow/exclusions/validation/compiled_exclusions.json data/exclusions/validation_reference_compiled.json
git add data/exclusions/discovery_reference_compiled.json data/exclusions/validation_reference_compiled.json
git commit -m "chore(exclusions): freeze current validated compiled set as gate reference

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

Expected: both files exist; `python -c "import json;print(len(json.load(open('data/exclusions/discovery_reference_compiled.json'))))"` prints 44 (discovery) / 142 (validation) — matching the committed lockfile `n_total_entries`. If counts differ, STOP: the machine-local compiled set is stale; run `uv run neuro-run exclusions compile <cohort>` first and re-verify.

### Task 0.2: Pin flywheel-sdk

**Files:**
- Modify: `pyproject.toml` (the `[bidsify]` optional-dependency group)

- [ ] **Step 1: Read the current pin**

Run: `grep -n "flywheel" pyproject.toml uv.lock | head`
Expected: `pyproject.toml` shows `flywheel-sdk>=17.0`; `uv.lock` resolves a concrete version (e.g. `21.5.0`).

- [ ] **Step 2: Pin to the locked version**

Edit `pyproject.toml`: change `flywheel-sdk>=17.0` to `flywheel-sdk==<version from uv.lock>` (use the exact version `uv.lock` resolved).

- [ ] **Step 3: Re-lock and verify unchanged resolution**

Run: `module load uv && uv lock && git diff uv.lock`
Expected: no change to the flywheel-sdk resolved version (the pin matches what was already resolved).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: pin flywheel-sdk to locked version for reproducible live pull

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 0.3: Add the `/oak` bind to bidsify.sbatch

**Files:**
- Modify: `src/neuro_workflow/templates/bidsify.sbatch:18`
- Test: `tests/pipelines/test_bidsify.py` (add a template-content assertion; create the test module if absent)

- [ ] **Step 1: Write the failing test**

```python
# tests/pipelines/test_bidsify.py
from pathlib import Path

def test_bidsify_template_binds_oak():
    tmpl = Path("src/neuro_workflow/templates/bidsify.sbatch").read_text()
    # /oak must be bound so bidsify can write BIDS output to an Oak target dir
    # (Sherlock apptainer does not guarantee an /oak auto-mount).
    assert "-B /oak:/oak" in tmpl
    assert "apptainer run" in tmpl
```

- [ ] **Step 2: Run test to verify it fails**

Run: `module load uv && uv run pytest tests/pipelines/test_bidsify.py::test_bidsify_template_binds_oak -v`
Expected: FAIL (`-B /oak:/oak` not in template).

- [ ] **Step 3: Edit the template**

In `src/neuro_workflow/templates/bidsify.sbatch`, change line 18 from:
```
apptainer run "$CONTAINER" bidsify {sample} \
```
to:
```
apptainer run -B /oak:/oak "$CONTAINER" bidsify {sample} \
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipelines/test_bidsify.py::test_bidsify_template_binds_oak -v`
Expected: PASS.

- [ ] **Step 5: Run the dynamic template-render meta-test (safety net for missing keys)**

Run: `uv run pytest tests/pipelines/ -k template -v`
Expected: PASS (the bind is a literal, adds no new `{placeholder}`).

- [ ] **Step 6: Commit**

```bash
git add src/neuro_workflow/templates/bidsify.sbatch tests/pipelines/test_bidsify.py
git commit -m "feat(bidsify): bind /oak in sbatch so bidsify can target Oak output

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 0.4: Retarget reproduce_cohort with `--bids-root`

**Files:**
- Modify: `scripts/reproduce_cohort.py` (add `_resolve_cohort_paths`; wire into `main` + `_parse_args`)
- Test: `tests/scripts/test_reproduce_cohort_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_reproduce_cohort_paths.py
from pathlib import Path
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "reproduce_cohort", "scripts/reproduce_cohort.py")
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def test_default_paths_unchanged():
    p = rc._resolve_cohort_paths("discovery")
    assert p["bids"] == Path("/scratch/users/logben/discovery_bids")
    assert p["committed_bidsignore"] == Path("/scratch/users/logben/discovery_bids/.bidsignore")


def test_bids_root_override_recomputes_derived_paths():
    root = Path("/oak/stanford/groups/russpold/data/network_grant/bids/discovery")
    p = rc._resolve_cohort_paths("discovery", bids_root=root)
    assert p["bids"] == root
    assert p["fmriprep_src"] == root / "derivatives" / "fmriprep_25.2.4"
    assert p["lev1_fe_dir"] == root / "derivatives" / "lev1_surface"
    assert p["committed_bidsignore"] == root / ".bidsignore"
    # snapshot / behavioral / decisions_tsv are NOT under the bids root
    assert p["snapshot"] == rc._COHORT_PATHS["discovery"]["snapshot"]
    assert p["behavioral"] == rc._OAK_BEHAVIORAL


def test_lev1_outliers_csv_override():
    p = rc._resolve_cohort_paths(
        "discovery", lev1_outliers_csv=Path("/tmp/x.csv"))
    assert p["lev1_outliers_csv"] == Path("/tmp/x.csv")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scripts/test_reproduce_cohort_paths.py -v`
Expected: FAIL (`_resolve_cohort_paths` not defined).

- [ ] **Step 3: Add `_resolve_cohort_paths` to `scripts/reproduce_cohort.py`**

Insert after the `_COHORT_PATHS` dict (after line 94):

```python
def _resolve_cohort_paths(cohort: str, *, bids_root: Path | None = None,
                          lev1_outliers_csv: Path | None = None) -> dict:
    """Return the cohort path dict, optionally retargeted to a new BIDS root.

    When ``bids_root`` is given, the four BIDS-derived paths (bids, fmriprep_src,
    lev1_fe_dir, committed_bidsignore) are recomputed under it — so the same
    reproduction can certify the Oak datasets. Non-BIDS-derived paths (snapshot,
    behavioral, decisions_tsv) are unchanged. ``lev1_outliers_csv`` overrides the
    lev1-outlier reference CSV location (regenerated on Oak).
    """
    base = dict(_COHORT_PATHS[cohort])
    ver = base["fmriprep_version"]
    if bids_root is not None:
        bids_root = Path(bids_root)
        base["bids"] = bids_root
        base["fmriprep_src"] = bids_root / "derivatives" / f"fmriprep_{ver}"
        base["lev1_fe_dir"] = bids_root / "derivatives" / "lev1_surface"
        base["committed_bidsignore"] = bids_root / ".bidsignore"
    if lev1_outliers_csv is not None:
        base["lev1_outliers_csv"] = Path(lev1_outliers_csv)
    return base
```

- [ ] **Step 4: Wire it into `main` and `_parse_args`**

In `main`, replace `paths = _COHORT_PATHS[cohort]` (line 410) with:
```python
    paths = _resolve_cohort_paths(
        cohort, bids_root=getattr(_MAIN_ARGS, "bids_root", None),
        lev1_outliers_csv=getattr(_MAIN_ARGS, "lev1_outliers_csv", None))
```
Add a module-level `_MAIN_ARGS = None` near the top (after imports), and in the `__main__` block set it before calling `main`:
```python
if __name__ == "__main__":
    args = _parse_args()
    _MAIN_ARGS = args
    main(args.cohort, args.out)
    report_text = args.out.read_text()
    sys.exit(0 if "PASS" in report_text.splitlines()[0] else 1)
```
In `_parse_args`, add:
```python
    parser.add_argument("--bids-root", type=Path, default=None,
        help="Retarget all BIDS-derived paths to this dataset root (e.g. the Oak dataset).")
    parser.add_argument("--lev1-outliers-csv", type=Path, default=None,
        help="Override the lev1_outliers.csv reference path.")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/scripts/test_reproduce_cohort_paths.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add scripts/reproduce_cohort.py tests/scripts/test_reproduce_cohort_paths.py
git commit -m "feat(reproduce): --bids-root retarget so Oak datasets can be certified

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 0.5: Create the exclusion diff-gate

**Files:**
- Create: `scripts/exclusion_gate.py`
- Test: `tests/scripts/test_exclusion_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/scripts/test_exclusion_gate.py
import json
from pathlib import Path
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "exclusion_gate", "scripts/exclusion_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)


def _entry(sub, ses, task, run, action="exclude", source="motion", contrast=None, reason="r"):
    return {"subject": sub, "session": ses, "task": task, "run": run,
            "action": action, "source": source, "contrast": contrast, "reason": reason}


def _write(tmp_path, name, entries):
    p = tmp_path / name
    p.write_text(json.dumps(entries))
    return p


def test_identical_sets_no_drift(tmp_path):
    ref = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1")]
    new = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1")]
    r = _write(tmp_path, "ref.json", ref)
    n = _write(tmp_path, "new.json", new)
    result = gate.diff_gate(new_path=n, reference_path=r)
    assert result["added"] == [] and result["dropped"] == []
    assert result["ok"] is True


def test_added_and_dropped_detected(tmp_path):
    ref = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1")]
    new = [_entry("sub-s2", "ses-02", "task-flanker", "run-2")]
    result = gate.diff_gate(
        new_path=_write(tmp_path, "new.json", new),
        reference_path=_write(tmp_path, "ref.json", ref))
    assert result["ok"] is False
    assert len(result["added"]) == 1 and len(result["dropped"]) == 1


def test_source_filter_scopes_the_diff(tmp_path):
    # ref has a motion + a behavioral entry; new drops the behavioral one.
    ref = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1", source="motion"),
           _entry("sub-s9", "ses-09", "task-nBack", "run-1", source="behavioral-qc")]
    new = [_entry("sub-s1", "ses-01", "task-goNogo", "run-1", source="motion")]
    # Scoped to motion → no drift (motion identical).
    res_motion = gate.diff_gate(
        new_path=_write(tmp_path, "new.json", new),
        reference_path=_write(tmp_path, "ref.json", ref), source="motion")
    assert res_motion["ok"] is True
    # Unscoped → the behavioral drop shows.
    res_all = gate.diff_gate(
        new_path=_write(tmp_path, "new2.json", new),
        reference_path=_write(tmp_path, "ref2.json", ref))
    assert res_all["ok"] is False and len(res_all["dropped"]) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/scripts/test_exclusion_gate.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `scripts/exclusion_gate.py`**

```python
#!/usr/bin/env python3
"""exclusion_gate.py — halt on undeliberate exclusion drift.

Diffs a NEWLY-compiled exclusion set against a frozen REFERENCE set (the current
validated compiled exclusions) using the provenance-stripped 7-tuple keyset.
Optionally scopes the diff to one ``source`` (motion, lev1_outlier, …) so a stage
that only just gained a source is compared like-for-like. Exit 0 = no drift;
exit 3 = drift (distinct from other scripts' exit codes). Every added/dropped
scan is printed with its evidence and written to a Markdown report.

Usage::

    uv run python scripts/exclusion_gate.py \
        --new  ~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json \
        --reference data/exclusions/discovery_reference_compiled.json \
        --source motion \
        --report /scratch/users/logben/oak_reexec/gate_discovery_motion.md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from neuro_workflow.testing.reproduce.canonical import compiled_to_keyset


def _load(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text())
    # compiled files are a bare list of entry dicts
    return data if isinstance(data, list) else data.get("exclusions", data)


def _keyset(entries: list[dict], source: str | None) -> set:
    ks = compiled_to_keyset(entries)
    if source is not None:
        ks = {t for t in ks if t[5] == source}  # element 5 = source
    return ks


def _entries_for_keys(entries: list[dict], keys: set) -> list[dict]:
    """Return the full entry dicts (with evidence) matching a set of 7-tuples."""
    from neuro_workflow.testing.reproduce.canonical import compiled_to_keyset as _k
    out = []
    for e in entries:
        # recompute this entry's tuple; keep if in keys
        for t in _k([e]):
            if t in keys:
                out.append(e)
    return out


def diff_gate(*, new_path: Path, reference_path: Path,
              source: str | None = None) -> dict:
    """Return {ok, added, dropped} — added = in new not reference; dropped = reverse."""
    new_entries = _load(new_path)
    ref_entries = _load(reference_path)
    new_ks = _keyset(new_entries, source)
    ref_ks = _keyset(ref_entries, source)
    added_keys = new_ks - ref_ks
    dropped_keys = ref_ks - new_ks
    return {
        "ok": not added_keys and not dropped_keys,
        "added": _entries_for_keys(new_entries, added_keys),
        "dropped": _entries_for_keys(ref_entries, dropped_keys),
        "source": source,
    }


def _render(result: dict) -> str:
    lines = [f"# Exclusion gate — {'PASS (no drift)' if result['ok'] else 'DRIFT DETECTED'}",
             f"source filter: {result['source'] or '(all)'}", ""]
    for label, key in (("ADDED (in new, not reference)", "added"),
                       ("DROPPED (in reference, not new)", "dropped")):
        lines.append(f"## {label}: {len(result[key])}")
        for e in result[key]:
            lines.append(
                f"- {e['subject']} {e['session']} {e['task']} {e['run']} "
                f"[{e.get('source')}] {e.get('action')} "
                f"contrast={e.get('contrast')} — {e.get('reason')}")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--new", required=True, type=Path)
    p.add_argument("--reference", required=True, type=Path)
    p.add_argument("--source", default=None,
                   help="Scope the diff to one source (e.g. motion, lev1_outlier).")
    p.add_argument("--report", type=Path, default=None)
    a = p.parse_args(argv)
    result = diff_gate(new_path=a.new, reference_path=a.reference, source=a.source)
    report = _render(result)
    print(report)
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(report)
        print(f"report: {a.report}")
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/scripts/test_exclusion_gate.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/exclusion_gate.py tests/scripts/test_exclusion_gate.py
git commit -m "feat(exclusions): per-stage exclusion diff-gate (halt on undeliberate drift)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 0.6: Verify the `/oak` apptainer bind operationally

- [ ] **Step 1: Confirm the container can see Oak**

Run:
```bash
apptainer exec -B /oak:/oak /home/groups/russpold/singularity_images/neuro_workflow.sif ls /oak/stanford/groups/russpold/data/network_grant/ | head
```
Expected: lists the Oak directory contents (confirms the bind works). If it errors, STOP and resolve binds before Phase 1.

### Task 0.7: Create the Oak datalad datasets + register them

**Files:** none in-repo; creates Oak datasets + `~/.neuro_workflow/datasets.json` entries.

- [ ] **Step 1: Assert the Oak targets do NOT already exist (no-overwrite guardrail)**

Run:
```bash
for d in /oak/stanford/groups/russpold/data/network_grant/bids/discovery \
         /oak/stanford/groups/russpold/data/network_grant/bids/validation \
         /oak/stanford/groups/russpold/data/network_grant/bids/excluded; do
  if [ -e "$d" ]; then echo "ABORT: target exists: $d"; else echo "OK (new): $d"; fi
done
```
Expected: all three print `OK (new)`. If any exists, STOP and choose a fresh path.

- [ ] **Step 2: Create the three datalad datasets in a `sh_dev` shell (annex available)**

Run (in `sh_dev`, with git-annex on PATH):
```bash
export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
mkdir -p /oak/stanford/groups/russpold/data/network_grant/bids
for c in discovery validation excluded; do
  ~/.local/bin/datalad create -c text2git \
    /oak/stanford/groups/russpold/data/network_grant/bids/$c
done
```
Note: `-c text2git` puts small text files in git and annexes large binaries — mirroring the scratch datasets. Verify each has `.datalad/config` and `.git/annex`.

- [ ] **Step 3: Copy the `.gitattributes` annex policy from an existing dataset**

Run:
```bash
for c in discovery validation excluded; do
  cp /scratch/users/logben/discovery_bids/.gitattributes \
     /oak/stanford/groups/russpold/data/network_grant/bids/$c/.gitattributes
done
```
Expected: each Oak dataset now has `* annex.backend=MD5E`, `**/.git* annex.largefiles=nothing`, `.bidsignore annex.largefiles=nothing`.

- [ ] **Step 4: Write a minimal subjects file per cohort (add-dataset requires it)**

Run:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
mkdir -p /scratch/users/logben/oak_reexec
for c in discovery validation excluded; do
  uv run python -c "import json,sys; cfg=json.load(open('config/pipeline_config.json')); s=cfg['samples']['$c']; ids=list(s.keys()) if isinstance(s,dict) else s; open('/scratch/users/logben/oak_reexec/subjects_$c.txt','w').write('\n'.join(ids)+'\n')"
done
cat /scratch/users/logben/oak_reexec/subjects_discovery.txt
```
Expected: discovery file lists 5 subject IDs.

- [ ] **Step 5: Register the Oak datasets**

Run:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
uv run neuro-run add-dataset discovery_oak --bids-dir /oak/stanford/groups/russpold/data/network_grant/bids/discovery --subjects-file /scratch/users/logben/oak_reexec/subjects_discovery.txt
uv run neuro-run add-dataset validation_oak --bids-dir /oak/stanford/groups/russpold/data/network_grant/bids/validation --subjects-file /scratch/users/logben/oak_reexec/subjects_validation.txt
uv run neuro-run add-dataset excluded_oak --bids-dir /oak/stanford/groups/russpold/data/network_grant/bids/excluded --subjects-file /scratch/users/logben/oak_reexec/subjects_excluded.txt
```
Expected: `~/.neuro_workflow/datasets.json` gains `discovery_oak`, `validation_oak`, `excluded_oak`. The scratch `discovery`/`validation` entries are untouched (cross-check reference).

> **IMPORTANT:** the sample name passed to `bidsify`/`events`/`exclusions`/`lev1`/`lev2` must still be the canonical roster name (`discovery`/`validation`/`excluded`) for subject resolution from `pipeline_config.json`, while the **dataset registration** name is `<cohort>_oak` for path resolution. Where a command takes a *dataset* arg it resolves `bids_dir` from the registry; where it takes a *sample* it resolves the roster. Confirm each command's arg meaning with `--help` before the first real run of that command.

---

## Phase 1 — Flywheel→BIDS (per cohort) → datalad commit #1

> Run Phase 1 for `discovery` first end-to-end as the pilot, verify, then `validation`, then `excluded`. Each cohort is independent.

### Task 1.1: Drift Gate — capture fresh inventory + diff vs committed snapshot

- [ ] **Step 1: Capture a fresh Flywheel inventory (needs Flywheel auth)**

Run (in `sh_dev`, flywheel-sdk installed, `~/.config/flywheel/user.json` present):
```bash
cd /scratch/users/logben/neuro_workflow_refactor
uv run python scripts/capture_fw_inventory.py discovery --out /scratch/users/logben/oak_reexec/fw_inventory_discovery_fresh.json
```
Expected: `wrote … (N subjects)`.

- [ ] **Step 2: Diff fresh vs committed snapshot (the Drift Gate)**

Run:
```bash
diff <(python -m json.tool data/repro/fw_inventory_discovery.json) \
     <(python -m json.tool /scratch/users/logben/oak_reexec/fw_inventory_discovery_fresh.json) | head -80
```
Expected: **no differences in subject/session/acquisition structure**. Timestamps/echoes/labels identical → session numbering (`ses-NN`, timestamp-derived) is stable → exclusion keys remain valid.

- [ ] **Step 3: GATE**

If the diff shows any added/removed acquisition or any change that would reorder sessions (timestamps), **STOP** and review with the user: a renumbered `ses-NN` invalidates exclusion keys. Only proceed when the diff is empty (or every difference is understood and confirmed inert). Record the outcome in `docs/REEXECUTION-RUN-LOG.md` (created in Phase 6; append as you go).

### Task 1.2: Live bidsify to Oak + trim

- [ ] **Step 1: Submit live bidsify to the Oak target**

Run:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
uv run neuro-run submit bidsify discovery \
  --output-dir /oak/stanford/groups/russpold/data/network_grant/bids/discovery \
  --overwrite --time 04:00:00 --mem-gb 16
```
Expected: prints the rendered sbatch (with `-B /oak:/oak`) and a submitted job id. Watch: `squeue --me`.

- [ ] **Step 2: Verify BIDS produced + no per-subject failures**

Run:
```bash
ls /oak/stanford/groups/russpold/data/network_grant/bids/discovery/sub-*/ | head
grep -i "Failed to process" /oak/stanford/groups/russpold/data/network_grant/bids/discovery/sourcedata/logs/*.err /oak/stanford/groups/russpold/data/network_grant/bids/discovery/*.log 2>/dev/null || echo "no per-subject failures logged"
```
Expected: subject dirs present; no `Failed to process` (the silent per-subject swallow). If any subject failed, STOP and investigate (e.g. null session timestamp).

- [ ] **Step 3: Trim dummy volumes**

Run:
```bash
uv run python scripts/trim_bold.py /oak/stanford/groups/russpold/data/network_grant/bids/discovery
```
Expected: trims 7 dummy vols per BOLD (idempotent). Spot-check a sidecar: `NumberOfVolumesDiscardedByUser` == 7.

### Task 1.3: Reconcile behavioral (reuse committed manifest)

- [ ] **Step 1: Re-run reconcile in report mode to surface NEW pending rows only**

Run:
```bash
uv run python scripts/reconcile_sessions.py \
  --raw-dir "/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned" \
  --bids-dir /oak/stanford/groups/russpold/data/network_grant/bids/discovery \
  --scan-notes docs/SCAN-NOTES.md \
  --output /scratch/users/logben/oak_reexec/reconciliation_discovery_fresh.tsv
```

- [ ] **Step 2: Diff fresh reconcile vs committed manifest**

Run:
```bash
diff <(cut -f1-6 config/manifests/reconciliation_discovery.tsv | sort) \
     <(cut -f1-6 /scratch/users/logben/oak_reexec/reconciliation_discovery_fresh.tsv | sort) | head -60
```
Expected: the matched-scan rows agree. Any NEW `pending` rows (unmatched) must be human-reviewed. **Reuse the committed `config/manifests/reconciliation_discovery.tsv`** (with its human `action`/`dest_session`/`dest_run` decisions) for migration — do NOT overwrite it with the fresh one.

- [ ] **Step 3: GATE**

If new pending rows exist, STOP and review with the user; update the committed manifest deliberately. Otherwise proceed with the committed manifest.

### Task 1.4: Migrate behavioral into the dataset's own sourcedata

- [ ] **Step 1: Migrate**

Run:
```bash
uv run python scripts/migrate_behavioral.py \
  --manifest config/manifests/reconciliation_discovery.tsv \
  --raw-dir "/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned" \
  --output-dir /oak/stanford/groups/russpold/data/network_grant/bids/discovery/sourcedata \
  --sample discovery --strict
```
Expected: writes `in_scanner_behavior/sub-*/ses-*/beh/*.csv` under the dataset's own sourcedata; `migration_report.json` written; `--strict` aborts if any manifest row is still `pending`.

### Task 1.5: Generate events + behavioral QC

- [ ] **Step 1: Create events**

Run:
```bash
uv run neuro-run events create discovery_oak --behavioral-dir /oak/stanford/groups/russpold/data/network_grant/bids/discovery/sourcedata/in_scanner_behavior
```
Expected: `_events.tsv` written for non-rest tasks under each `func/`; onsets shifted by 10.43 s; non-monotonic tails truncated.

- [ ] **Step 2: Run behavioral QC (produces the behavioral-qc exclusion source)**

Run:
```bash
uv run neuro-run events qc discovery_oak --behavioral-dir /oak/stanford/groups/russpold/data/network_grant/bids/discovery/sourcedata/in_scanner_behavior
```
Expected: `Saved N behavioral-qc exclusion entries` to `~/.neuro_workflow/exclusions/discovery_oak/sources/behavioral-qc.json`.

### Task 1.6: BIDS-validate

- [ ] **Step 1: Validate**

Run:
```bash
apptainer run -B /oak:/oak /home/groups/russpold/singularity_images/bids-validator_1.14.6.simg \
  /oak/stanford/groups/russpold/data/network_grant/bids/discovery 2>&1 | tail -30
```
Expected: 0 errors (warnings acceptable, matching the scratch dataset's known warning set).

### Task 1.7: Compile pre-fMRIPrep exclusions + Gate + datalad commit #1

- [ ] **Step 1: Generate collection + qa_decisions sources**

Run:
```bash
uv run neuro-run exclusions generate collection discovery_oak
uv run neuro-run exclusions generate qa_decisions discovery_oak --decisions-tsv config/manifests/qc_decisions.tsv
```
Expected: `Saved N entries` for each. (behavioral-qc was saved in Task 1.5. motion + lev1_outlier are NOT generated yet — their evidence doesn't exist.)

- [ ] **Step 2: Compile (behavioral + collection + qa_decisions only)**

Run:
```bash
uv run neuro-run exclusions compile discovery_oak
```
Expected: prints per-source counts (motion/lev1_outlier = 0 at this stage). Writes `~/.neuro_workflow/exclusions/discovery_oak/compiled_exclusions.json` + committed lockfile `data/exclusions/discovery_oak_lock.json`.

- [ ] **Step 3: Exclusion Gate — pre-fMRIPrep sources vs reference**

Run once per pre-fMRIPrep source (behavioral-qc, collection, qa_decisions):
```bash
for src in behavioral-qc collection qa_decisions; do
  uv run python scripts/exclusion_gate.py \
    --new ~/.neuro_workflow/exclusions/discovery_oak/compiled_exclusions.json \
    --reference data/exclusions/discovery_reference_compiled.json \
    --source $src \
    --report /scratch/users/logben/oak_reexec/gate_discovery_$src.md || echo "DRIFT in $src (exit $?)"
done
```
Expected: exit 0 (no drift) for each source. **GATE:** if any source drifts (exit 3), STOP, read the report, and review the added/dropped scans with the user before committing. `collection`/`qa_decisions` should match exactly (static inputs); `behavioral-qc` should match if behavioral CSVs + code are unchanged.

- [ ] **Step 4: Render the (partial) .bidsignore into the Oak dataset**

Run:
```bash
uv run neuro-run exclusions render-bidsignore discovery_oak --output /scratch/users/logben/oak_reexec/discovery.bidsignore
```
Then place it into the annex dataset WITHOUT writing through an annex symlink (`.bidsignore` is git-only per `.gitattributes`, so a plain copy is safe):
```bash
cp /scratch/users/logben/oak_reexec/discovery.bidsignore /oak/stanford/groups/russpold/data/network_grant/bids/discovery/.bidsignore
```

- [ ] **Step 5: datalad commit #1 (in sh_dev; annex available)**

Run (in `sh_dev`, git-annex on PATH):
```bash
export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
cd /oak/stanford/groups/russpold/data/network_grant/bids/discovery
~/.local/bin/datalad save -m "commit #1: raw BIDS + pre-fMRIPrep exclusions (behavioral/collection/qa)"
```
Expected: BIDS (annexed NIfTIs), sourcedata, events, `.bidsignore` committed. Verify: `git -C <dataset> log --oneline -1`.

- [ ] **Step 6: Commit the lockfile in the code repo**

```bash
cd /scratch/users/logben/neuro_workflow_refactor
git add data/exclusions/discovery_oak_lock.json
git commit -m "chore(exclusions): discovery_oak lockfile — pre-fMRIPrep sources

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Repeat Tasks 1.1–1.7 for `validation` (→ validation_oak) and `excluded` (→ excluded_oak)**

For `excluded`: run Steps 1.2–1.6 + commit #1, but note the excluded cohort has no lev1/lev2 downstream — its `.bidsignore` reflects only the pre-fMRIPrep sources and stays final for that cohort (no Gate A/B).

---

## Phase 2 — fMRIPrep (discovery + validation) → Gate A + datalad commit #2

### Task 2.1: Submit fMRIPrep against the FULL Oak BIDS

> Run against the **full** BIDS (not the `.bidsignore` view) so that excluded scans still get confounds — the motion generator needs them. Output to a scratch staging dir (Sherlock policy), then rsync to Oak in Task 2.3.

- [ ] **Step 1: Submit the array (russpold, medium throttle, production resources)**

Run:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
uv run neuro-run submit fmriprep discovery_oak \
  --version 25.2.4 \
  --output-dir /scratch/users/logben/oak_reexec/discovery/derivatives \
  --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage:den-41k fsnative T1w func" \
  --fmriprep-args "--cifti-output 91k --bold2anat-init t2w --subject-anatomical-reference first-lex" \
  --nthreads 24 --mem-per-cpu-gb 7 --time 2-00:00:00 --array-throttle 4
```
Expected: rendered sbatch shows `--array=1-5%4`, `--cpus-per-task 24`, `--mem-per-cpu 7G`, partition `russpold`; job id printed. (24×7×0.9 ≈ 151 GB `--mem_mb`, matching observed ~113 GB peak with headroom.)

> **Throttle note:** `%4` is "medium" — it leaves russpold headroom for the finishing iProc campaign. Raise to `%8` once iProc drains (`squeue --me | grep iproc` empty). Do NOT exceed the cohort size.

- [ ] **Step 2: Verify partition + resources before it runs wide**

Run: `scontrol show job <jobid> | grep -E "Partition|NumCPUs|MinMemory|ArrayTaskThrottle"`
Expected: `russpold`, 24 CPUs, ~7G/cpu, throttle 4.

### Task 2.2: Monitor to completion

- [ ] **Step 1: Poll every few minutes (NOT tight-loop)**

Run: `squeue --me -o "%.10i %.20j %.8T %.11M %R"`
Expected: array tasks progress `PD`→`R`→ complete. Median ~24 h/subject.

- [ ] **Step 2: Verify each subject finished successfully**

Run:
```bash
for s in $(cat /scratch/users/logben/oak_reexec/subjects_discovery.txt); do
  f=$(ls /scratch/users/logben/oak_reexec/discovery/derivatives/fmriprep_25.2.4/logs/*sub-$s* 2>/dev/null | tail -1)
  grep -l "fMRIPrep finished successfully" "$f" >/dev/null 2>&1 && echo "$s OK" || echo "$s CHECK"
done
```
Expected: all `OK`. Investigate any `CHECK` (the fmriprep#3634 benign exit-1 is handled by the template).

- [ ] **Step 3: Verify confounds exist for EXCLUDED scans too**

Run:
```bash
find /scratch/users/logben/oak_reexec/discovery/derivatives/fmriprep_25.2.4 -name "*_desc-confounds_timeseries.tsv" | wc -l
```
Expected: a count covering ALL processed BOLD (including scans that will be `.bidsignore`'d) — this is the motion generator's evidence.

### Task 2.3: rsync derivatives → Oak + build views

- [ ] **Step 1: rsync via DTN**

Run (from a DTN session or a data-transfer job):
```bash
rsync -avP /scratch/users/logben/oak_reexec/discovery/derivatives/fmriprep_25.2.4 \
  /oak/stanford/groups/russpold/data/network_grant/bids/discovery/derivatives/
```
Expected: full derivative tree lands under the Oak dataset's `derivatives/`.

- [ ] **Step 2: Register the fmriprep_dir + build the filtered views**

Run:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
uv run python scripts/build_xcpd_view.py discovery_oak --fmriprep-version 25.2.4
```
Expected: `fmriprep_25.2.4_input` (raw-BIDS view filtered by `.bidsignore`) + `xcp_d_26.0.2_input` (fMRIPrep-output view) built, dropping `.bidsignore`'d scan-keys. (If `build_xcpd_view.py` resolves `bids_dir` from the registry it auto-targets Oak; confirm with `--help`.)

### Task 2.4: Generate motion exclusions + Gate A + commit #2

- [ ] **Step 1: Generate the motion source from the fresh confounds**

Run:
```bash
uv run neuro-run exclusions generate motion discovery_oak --fmriprep-version 25.2.4
```
Expected: `Saved N entries` (fails loud if the confounds glob is empty — confirms Task 2.3 landed).

- [ ] **Step 2: Recompile (now behavioral+collection+qa+motion)**

Run: `uv run neuro-run exclusions compile discovery_oak`
Expected: per-source table now shows a non-zero `motion` count.

- [ ] **Step 3: Exclusion Gate A — motion vs reference**

Run:
```bash
uv run python scripts/exclusion_gate.py \
  --new ~/.neuro_workflow/exclusions/discovery_oak/compiled_exclusions.json \
  --reference data/exclusions/discovery_reference_compiled.json \
  --source motion \
  --report /scratch/users/logben/oak_reexec/gate_discovery_motion.md; echo "exit=$?"
```
Expected: `exit=0` (no motion drift). **GATE:** if `exit=3`, read the report — each added/dropped scan carries its FD/DVARS evidence. Since fMRIPrep is not byte-reproducible, a threshold-crossing change is *possible and legitimate*; review each with the user and decide adopt/override before committing. Nothing is committed until sign-off.

- [ ] **Step 4: Re-render .bidsignore + datalad commit #2**

Run:
```bash
uv run neuro-run exclusions render-bidsignore discovery_oak --output /scratch/users/logben/oak_reexec/discovery.bidsignore
cp /scratch/users/logben/oak_reexec/discovery.bidsignore /oak/stanford/groups/russpold/data/network_grant/bids/discovery/.bidsignore
```
Then in `sh_dev`:
```bash
export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
cd /oak/stanford/groups/russpold/data/network_grant/bids/discovery
~/.local/bin/datalad save -m "commit #2: + motion exclusions (post-fMRIPrep); derivatives staged"
```
And commit the lockfile in the code repo:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
git add data/exclusions/discovery_oak_lock.json
git commit -m "chore(exclusions): discovery_oak lockfile + motion (post-fMRIPrep)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Repeat Phase 2 for `validation` (→ validation_oak, `--array=1-41%4`)**

---

## Phase 3 — lev1 surface (8 base tasks) + cohort QC → Gate B + commit #3

### Task 3.1: Submit lev1 surface (base tasks only)

- [ ] **Step 1: Submit**

Run:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
uv run neuro-run submit lev1 discovery_oak \
  --base-tasks --space fsaverage6 --within-subject-threshold 1.0 \
  --residuals --min-runs 2 --time 2-00:00:00
```
Expected: `job_list.txt` = 5 subjects × 8 base tasks = 40 cells (discovery); array submitted on russpold. It reads BIDS events + fMRIPrep fsaverage6 GIFTI from the Oak dataset, honoring the compiled exclusions (`--exclusions-file` defaults to the compiled lockfile path for `discovery_oak`).

- [ ] **Step 2: Verify completion + fixed-effects present**

Run:
```bash
squeue --me | grep lev1 || echo "lev1 done"
ls /oak/stanford/groups/russpold/data/network_grant/bids/discovery/derivatives/lev1_surface/sub-*/*/fixed_effects/*_stat-fixed-effects.func.gii | wc -l
```
Expected: fixed-effects maps present (per subject × contrast × hemisphere), some possibly tagged `_desc-belowMinRuns`.

### Task 3.2: Cohort QC → lev1_outliers.csv

- [ ] **Step 1: Run cohort QC**

Run:
```bash
uv run neuro-run submit qa lev1 discovery_oak --output-dir /scratch/users/logben/oak_reexec/qa_lev1_discovery
```
(Confirm the exact `qa` subcommand + flag with `uv run neuro-run qa --help`; the cohort-QC entry produces `lev1_outliers.csv`.)
Expected: `/scratch/users/logben/oak_reexec/qa_lev1_discovery/lev1_outliers.csv` written.

### Task 3.3: Generate lev1_outlier exclusions + Gate B + final commit #3

- [ ] **Step 1: Generate the lev1_outlier source**

Run:
```bash
uv run neuro-run exclusions generate lev1_outlier discovery_oak \
  --lev1-outliers-csv /scratch/users/logben/oak_reexec/qa_lev1_discovery/lev1_outliers.csv
```
Expected: `Saved N entries` (per-contrast `exclude-contrast` actions).

- [ ] **Step 2: Recompile — all 5 sources, single clean SHA**

Run: `uv run neuro-run exclusions compile discovery_oak`
Expected: per-source table shows all of behavioral/collection/qa_decisions/motion/lev1_outlier.

- [ ] **Step 3: Exclusion Gate B — lev1_outlier vs reference AND full-set vs reference**

Run:
```bash
uv run python scripts/exclusion_gate.py \
  --new ~/.neuro_workflow/exclusions/discovery_oak/compiled_exclusions.json \
  --reference data/exclusions/discovery_reference_compiled.json \
  --source lev1_outlier \
  --report /scratch/users/logben/oak_reexec/gate_discovery_lev1_outlier.md; echo "exit=$?"
uv run python scripts/exclusion_gate.py \
  --new ~/.neuro_workflow/exclusions/discovery_oak/compiled_exclusions.json \
  --reference data/exclusions/discovery_reference_compiled.json \
  --report /scratch/users/logben/oak_reexec/gate_discovery_full.md; echo "exit=$?"
```
Expected: both `exit=0`. **GATE:** any drift → read reports (VIF/outlier evidence), review with the user, decide adopt/override, and only then commit.

- [ ] **Step 4: Render FINAL .bidsignore + EXCLUSIONS.md + datalad commit #3**

Run:
```bash
uv run neuro-run exclusions render-bidsignore discovery_oak --output /scratch/users/logben/oak_reexec/discovery.bidsignore
uv run neuro-run exclusions render-md discovery_oak --output /scratch/users/logben/oak_reexec/discovery_EXCLUSIONS.md
cp /scratch/users/logben/oak_reexec/discovery.bidsignore /oak/stanford/groups/russpold/data/network_grant/bids/discovery/.bidsignore
cp /scratch/users/logben/oak_reexec/discovery_EXCLUSIONS.md /oak/stanford/groups/russpold/data/network_grant/bids/discovery/EXCLUSIONS.md
```
Then in `sh_dev`:
```bash
export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
cd /oak/stanford/groups/russpold/data/network_grant/bids/discovery
~/.local/bin/datalad save -m "commit #3: FINAL exclusion set (all 5 sources) + lev1_surface derivatives"
```
And in the code repo:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
git add data/exclusions/discovery_oak_lock.json
git commit -m "chore(exclusions): discovery_oak FINAL lockfile (all 5 sources)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 5: Repeat Phase 3 for `validation` (→ validation_oak, 41×8 = 328 cells)**

---

## Phase 4 — lev2 (discovery + validation)

### Task 4.1: Submit lev2 (surface + volume)

- [ ] **Step 1: Surface lev2 (seeded sign-flip permutation)**

Run:
```bash
uv run neuro-run submit lev2 discovery_oak --space surface --num-permutations 5000 --seed 0 --time 04:00:00
```
Expected: one array task per base-task contrast; drops `_desc-belowMinRuns` inputs; outputs under the Oak dataset's `derivatives/lev2_surface/` (or `--results-dir` staging → rsync).

- [ ] **Step 2: Volume lev2 (verify randomise seed support first)**

Run: `uv run neuro-run submit lev2 discovery_oak --space volume --num-permutations 5000 --time 04:00:00`
Expected: FSL randomise TFCE outputs. If the installed `randomise` lacks seed support (a warning is logged), record that volume lev2 p-values are not seed-reproducible and treat the surface lev2 as the reproducible science path.

### Task 4.2: rsync lev2 outputs → Oak

- [ ] **Step 1: rsync any scratch-staged lev2 outputs into the Oak dataset**

Run: `rsync -avP /scratch/users/logben/oak_reexec/discovery/derivatives/lev2_* /oak/stanford/groups/russpold/data/network_grant/bids/discovery/derivatives/`
Expected: lev2 outputs present under the Oak dataset. Repeat for `validation`.

---

## Phase 5 — Reproduce certification (Oak)

### Task 5.1: Re-point reproduce_cohort at the Oak datasets → PASS

- [ ] **Step 1: Run reproduce_cohort against Oak (discovery)**

Run:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
uv run python scripts/reproduce_cohort.py discovery \
  --bids-root /oak/stanford/groups/russpold/data/network_grant/bids/discovery \
  --lev1-outliers-csv /scratch/users/logben/oak_reexec/qa_lev1_discovery/lev1_outliers.csv \
  --out /scratch/users/logben/oak_reexec/reproduce_discovery.md; echo "exit=$?"
```
Expected: `exit=0`; first report line contains `PASS`; all three diffs (Filenames / Exclusion set / Lev2-eligible) empty. Exit 2 = a prereq (e.g. `.bidsignore` content) is missing — fix and re-run. Exit 1 = real divergence — investigate the report's `only_produced`/`only_reference`.

- [ ] **Step 2: Run reproduce_cohort against Oak (validation)**

Run the same with `validation` + its Oak root + its lev1_outliers CSV.
Expected: `exit=0`, `PASS`.

- [ ] **Step 3: Run the harness unit + e2e suite (regression safety net)**

Run: `uv run pytest tests/analysis/e2e tests/scripts -v`
Expected: all pass (Sherlock-gated cohort test may skip if a prereq is absent).

---

## Phase 6 — Finalize (all 3 cohorts)

### Task 6.1: Final datalad save + git annex lock (in a SLURM job)

- [ ] **Step 1: Save + lock each cohort in `sh_dev`**

Run (in `sh_dev`, git-annex on PATH):
```bash
export PATH=/share/software/user/open/git-annex/8.20210622:$PATH
for c in discovery validation excluded; do
  cd /oak/stanford/groups/russpold/data/network_grant/bids/$c
  ~/.local/bin/datalad save -m "finalize: full reproducible state"
  git annex lock . || true   # collapse unlocked working copies to symlinks (like excluded_bids)
done
```
Expected: clean `git status` (no typechanges) after lock; files are symlinks into `.git/annex/objects`.

### Task 6.2: chmod read-only (LAST — after all saves/locks)

- [ ] **Step 1: Drop write bits on each cohort**

Run:
```bash
for c in discovery validation excluded; do
  find /oak/stanford/groups/russpold/data/network_grant/bids/$c -type f -exec chmod a-w {} + 2>/dev/null || true
  find /oak/stanford/groups/russpold/data/network_grant/bids/$c -type d -exec chmod a-w {} + 2>/dev/null || true
done
```
Expected: files/dirs read-only (mirrors the sourcedata precedent). "Operation not permitted" on other users' files is expected and non-fatal.

### Task 6.3: Write the executability-proof run log + provenance manifest

**Files:**
- Create: `docs/REEXECUTION-RUN-LOG.md`

- [ ] **Step 1: Write the run log**

Record, per cohort: the live-pull date, the Drift Gate outcome, each stage's job id, the fMRIPrep version, the final exclusion lockfile SHA + per-source counts, every exclusion-gate outcome (and any human-adopted drift with rationale), the reproduce_cohort PASS line, and the Oak dataset datalad commit SHAs. This is the "pipeline is fully executable Flywheel→lev2" certificate.

- [ ] **Step 2: Commit the run log**

```bash
cd /scratch/users/logben/neuro_workflow_refactor
git add docs/REEXECUTION-RUN-LOG.md
git commit -m "docs: Flywheel→lev2 Oak re-execution run log + provenance

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

### Task 6.4: Full test suite + retire scratch

- [ ] **Step 1: Run the full suite**

Run: `uv run pytest tests/ --ignore=tests/analysis -v && uv run pytest tests/analysis -v`
Expected: green.

- [ ] **Step 2: Retire scratch (ONLY after both Oak reproduce PASSes are recorded)**

Leave the scratch datasets in place as the cross-check reference until the Oak PASS is confirmed and the user signs off. Then let the 90-day purge reclaim them (no manual delete needed). Record the decision in the run log.

---

## Self-Review notes (author)

- **Spec coverage:** Stage 0→Phase 0; Stage 1→Phase 1; Stage 2→Phase 2; Stage 3→Phase 3; Stage 4→Phase 4; Stage 5→Phase 5; Stage 6→Phase 6. Exclusion diff-gate → Task 0.5 + Gates in 1.7/2.4/3.3. No-overwrite guardrail → Task 0.7 Step 1 + conventions. Excluded-cohort-as-BIDS-only → Task 1.7 Step 7 + Phase 2/3 skip.
- **Deviation from spec §8 (justified):** only `reproduce_cohort` is retargeted (Task 0.4). `reconcile_audit.py` / `recompile_delta.py` / `remove_orphan_derivatives.py` are reconciliation-of-existing-dataset tools **not used** in a clean-slate run (no divergence audit; no orphans because fMRIPrep runs against full BIDS and confounds are retained; `recompile_delta`'s diff is superseded by the new `exclusion_gate.py`). If a later decision reintroduces orphan-stripping to save Oak space, retarget `remove_orphan_derivatives.py` then.
- **Type/name consistency:** `_resolve_cohort_paths` keys match `_COHORT_PATHS` (bids, fmriprep_src, lev1_fe_dir, committed_bidsignore, snapshot, behavioral, decisions_tsv, lev1_outliers_csv, fmriprep_version). Gate uses `compiled_to_keyset` 7-tuple element [5]=source (matches `canonical.py`). CLI verbs confirmed against source: `submit`, `events {create,qc}`, `exclusions {generate,compile,render-bidsignore,render-md}`, `add-dataset --bids-dir --subjects-file`.
- **Confirm-with-`--help` steps** are used only for the two commands whose flags weren't read in full during planning (`neuro-run qa lev1`, `build_xcpd_view.py` registry resolution) — verify before first real invocation.
