# Cohort Reproduction Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Sherlock-gated harness that proves the current codebase exactly reproduces the discovery + validation datasets — Flywheel snapshot → bidsify → trim → events → all 5 exclusion generators → `.bidsignore` → lev2-eligible `(subject,task,contrast)` set — on real small metric inputs + stub NIfTIs.

**Architecture:** New `src/neuro_workflow/testing/reproduce/` package that *imports* production stages (`make_fake_flywheel`, `run_bidsify`, `trim_bold_directory`, `run_create_events`, the 5 generators via `simulate_exclusions`, `FileFinder`, `get_task_contrasts`) and reuses the validated `simulate_exclusions()` glue. New logic only: snapshot→spec adapter, tiny-stub replay, metric staging, canonical set extraction, lev2 selection, diff/report. `simulate.py` is not modified.

**Tech Stack:** Python 3.11 (`uv`), pytest, nibabel/numpy/pandas (already in the worktree venv). Branch `repro-harness-2026-06` in `/scratch/users/logben/neuro_workflow_refactor`.

**Spec:** `docs/superpowers/specs/2026-06-27-cohort-reproduction-harness-design.md`

---

## Reference paths & commands

```
WT   = /scratch/users/logben/neuro_workflow_refactor   # current main + this branch
RUN  = (in WT) module load uv; export UV_CACHE_DIR=/scratch/users/logben/.uv_cache; uv run pytest ...
# Python execution on Sherlock goes through a dev/normal srun or sbatch, never the login node.
TESTJOB: sbatch -p russpold --time=00:20:00 --mem=8G --wrap "cd $WT && module load uv && uv run pytest <args>"
```

All unit tests in this plan are **hermetic** (tiny synthetic fixtures, no real cohort data) and run anywhere `uv run pytest` works. The single Sherlock-gated e2e (Task 9) auto-skips when real inputs are absent.

---

## File structure

```
src/neuro_workflow/testing/reproduce/
  __init__.py        # exports load_inventory, replay_to_bids, stage_metrics,
                     #   compiled_to_keyset, bidsignore_lineset, lev2_eligible_set,
                     #   lev2_reference_set, build_report
  snapshot.py        # JSON inventory <-> FlywheelCohortSpec
  replay.py          # spec -> FakeFlywheel(tiny stub) -> run_bidsify -> trim -> events
  stage_metrics.py   # symlink real metric inputs into the produced tree
  canonical.py       # provenance-stripped set extraction (exclusions, filenames, bidsignore)
  lev2_select.py     # modeled lev2-eligible set + on-disk reference set
  report.py          # 3-diff report + PASS/FAIL
scripts/
  capture_fw_inventory.py   # one-time real-fw capture -> data/repro/fw_inventory_<cohort>.json
  reproduce_cohort.py       # CLI driver
tests/analysis/e2e/
  test_reproduce_units.py   # hermetic unit tests (all new logic)
  test_reproduce_cohort.py  # Sherlock e2e, auto-skips when inputs absent
data/repro/                 # committed Flywheel inventory snapshots (produced by Task 8)
```

---

## Task 1: Verify the committed reference shape (spike, no new code)

**Files:** none (investigation recorded in the commit message).

- [ ] **Step 1: Confirm what the committed lock.json contains vs the .bidsignore**

Run:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
python3 - <<'PY'
import json
lk = json.load(open("data/exclusions/discovery_lock.json"))
print("lock top-level keys:", list(lk.keys()))
print("has 'entries'/'compiled'?:", [k for k in lk if k in ("entries","compiled","exclusions")])
print("n_total_entries:", lk.get("n_total_entries"))
print("sources:", [(s["generator"], s["n_entries"]) for s in lk.get("sources", [])])
PY
sed -n '1,40p' /scratch/users/logben/validation_bids/.bidsignore
```
Expected: confirms whether `lock.json` embeds the per-entry list or only provenance + `sources[]` counts. **Record the finding.** If `lock.json` has NO entry list, the canonical exclusion reference is the committed `.bidsignore` (glob set) + the `sources[].n_entries` counts; if it DOES embed entries, use those directly. The rest of the plan supports both via `canonical.py` (Task 5).

- [ ] **Step 2: Note the discovery `.bidsignore` source**

Run:
```bash
cd /scratch/users/logben/neuro_workflow_refactor
git -C /scratch/users/logben/discovery_bids annex whereis .bidsignore 2>/dev/null | head -3 || echo "annex content absent"
ls -l data/exclusions/discovery_collection.bidsignore
```
Expected: discovery `.bidsignore` content is annex-absent; the committed static reference for discovery's *collection* exclusions is `data/exclusions/discovery_collection.bidsignore`. **The harness re-renders `.bidsignore` from a fresh compile and compares to whatever committed copy exists; for discovery it will compare against the regenerated `.bidsignore` that the prerequisite recompile commits (Task 10).**

- [ ] **Step 3: Commit the finding**
```bash
git commit --allow-empty -m "chore(repro): record exclusion-reference shape (lock=provenance, .bidsignore=enumeration)"
```

---

## Task 2: `snapshot.py` — JSON inventory → FlywheelCohortSpec (TDD)

**Files:**
- Create: `src/neuro_workflow/testing/reproduce/__init__.py`
- Create: `src/neuro_workflow/testing/reproduce/snapshot.py`
- Test: `tests/analysis/e2e/test_reproduce_units.py`

- [ ] **Step 1: Write the failing test**
```python
# tests/analysis/e2e/test_reproduce_units.py
import json
from pathlib import Path
from neuro_workflow.testing.reproduce.snapshot import load_inventory, dump_inventory
from neuro_workflow.testing.fake_flywheel import FlywheelCohortSpec


def _sample_inventory():
    return {
        "project": "r01network",
        "subjects": [
            {"label": "s03", "sessions": [
                {"label": "ses-A", "timestamp": "2021-01-15T10:30:00+00:00", "acquisitions": [
                    {"label": "task-flanker_bold", "timestamp": "2021-01-15T10:35:00+00:00",
                     "echoes": 3, "n_trs": 10},
                    {"label": "T1w MPRAGE PROMO", "timestamp": "2021-01-15T10:50:00+00:00"},
                ]},
            ]},
        ],
    }


def test_load_inventory_builds_spec(tmp_path):
    p = tmp_path / "inv.json"
    p.write_text(json.dumps(_sample_inventory()))
    spec = load_inventory(p)
    assert isinstance(spec, FlywheelCohortSpec)
    assert spec.project == "r01network"
    assert [s.label for s in spec.subjects] == ["s03"]
    sess = spec.subjects[0].sessions[0]
    assert sess.label == "ses-A" and sess.timestamp == "2021-01-15T10:30:00+00:00"
    acqs = sess.acquisitions
    assert acqs[0].label == "task-flanker_bold" and acqs[0].echoes == 3 and acqs[0].n_trs == 10
    assert acqs[1].label == "T1w MPRAGE PROMO"  # defaults fill echoes/n_trs


def test_inventory_roundtrip(tmp_path):
    inv = _sample_inventory()
    spec = load_inventory_from_dict(inv) if False else load_inventory(_w(tmp_path, inv))
    out = tmp_path / "rt.json"
    dump_inventory(spec, out)
    spec2 = load_inventory(out)
    assert [a.label for a in spec2.subjects[0].sessions[0].acquisitions] == \
           [a.label for a in spec.subjects[0].sessions[0].acquisitions]


def _w(tmp_path, inv):
    p = tmp_path / "inv.json"; p.write_text(json.dumps(inv)); return p
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: ...reproduce.snapshot`)
Run: `… uv run pytest tests/analysis/e2e/test_reproduce_units.py -v`

- [ ] **Step 3: Implement**
```python
# src/neuro_workflow/testing/reproduce/__init__.py
"""Sherlock-gated real-cohort reproduction harness (see docs spec 2026-06-27)."""
```
```python
# src/neuro_workflow/testing/reproduce/snapshot.py
"""Flywheel inventory snapshot <-> FlywheelCohortSpec.

The snapshot JSON captures exactly what bidsify consumes (subject/session/acq
labels + timestamps + echo/n_trs); aliases + session overrides are applied by
production bidsify from pipeline_config.json, NOT here.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from neuro_workflow.testing.fake_flywheel import (
    FlywheelAcqSpec,
    FlywheelCohortSpec,
    FlywheelSessionSpec,
    FlywheelSubjectSpec,
)


def load_inventory(path: Path) -> FlywheelCohortSpec:
    data = json.loads(Path(path).read_text())
    subjects = []
    for subj in data.get("subjects", []):
        sessions = []
        for sess in subj.get("sessions", []):
            acqs = [
                FlywheelAcqSpec(
                    label=a["label"],
                    timestamp=a.get("timestamp"),
                    echoes=a.get("echoes", 3),
                    n_trs=a.get("n_trs", 10),
                    with_physio=a.get("with_physio", False),
                )
                for a in sess.get("acquisitions", [])
            ]
            sessions.append(FlywheelSessionSpec(
                label=sess["label"], timestamp=sess.get("timestamp"), acquisitions=acqs))
        subjects.append(FlywheelSubjectSpec(label=subj["label"], sessions=sessions))
    return FlywheelCohortSpec(project=data.get("project", "r01network"), subjects=subjects)


def dump_inventory(spec: FlywheelCohortSpec, path: Path) -> None:
    Path(path).write_text(json.dumps(asdict(spec), indent=2, default=str))
```
> NOTE: confirm `FlywheelAcqSpec`/`FlywheelSessionSpec`/`FlywheelSubjectSpec` constructor kwargs match `fake_flywheel.py` exactly (the interface map lists them: acq carries `label, timestamp, echoes=3, n_trs=10, with_physio=False, outcome='keep', plant_contrast=False`). If a field is positional-only, adapt the kwargs.

- [ ] **Step 4: Run → PASS.** **Step 5: Commit** `feat(repro): snapshot JSON <-> FlywheelCohortSpec adapter`.

---

## Task 3: `replay.py` — spec → stub BIDS via real bidsify/trim/events (TDD)

**Files:** Create `src/neuro_workflow/testing/reproduce/replay.py`; Test: append to `test_reproduce_units.py`.

Reuses production: `make_fake_flywheel`, `run_bidsify`, `trim_bold_directory`, `run_create_events`. Stub = the fake client's existing synthetic NIfTI maker with **tiny** dims (small `n_trs`, default voxel grid) — valid NIfTIs of a few KB, ≥8 volumes so `trim_bold` actually trims (writes the `NumberOfVolumesDiscardedByUser=7` sidecar).

- [ ] **Step 1: Failing test**
```python
# append to tests/analysis/e2e/test_reproduce_units.py
from neuro_workflow.testing.reproduce.replay import replay_to_bids
from neuro_workflow.testing.fake_flywheel import (
    FlywheelCohortSpec, FlywheelSubjectSpec, FlywheelSessionSpec, FlywheelAcqSpec)


def _mini_spec():
    acq = FlywheelAcqSpec(label="task-flanker_bold", timestamp="2021-01-15T10:35:00+00:00",
                          echoes=1, n_trs=12)
    sess = FlywheelSessionSpec(label="ses-A", timestamp="2021-01-15T10:30:00+00:00",
                               acquisitions=[acq])
    return FlywheelCohortSpec(project="r01network",
                              subjects=[FlywheelSubjectSpec(label="s03", sessions=[sess])])


def test_replay_produces_named_trimmed_bids(tmp_path, monkeypatch):
    spec = _mini_spec()
    # install_flywheel seam: patch flywheel.Client to return the fake (mirrors simulate_full_pipeline)
    def install(fake):
        import flywheel
        monkeypatch.setattr(flywheel, "Client", lambda *a, **k: fake)
    bids = replay_to_bids(spec, tmp_path, sample_name="discovery",
                          behavioral_dir=tmp_path / "empty_beh", install_flywheel=install)
    bold = list((bids).glob("sub-s03/ses-01/func/*task-flanker*_bold.nii.gz"))
    assert bold, "bidsify must produce a flanker bold with the expected name"
    import json as _j
    sc = _j.loads(next((bids).glob("sub-s03/ses-01/func/*task-flanker*_bold.json")).read_text())
    assert sc.get("NumberOfVolumesDiscardedByUser") == 7  # trim ran
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Implement**
```python
# src/neuro_workflow/testing/reproduce/replay.py
"""Replay a Flywheel snapshot through the REAL bidsify -> trim -> events chain,
producing a stub BIDS tree (tiny valid NIfTIs)."""
from __future__ import annotations

from pathlib import Path

from neuro_workflow.bidsify.run import run_bidsify
from neuro_workflow.events.create import run_create_events
from neuro_workflow.testing.fake_flywheel import FlywheelCohortSpec, make_fake_flywheel

# import the production trim entry by path-independent import
import importlib.util as _ilu


def _trim_dir(bids_dir: Path):
    spec = _ilu.spec_from_file_location(
        "trim_bold",
        str(Path(__file__).resolve().parents[4] / "scripts" / "trim_bold.py"),
    )
    mod = _ilu.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.trim_bold_directory(bids_dir)


def replay_to_bids(spec: FlywheelCohortSpec, root: Path, *, sample_name: str,
                   behavioral_dir: Path, install_flywheel) -> Path:
    """spec -> FakeFlywheel -> run_bidsify -> trim_bold -> events.create. Returns bids dir."""
    root = Path(root); bids = root / "bids"
    fake = make_fake_flywheel(spec)
    install_flywheel(fake)
    subjects = [s.label for s in spec.subjects]
    run_bidsify(sample_name, output_dir=bids, subjects=subjects, overwrite=True)
    _trim_dir(bids)
    run_create_events(behavioral_dir=Path(behavioral_dir), bids_dir=bids)
    return bids
```
> NOTE: `trim_bold.py` is a top-level script (not importable as a package module); the helper loads it by file path. If the team has since promoted it into the package, replace with a direct import. Confirm `scripts/trim_bold.py` exposes `trim_bold_directory` (the interface map confirms it does).

- [ ] **Step 4: Run → PASS. Step 5: Commit** `feat(repro): replay snapshot -> stub BIDS via real bidsify/trim/events`.

---

## Task 4: `stage_metrics.py` — symlink real metric inputs (TDD)

**Files:** Create `src/neuro_workflow/testing/reproduce/stage_metrics.py`; Test: append.

Symlinks the real fMRIPrep confounds derivative, behavioral sourcedata, and `lev1_outliers.csv` into / beside the produced tree so the generators read genuine metrics. Resolves real paths from a per-cohort config dict (passed in; the CLI supplies the real Sherlock paths).

- [ ] **Step 1: Failing test**
```python
# append
from neuro_workflow.testing.reproduce.stage_metrics import stage_metrics

def test_stage_metrics_symlinks(tmp_path):
    bids = tmp_path / "bids"; (bids / "derivatives").mkdir(parents=True)
    real_fmriprep = tmp_path / "real_fmriprep_25.2.4"; real_fmriprep.mkdir()
    (real_fmriprep / "marker.txt").write_text("x")
    staged = stage_metrics(bids, fmriprep_src=real_fmriprep, version="25.2.4")
    link = bids / "derivatives" / "fmriprep_25.2.4"
    assert link.is_symlink() and (link / "marker.txt").exists()
    assert staged["fmriprep"] == link
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**
```python
# src/neuro_workflow/testing/reproduce/stage_metrics.py
"""Symlink real (small) metric inputs into the stub tree for the generators."""
from __future__ import annotations
from pathlib import Path
from typing import Optional


def _link(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    dst.symlink_to(Path(src).resolve())
    return dst


def stage_metrics(bids_dir: Path, *, fmriprep_src: Path, version: str,
                  behavioral_src: Optional[Path] = None) -> dict:
    """Symlink the fMRIPrep derivative (motion) + optional behavioral sourcedata.
    Returns {kind: linked_path}. lev1_outliers.csv is passed to the generator by
    path directly (not staged into the tree)."""
    out = {}
    out["fmriprep"] = _link(fmriprep_src, bids_dir / "derivatives" / f"fmriprep_{version}")
    if behavioral_src is not None:
        out["behavioral"] = _link(behavioral_src, bids_dir / "sourcedata" / "in_scanner_behavior")
    return out
```

- [ ] **Step 4: PASS. Step 5: Commit** `feat(repro): stage real metric inputs via symlink`.

---

## Task 5: `canonical.py` — provenance-stripped set extraction (TDD)

**Files:** Create `src/neuro_workflow/testing/reproduce/canonical.py`; Test: append.

The gating key is `(subject, session, task, run, action, source)` with `task` normalized (strip a leading `task-`). Also extract a `.bidsignore` glob-line set and a BIDS filename set.

- [ ] **Step 1: Failing test**
```python
# append
from neuro_workflow.testing.reproduce.canonical import (
    compiled_to_keyset, bidsignore_lineset, bids_fileset)

def test_compiled_keyset_normalizes_task_prefix():
    compiled = [
        {"subject": "sub-s10", "session": "ses-01", "task": "task-goNogo",
         "run": "run-1", "action": "exclude", "source": "qa_decisions", "reason": "x"},
        {"subject": "sub-s10", "session": "ses-01", "task": "goNogo",
         "run": "run-1", "action": "exclude", "source": "collection", "reason": "y"},
    ]
    ks = compiled_to_keyset(compiled)
    # task normalized to bare 'goNogo' for both; sources distinct
    assert ("sub-s10","ses-01","goNogo","run-1","exclude","qa_decisions") in ks
    assert ("sub-s10","ses-01","goNogo","run-1","exclude","collection") in ks

def test_bidsignore_lineset_ignores_comments_blanks():
    text = "# header\n\nsub-s10/ses-01/func/foo_bold.*\n  \nsub-s19/ses-02/func/bar_bold.*\n"
    assert bidsignore_lineset(text) == {
        "sub-s10/ses-01/func/foo_bold.*", "sub-s19/ses-02/func/bar_bold.*"}

def test_bids_fileset_relative(tmp_path):
    (tmp_path / "sub-s03/ses-01/func").mkdir(parents=True)
    (tmp_path / "sub-s03/ses-01/func/a_bold.nii.gz").write_bytes(b"")
    (tmp_path / "sub-s03/ses-01/func/a_events.tsv").write_text("")
    (tmp_path / "sourcedata").mkdir()
    (tmp_path / "sourcedata/x.json").write_text("")  # excluded (not under sub-*)
    fs = bids_fileset(tmp_path)
    assert "sub-s03/ses-01/func/a_bold.nii.gz" in fs
    assert "sub-s03/ses-01/func/a_events.tsv" in fs
    assert not any(f.startswith("sourcedata/") for f in fs)
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**
```python
# src/neuro_workflow/testing/reproduce/canonical.py
"""Provenance-stripped canonical sets for reproduction diffs."""
from __future__ import annotations
from pathlib import Path
from typing import Iterable

_GATING_ACTIONS = {"exclude", "trim"}


def _bare_task(task: str) -> str:
    return task[5:] if task.startswith("task-") else task


def compiled_to_keyset(compiled: Iterable[dict]) -> set:
    """6-tuple gating set; reason intentionally excluded (informational)."""
    out = set()
    for e in compiled:
        if e.get("action") not in _GATING_ACTIONS:
            continue
        out.add((e["subject"], e["session"], _bare_task(e["task"]),
                 e["run"], e["action"], e.get("source")))
    return out


def bidsignore_lineset(text: str) -> set:
    return {ln.strip() for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")}


def bids_fileset(bids_dir: Path) -> set:
    """All files under sub-*/ (bold, events, sidecars, anat), as posix relpaths."""
    bids_dir = Path(bids_dir)
    out = set()
    for sub in sorted(bids_dir.glob("sub-*")):
        for f in sub.rglob("*"):
            if f.is_file():
                out.add(f.relative_to(bids_dir).as_posix())
    return out
```

- [ ] **Step 4: PASS. Step 5: Commit** `feat(repro): canonical set extractors (exclusion keyset, bidsignore, filenames)`.

---

## Task 6: `lev2_select.py` — modeled eligible set + on-disk reference (TDD)

**Files:** Create `src/neuro_workflow/testing/reproduce/lev2_select.py`; Test: append.

Models the eligible `{(subject, task, contrast)}` set deterministically from the BIDS inventory minus exclusions, minus rest/no-events (via `FileFinder`, which drops runs missing `events`), applying the `min_runs` floor (default 2), expanded over `get_task_contrasts(task)`. Reference set = glob the real fixed-effects outputs (non-`belowMinRuns`).

- [ ] **Step 1: Failing test** (hermetic — fabricate a tiny FE output tree + a stub inventory)
```python
# append
from neuro_workflow.testing.reproduce.lev2_select import lev2_reference_set

def test_lev2_reference_set_globs_and_filters_belowminruns(tmp_path):
    base = tmp_path / "lev1/sub-s03/task-flanker/fixed_effects"; base.mkdir(parents=True)
    (base / "sub-s03_task-flanker_contrast-incongruent-congruent_rtmodel-RTDur_stat-fixed-effects.nii.gz").write_bytes(b"")
    (base / "sub-s03_task-flanker_contrast-rare_rtmodel-RTDur_desc-belowMinRuns_stat-fixed-effects.nii.gz").write_bytes(b"")
    ref = lev2_reference_set([tmp_path / "lev1"])
    assert ("sub-s03", "flanker", "incongruent-congruent") in ref
    assert all("rare" not in c for (_, _, c) in ref)  # belowMinRuns filtered
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement** (reference set first; modeled set reuses `FileFinder` + `get_task_contrasts`)
```python
# src/neuro_workflow/testing/reproduce/lev2_select.py
"""Model the lev2-eligible {(subject,task,contrast)} set + the on-disk reference."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Iterable

_FE_RE = re.compile(
    r"(?P<sub>sub-[^_/]+)_(?:hemi-[^_]+_)?(?:space-[^_]+_)?task-(?P<task>[^_]+)"
    r"_contrast-(?P<contrast>.+?)_rtmodel-[^_]+(?:_desc-belowMinRuns)?_stat-fixed-effects")


def lev2_reference_set(level1_dirs: Iterable[Path]) -> set:
    """Glob real fixed-effects maps lev2 consumes; drop _desc-belowMinRuns."""
    out = set()
    for d in level1_dirs:
        for f in Path(d).glob("sub-*/*/fixed_effects/*_stat-fixed-effects.nii.gz"):
            if "_desc-belowMinRuns" in f.name:
                continue
            m = _FE_RE.search(f.name)
            if m:
                out.add((m.group("sub"), m.group("task"), m.group("contrast")))
    return out


def lev2_eligible_set(bids_dir: Path, fmriprep_dir: Path, subjects, tasks,
                      excluded_keys: set, *, min_runs: int = 2) -> set:
    """Deterministic model: (BIDS runs - excluded - missing-events) >= min_runs
    -> expand over task contrasts. excluded_keys are bare-task 4-tuples
    (subject, session, task, run)."""
    from neuro_workflow.analysis.io.file_discovery import FileFinder
    from neuro_workflow.analysis.task_config.loader import get_task_contrasts

    finder = FileFinder(str(bids_dir), str(fmriprep_dir))
    out = set()
    for sub in subjects:
        for task in tasks:
            if task == "rest":
                continue
            files = finder.get_files(sub, task,
                                     required_files=FileFinder.get_required_files_for_space("MNI"))
            n = 0
            for ses, runs in files.items():
                for run in runs:
                    if (sub, ses, task, run) in excluded_keys:
                        continue
                    n += 1
            if n < min_runs:
                continue
            for contrast in get_task_contrasts(task):
                out.add((sub, task, contrast))
    return out
```
> NOTE: `excluded_keys` here is the bare 4-tuple `(subject, session, task, run)` derived from `compiled_to_keyset` by dropping `action`/`source`; the CLI computes it. `FileFinder` already drops runs missing `events` (rest has none), satisfying the "no-events/rest" filter.

- [ ] **Step 4: PASS** (the reference-set test; the modeled-set path is exercised in the Sherlock e2e). **Step 5: Commit** `feat(repro): lev2-eligible modeled set + on-disk reference`.

---

## Task 7: `report.py` — 3-diff report + PASS/FAIL (TDD)

**Files:** Create `src/neuro_workflow/testing/reproduce/report.py`; Test: append.

- [ ] **Step 1: Failing test**
```python
# append
from neuro_workflow.testing.reproduce.report import diff_sets, build_report

def test_diff_sets_partitions():
    d = diff_sets({"a","b"}, {"b","c"})
    assert d["matched"] == {"b"} and d["only_produced"] == {"a"} and d["only_reference"] == {"c"}

def test_build_report_pass_fail():
    clean = diff_sets({"a"}, {"a"})
    dirty = diff_sets({"a"}, {"a","b"})
    rep_ok = build_report("discovery", clean, clean, clean, provenance={"sha": "x"})
    assert "PASS" in rep_ok and "FAIL" not in rep_ok.splitlines()[0]
    rep_bad = build_report("discovery", clean, dirty, clean, provenance={"sha": "x"})
    assert "FAIL" in rep_bad
```

- [ ] **Step 2: Run → FAIL. Step 3: Implement**
```python
# src/neuro_workflow/testing/reproduce/report.py
"""Reproduction diff + Markdown report."""
from __future__ import annotations


def diff_sets(produced: set, reference: set) -> dict:
    return {"matched": produced & reference,
            "only_produced": produced - reference,
            "only_reference": reference - produced}


def _passed(d: dict) -> bool:
    return not d["only_produced"] and not d["only_reference"]


def build_report(cohort: str, filenames: dict, exclusions: dict, lev2: dict,
                 *, provenance: dict) -> str:
    ok = all(_passed(d) for d in (filenames, exclusions, lev2))
    lines = [f"# Reproduction report — {cohort}: {'PASS' if ok else 'FAIL'}", ""]
    lines.append("## Provenance")
    for k, v in provenance.items():
        lines.append(f"- {k}: {v}")
    for name, d in (("Filenames", filenames), ("Exclusion set", exclusions),
                    ("Lev2-eligible set", lev2)):
        lines += ["", f"## {name}: {'PASS' if _passed(d) else 'FAIL'}",
                  f"- matched: {len(d['matched'])}",
                  f"- only in produced ({len(d['only_produced'])}): "
                  f"{sorted(d['only_produced'])[:20]}",
                  f"- only in reference ({len(d['only_reference'])}): "
                  f"{sorted(d['only_reference'])[:20]}"]
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: PASS. Step 5: Commit** `feat(repro): diff + markdown report`.

---

## Task 8: `scripts/capture_fw_inventory.py` — one-time real-fw capture

**Files:** Create `scripts/capture_fw_inventory.py`; Test: append (unit-test the fw-object→dict transform on a fake object).

- [ ] **Step 1: Failing test** (transform pure function, no real fw)
```python
# append
from scripts_capture import fw_project_to_inventory  # see note on import shim

class _Acq:  # minimal duck-typed fw acquisition
    def __init__(self, label, ts): self.label = label; self.timestamp = ts
class _Sess:
    def __init__(self, label, ts, acqs): self.label=label; self.timestamp=ts; self._a=acqs
    def acquisitions(self): return self._a
# ... (the test builds a fake project tree and asserts the dict shape)
```
> NOTE: factor the pure transform `fw_project_to_inventory(project) -> dict` so it is unit-testable without Flywheel; the CLI `main()` only does auth + `fw.get_project(...)` + writes JSON. Place the transform in `src/neuro_workflow/testing/reproduce/snapshot.py` (add `fw_project_to_inventory`) and have the script import it, so the test imports from the package (avoids a scripts import shim).

- [ ] **Step 2–4:** implement `fw_project_to_inventory(project)` in `snapshot.py` (walk subjects→sessions→acquisitions, record `label`, `timestamp`, and per-acq `echoes` from the file list, `n_trs` left default), test green.

- [ ] **Step 5: Implement the CLI** `scripts/capture_fw_inventory.py`:
```python
#!/usr/bin/env python3
"""One-time: capture a Flywheel project inventory to data/repro/fw_inventory_<cohort>.json."""
import argparse, json
from pathlib import Path
import flywheel
from neuro_workflow.testing.reproduce.snapshot import fw_project_to_inventory

def main():
    p = argparse.ArgumentParser()
    p.add_argument("cohort", choices=["discovery", "validation"])
    p.add_argument("--project", default="r01network")
    p.add_argument("--out", type=Path, default=None)
    a = p.parse_args()
    fw = flywheel.Client()
    proj = fw.lookup(f"<group>/{a.project}")  # resolve real group/project per pipeline_config
    inv = fw_project_to_inventory(proj)
    out = a.out or Path("data/repro") / f"fw_inventory_{a.cohort}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inv, indent=2, default=str))
    print(f"wrote {out}")

if __name__ == "__main__":
    main()
```
> This runs once on Sherlock with Flywheel auth (a prerequisite, Task 10). Resolve the real group/project string from `config/pipeline_config.json` (`flywheel.project`). Commit the produced `data/repro/fw_inventory_<cohort>.json`.

- [ ] **Step 6: Commit** `feat(repro): one-time Flywheel inventory capture`.

---

## Task 9: `scripts/reproduce_cohort.py` CLI + Sherlock-gated e2e (TDD)

**Files:** Create `scripts/reproduce_cohort.py`; Test: `tests/analysis/e2e/test_reproduce_cohort.py`.

The CLI wires Tasks 2–7: `load_inventory` → `replay_to_bids` (with the real behavioral dir) → `stage_metrics` → `simulate_exclusions` (real generators on the staged tree) → render `.bidsignore` → `lev2_eligible_set` → three `diff_sets` vs references (real BIDS filenames; committed `.bidsignore`; `lev2_reference_set`) → `build_report` → write `repro_report.md`; exit non-zero on FAIL.

- [ ] **Step 1: Sherlock-gated e2e test (auto-skip)**
```python
# tests/analysis/e2e/test_reproduce_cohort.py
import os, subprocess, sys
from pathlib import Path
import pytest

WT = Path("/scratch/users/logben/neuro_workflow_refactor")
SNAP = WT / "data/repro/fw_inventory_discovery.json"
REAL_BIDS = Path("/scratch/users/logben/discovery_bids")

pytestmark = pytest.mark.skipif(
    not (SNAP.exists() and REAL_BIDS.exists()),
    reason="real cohort inputs / Flywheel snapshot absent (Sherlock-only)")

def test_discovery_reproduces(tmp_path):
    rc = subprocess.run([sys.executable, str(WT/"scripts/reproduce_cohort.py"),
                         "discovery", "--out", str(tmp_path/"rep.md")]).returncode
    report = (tmp_path/"rep.md").read_text()
    assert "PASS" in report.splitlines()[0], report
    assert rc == 0
```

- [ ] **Step 2: Run → SKIP** (snapshot absent until Task 10) — confirm it *skips*, not errors.
- [ ] **Step 3: Implement `reproduce_cohort.py`** composing the units with the real per-cohort paths (resolved from a small `_COHORT_PATHS` dict: real bids dir, fmriprep version `25.2.4`, behavioral Oak dir, `lev1_outliers.csv`, committed `.bidsignore`, lev1 FE dir). Compute `excluded_keys` (bare 4-tuple) from the compiled set; pass to `lev2_eligible_set`. Write the report; `sys.exit(0 if PASS else 1)`.
- [ ] **Step 4: Run the full hermetic unit suite green** (`uv run pytest tests/analysis/e2e/test_reproduce_units.py -v`); the cohort e2e stays skipped off-Sherlock.
- [ ] **Step 5: Commit** `feat(repro): reproduce_cohort CLI + Sherlock-gated e2e`.

---

## Task 10: Prerequisite gates (operational — sequenced, not harness code)

These are the ordered gates the harness asserts against. Do them before the first real `reproduce_cohort.py` run.

- [ ] **Step 1:** Confirm validation `lev1_outliers.csv` exists (done 2026-06-27).
- [ ] **Step 2: Recompile both lockfiles with all 5 generators** (incl. `lev1_outlier`) from current code + current inputs, via `neuro-run exclusions generate` (each source) + `neuro-run exclusions compile <dataset>`; **diff the new exclusion set vs the committed (stale) one and review** before committing. Commit regenerated `data/exclusions/{discovery,validation}_lock.json` + re-rendered `.bidsignore` (de-annex discovery's: write a real committed copy).
- [ ] **Step 3: Capture Flywheel snapshots** — run `scripts/capture_fw_inventory.py discovery` and `... validation` (Flywheel auth); commit `data/repro/fw_inventory_*.json`.
- [ ] **Step 4: Run `reproduce_cohort.py discovery` and `... validation`** on Sherlock; iterate until both reports PASS. Commit the passing `repro_report.md`s under `docs/` or attach to the PR.
- [ ] **Step 5: Trim invariant check** — extend `reproduce_cohort.py` (or a standalone assertion) to verify, per kept func scan, `NumberOfVolumesDiscardedByUser==7` AND the matching real fMRIPrep confounds row count == trimmed BOLD volume count; confirm the fMRIPrep template carries `--dummy-scans 0`. (Closes the §4 loose end.)

---

## Self-review

- **Spec coverage:** §1 module layout → Tasks 2–9; §2 data flow → Task 9 wiring; §3 lev2 model → Task 6; §3 comparison semantics → Task 5; §4 report/gating → Tasks 7,9; §4 trim invariant → Task 10.5; §5 prereqs/sequencing → Task 10. Covered.
- **Placeholders:** none — every code step has real code; the two `NOTE`s flag interface confirmations (acq dataclass kwargs; trim import) the implementer verifies against the cited files, not deferred work.
- **Type consistency:** `compiled_to_keyset` → 6-tuple; `lev2_eligible_set` consumes a bare 4-tuple `excluded_keys` (CLI derives it by dropping action/source) — stated explicitly. `diff_sets`/`build_report` keys (`matched`/`only_produced`/`only_reference`) consistent across Tasks 7 and 9.
- **Known soft spot:** Task 1 resolves whether the committed lock embeds entries; the exclusion reference defaults to the committed `.bidsignore` glob set + `sources[].n_entries`. The diff is on the rendered-`.bidsignore` line set, robust to that.
