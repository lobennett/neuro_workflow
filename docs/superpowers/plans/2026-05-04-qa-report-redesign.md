# QA Report Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the existing 169-page-per-subject PDF QA report with a static HTML cohort dashboard that surfaces flagged scans, embeds FreeSurfer Euler/holes metrics, integrates bold-reliability-movies output, and reads user decisions from a sidecar TSV.

**Architecture:** Pure-function metric extractors (`metrics/motion.py`, `metrics/freesurfer.py`, `metrics/outputs.py`) feed an orchestrator (`report.py`) that renders Jinja2 templates into static HTML. Bold-reliability-movies invoked via Python API. DataTables vendored for filterable client-side tables. Decisions read from version-controlled TSV.

**Tech Stack:** Python 3.13, Jinja2 (already in uv.lock), pandas, nibabel, pytest. DataTables vendored (~50 KB). bold-reliability-movies as PyPI dep.

**Spec:** `docs/superpowers/specs/2026-05-04-qa-report-redesign-design.md`

---

## File Structure

**Files to create:**
```
src/neuro_workflow/qa/
├── metrics/
│   ├── __init__.py
│   ├── motion.py             # MotionMetrics dataclass + compute_motion()
│   ├── freesurfer.py         # FreeSurferMetrics + compute_freesurfer()
│   └── outputs.py            # OutputCheckResult + check_expected_outputs()
├── decisions.py              # Decision dataclass + load_decisions()
├── cohort.py                 # cohort_euler_outliers()
├── reliability_movies.py     # render_reliability_movies()
└── templates/
    ├── __init__.py
    ├── cohort.html.j2
    ├── subject.html.j2
    └── static/
        ├── datatables.min.js
        ├── datatables.min.css
        └── style.css

tests/qa/
├── test_motion.py
├── test_freesurfer.py
├── test_outputs.py
├── test_cohort.py
├── test_decisions.py
├── test_reliability_movies.py
├── test_templates.py
├── test_report_orchestrator.py
└── fixtures/
    └── tiny_fmriprep/        # minimal fmriprep dir for integration tests
```

**Files to modify:**
- `src/neuro_workflow/qa/report.py` — full rewrite (orchestrator only; delete old PDF code)
- `scripts/qa_report.py` — update CLI (add `--no-reliability-movies`, `--decisions`, `--euler-n-sigma`)
- `pyproject.toml` — add `jinja2>=3.0` and `bold-reliability-movies>=0.1` to `qa` extras

---

## Task 1: Add deps + create metric package skeleton

**Files:**
- Modify: `pyproject.toml`
- Create: `src/neuro_workflow/qa/metrics/__init__.py` (empty)

- [ ] **Step 1.1: Add jinja2 + bold-reliability-movies to qa extras**

Edit `pyproject.toml`. Find the `qa` block under `[project.optional-dependencies]`:

```toml
qa = [
    "nilearn>=0.12",
    "nibabel>=5.0",
    "matplotlib>=3.0",
    "pandas>=2.0",
    "numpy>=1.24",
    "img2pdf>=0.5",
    "seaborn>=0.13",
    "cairosvg>=2.7",
]
```

Replace with:

```toml
qa = [
    "nilearn>=0.12",
    "nibabel>=5.0",
    "matplotlib>=3.0",
    "pandas>=2.0",
    "numpy>=1.24",
    "img2pdf>=0.5",
    "seaborn>=0.13",
    "cairosvg>=2.7",
    "jinja2>=3.0",
    "bold-reliability-movies>=0.1",
]
```

- [ ] **Step 1.2: Create empty metrics package**

```bash
mkdir -p /home/users/logben/neuro_workflow/src/neuro_workflow/qa/metrics
touch /home/users/logben/neuro_workflow/src/neuro_workflow/qa/metrics/__init__.py
```

- [ ] **Step 1.3: Verify imports still work (no breakage)**

```bash
cd /home/users/logben/neuro_workflow
uv run python -c "import neuro_workflow.qa; print('OK')"
```
Expected: prints `OK`.

- [ ] **Step 1.4: Commit**

```bash
git add pyproject.toml src/neuro_workflow/qa/metrics/__init__.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): add jinja2 + brm to qa extras; create metrics package

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Motion metrics module (TDD)

**Files:**
- Create: `src/neuro_workflow/qa/metrics/motion.py`
- Create: `tests/qa/test_motion.py`

- [ ] **Step 2.1: Create `tests/qa/__init__.py`**

```bash
mkdir -p /home/users/logben/neuro_workflow/tests/qa
touch /home/users/logben/neuro_workflow/tests/qa/__init__.py
```

- [ ] **Step 2.2: Write failing tests**

Create `tests/qa/test_motion.py`:

```python
"""Tests for src/neuro_workflow/qa/metrics/motion.py."""
import pandas as pd
import pytest

from neuro_workflow.qa.metrics.motion import MotionMetrics, compute_motion


def _make_confounds(tmp_path, n_vols=10, fd=None, dvars=None, n_outliers=0):
    """Helper: write a confounds TSV with given values."""
    df = pd.DataFrame({
        "framewise_displacement": [None] + (fd or [0.1] * (n_vols - 1)),
        "std_dvars": [None] + (dvars or [1.0] * (n_vols - 1)),
    })
    for i in range(n_outliers):
        df[f"motion_outlier{i:02d}"] = 0
    path = tmp_path / "confounds.tsv"
    df.to_csv(path, sep="\t", index=False, na_rep="n/a")
    return path


def test_compute_motion_returns_dataclass(tmp_path):
    path = _make_confounds(tmp_path, n_vols=5, fd=[0.1, 0.2, 0.3, 0.4],
                           dvars=[1.0, 1.1, 1.2, 1.3])
    m = compute_motion(path)
    assert isinstance(m, MotionMetrics)
    assert m.n_vols == 5
    assert m.fd_mean == pytest.approx(0.25)
    assert m.dvars_mean == pytest.approx(1.15)


def test_compute_motion_counts_motion_outliers(tmp_path):
    path = _make_confounds(tmp_path, n_vols=10, n_outliers=3)
    m = compute_motion(path)
    assert m.n_motion_outliers == 3


def test_compute_motion_proportion_over_thresholds(tmp_path):
    # 5 vols, FD = [0.1, 0.6, 0.7, 0.05] (after dropping leading n/a)
    # → 2/4 = 50% over 0.5
    path = _make_confounds(tmp_path, n_vols=5,
                           fd=[0.1, 0.6, 0.7, 0.05],
                           dvars=[1.0, 1.6, 1.7, 1.0])
    m = compute_motion(path)
    assert m.fd_prop_over_05 == pytest.approx(0.5)
    assert m.dvars_prop_over_15 == pytest.approx(0.5)


def test_compute_motion_handles_all_nan(tmp_path):
    df = pd.DataFrame({
        "framewise_displacement": [None] * 5,
        "std_dvars": [None] * 5,
    })
    path = tmp_path / "confounds.tsv"
    df.to_csv(path, sep="\t", index=False, na_rep="n/a")
    m = compute_motion(path)
    assert m.n_vols == 5
    # When all values are NaN, mean is NaN; we report 0.0 instead so the table
    # column stays numeric.
    assert m.fd_mean == 0.0 or (m.fd_mean != m.fd_mean)  # 0.0 or NaN both acceptable


def test_compute_motion_missing_columns(tmp_path):
    # Confounds without standard motion columns → graceful zeros
    df = pd.DataFrame({"global_signal": [1.0, 2.0, 3.0]})
    path = tmp_path / "confounds.tsv"
    df.to_csv(path, sep="\t", index=False)
    m = compute_motion(path)
    assert m.n_vols == 3
    assert m.fd_mean == 0.0
    assert m.dvars_mean == 0.0
```

- [ ] **Step 2.3: Run tests, verify failure**

```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/qa/test_motion.py -v
```
Expected: ImportError on `neuro_workflow.qa.metrics.motion`.

- [ ] **Step 2.4: Implement `motion.py`**

Create `src/neuro_workflow/qa/metrics/motion.py`:

```python
"""Motion metrics extracted from fmriprep confounds TSV files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class MotionMetrics:
    n_vols: int
    fd_mean: float
    fd_max: float
    fd_prop_over_05: float
    dvars_mean: float
    dvars_max: float
    dvars_prop_over_15: float
    n_motion_outliers: int
    fd_series: pd.Series
    dvars_series: pd.Series


def compute_motion(confounds_tsv: Path) -> MotionMetrics:
    """Compute per-scan motion metrics from a fmriprep confounds TSV.

    Returns zeros (not NaN) for any metric whose source column is missing or
    all-NaN, so downstream tables stay numeric.
    """
    df = pd.read_csv(confounds_tsv, sep="\t")

    fd = df["framewise_displacement"].dropna() if "framewise_displacement" in df.columns else pd.Series(dtype=float)
    dvars = df["std_dvars"].dropna() if "std_dvars" in df.columns else pd.Series(dtype=float)

    n_motion_outliers = sum(1 for c in df.columns if c.startswith("motion_outlier"))

    return MotionMetrics(
        n_vols=len(df),
        fd_mean=float(fd.mean()) if len(fd) else 0.0,
        fd_max=float(fd.max()) if len(fd) else 0.0,
        fd_prop_over_05=float((fd > 0.5).mean()) if len(fd) else 0.0,
        dvars_mean=float(dvars.mean()) if len(dvars) else 0.0,
        dvars_max=float(dvars.max()) if len(dvars) else 0.0,
        dvars_prop_over_15=float((dvars > 1.5).mean()) if len(dvars) else 0.0,
        n_motion_outliers=n_motion_outliers,
        fd_series=fd,
        dvars_series=dvars,
    )
```

- [ ] **Step 2.5: Run tests, verify pass**

```bash
uv run pytest tests/qa/test_motion.py -v
```
Expected: 5 passing.

- [ ] **Step 2.6: Commit**

```bash
git add src/neuro_workflow/qa/metrics/motion.py tests/qa/__init__.py tests/qa/test_motion.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): add motion metrics module

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: FreeSurfer metrics module (TDD)

**Files:**
- Create: `src/neuro_workflow/qa/metrics/freesurfer.py`
- Create: `tests/qa/test_freesurfer.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/qa/test_freesurfer.py`:

```python
"""Tests for src/neuro_workflow/qa/metrics/freesurfer.py."""
import pytest

from neuro_workflow.qa.metrics.freesurfer import (
    FreeSurferMetrics,
    compute_freesurfer,
    parse_euler_from_log,
    parse_recon_all_status,
    parse_aseg_stats,
)


def _make_fs_dir(tmp_path, status="OK", euler_lh=-100, euler_rh=-80,
                 elapsed_hours=10.0, brain_vol=1100000.0):
    """Build a minimal FreeSurfer subject directory."""
    fs = tmp_path / "sub-X_ses-01"
    (fs / "scripts").mkdir(parents=True)
    (fs / "stats").mkdir(parents=True)
    (fs / "mri").mkdir(parents=True)
    (fs / "surf").mkdir(parents=True)

    # recon-all-status.log
    if status == "OK":
        (fs / "scripts" / "recon-all-status.log").write_text(
            "Started\n"
            f"recon-all -s sub-X_ses-01 finished without error at Wed Apr 29 19:05:44 PDT 2026\n"
        )
    elif status == "FAILED":
        (fs / "scripts" / "recon-all-status.log").write_text(
            f"recon-all -s sub-X_ses-01 exited with ERRORS at Wed Apr 29 12:00:00 PDT 2026\n"
        )
    elif status == "INCOMPLETE":
        (fs / "scripts" / "recon-all-status.log").write_text("Started\n#@# Tessellate\n")

    # recon-all.log with Euler info + runtime
    (fs / "scripts" / "recon-all.log").write_text(
        f"#@# Topology lh\n"
        f"orig.nofix lheno = {euler_lh}, rheno = {euler_rh}\n"
        f"#@# DONE\n"
        f"#@#%# recon-all-run-time-hours {elapsed_hours}\n"
    )

    # aseg.stats
    (fs / "stats" / "aseg.stats").write_text(
        "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, "
        f"{brain_vol}, mm^3\n"
        "# Measure TotalGray, TotalGrayVol, Total gray matter volume, 600000.0, mm^3\n"
        "# Measure CerebralWhiteMatter, CerebralWhiteMatterVol, Cerebral White Matter Volume, 500000.0, mm^3\n"
        "# Measure CSF, CSFVol, CSF Volume, 1500.0, mm^3\n"
        "# Measure EstimatedTotalIntraCranialVol, eTIV, Estimated Total Intracranial Volume, 1500000.0, mm^3\n"
    )
    return fs


def test_parse_euler_from_log(tmp_path):
    log = tmp_path / "recon-all.log"
    log.write_text(
        "blah\n"
        "orig.nofix lheno = -366, rheno = -278\n"
        "more blah\n"
    )
    result = parse_euler_from_log(log)
    assert result == (-366, -278)


def test_parse_euler_from_log_missing_returns_none(tmp_path):
    log = tmp_path / "recon-all.log"
    log.write_text("no euler info here\n")
    assert parse_euler_from_log(log) is None


def test_parse_recon_all_status_ok(tmp_path):
    f = tmp_path / "recon-all-status.log"
    f.write_text("recon-all -s X finished without error at ...\n")
    assert parse_recon_all_status(f) == "OK"


def test_parse_recon_all_status_failed(tmp_path):
    f = tmp_path / "recon-all-status.log"
    f.write_text("recon-all -s X exited with ERRORS at ...\n")
    assert parse_recon_all_status(f) == "FAILED"


def test_parse_recon_all_status_incomplete(tmp_path):
    f = tmp_path / "recon-all-status.log"
    f.write_text("Started\n#@# Tessellate\n")
    assert parse_recon_all_status(f) == "INCOMPLETE"


def test_parse_aseg_stats(tmp_path):
    f = tmp_path / "aseg.stats"
    f.write_text(
        "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 1100000.5, mm^3\n"
        "# Measure TotalGray, TotalGrayVol, Total gray matter volume, 600000.0, mm^3\n"
        "# Measure CerebralWhiteMatter, CerebralWhiteMatterVol, Cerebral White Matter Volume, 500000.0, mm^3\n"
        "# Measure CSF, CSFVol, CSF Volume, 1500.0, mm^3\n"
        "# Measure EstimatedTotalIntraCranialVol, eTIV, Estimated Total Intracranial Volume, 1500000.0, mm^3\n"
    )
    vols = parse_aseg_stats(f)
    assert vols["brain_vol"] == pytest.approx(1100000.5)
    assert vols["gm_vol"] == pytest.approx(600000.0)
    assert vols["wm_vol"] == pytest.approx(500000.0)
    assert vols["csf_vol"] == pytest.approx(1500.0)
    assert vols["etiv"] == pytest.approx(1500000.0)


def test_compute_freesurfer_full(tmp_path):
    fs = _make_fs_dir(tmp_path)
    m = compute_freesurfer(fs)
    assert isinstance(m, FreeSurferMetrics)
    assert m.status == "OK"
    assert m.elapsed_hours == pytest.approx(10.0)
    assert m.euler_lh == -100
    assert m.euler_rh == -80
    assert m.euler_mean == pytest.approx(-90.0)
    assert m.holes_lh == 51   # (2 - (-100)) / 2 = 51
    assert m.holes_rh == 41
    assert m.holes_mean == pytest.approx(46.0)
    assert m.brain_vol == pytest.approx(1100000.0)


def test_compute_freesurfer_missing_dir(tmp_path):
    m = compute_freesurfer(tmp_path / "nonexistent")
    assert m.status == "MISSING"
    assert m.euler_mean is None
    assert m.brain_vol is None


def test_compute_freesurfer_failed_recon(tmp_path):
    fs = _make_fs_dir(tmp_path, status="FAILED")
    m = compute_freesurfer(fs)
    assert m.status == "FAILED"


def test_compute_freesurfer_incomplete_recon(tmp_path):
    fs = _make_fs_dir(tmp_path, status="INCOMPLETE")
    m = compute_freesurfer(fs)
    assert m.status == "INCOMPLETE"
```

- [ ] **Step 3.2: Run tests, verify failure**

```bash
uv run pytest tests/qa/test_freesurfer.py -v
```
Expected: ImportError.

- [ ] **Step 3.3: Implement `freesurfer.py`**

Create `src/neuro_workflow/qa/metrics/freesurfer.py`:

```python
"""FreeSurfer surface QC metrics extracted from recon-all output."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


_EULER_RE = re.compile(r"orig\.nofix\s+lheno\s*=\s*(-?\d+)\s*,\s*rheno\s*=\s*(-?\d+)")
_ELAPSED_RE = re.compile(r"recon-all-run-time-hours\s+([\d.]+)")
_ASEG_RE = re.compile(r"#\s*Measure\s+(\w+),.*?,\s*([\d.]+),\s*mm")


Status = Literal["OK", "FAILED", "INCOMPLETE", "MISSING"]


@dataclass
class FreeSurferMetrics:
    status: Status
    elapsed_hours: float | None
    euler_lh: int | None
    euler_rh: int | None
    euler_mean: float | None
    holes_lh: int | None
    holes_rh: int | None
    holes_mean: float | None
    brain_vol: float | None
    gm_vol: float | None
    wm_vol: float | None
    csf_vol: float | None
    etiv: float | None


def parse_euler_from_log(recon_all_log: Path) -> tuple[int, int] | None:
    """Return (lh_euler, rh_euler) parsed from recon-all.log, or None if not found."""
    if not recon_all_log.is_file():
        return None
    for line in recon_all_log.read_text().splitlines():
        m = _EULER_RE.search(line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def parse_recon_all_status(status_log: Path) -> Status:
    """Return OK / FAILED / INCOMPLETE based on recon-all-status.log content."""
    if not status_log.is_file():
        return "INCOMPLETE"
    text = status_log.read_text()
    if "finished without error" in text:
        return "OK"
    if "exited with ERRORS" in text or "ERROR" in text:
        return "FAILED"
    return "INCOMPLETE"


def parse_aseg_stats(aseg_stats: Path) -> dict[str, float]:
    """Parse aseg.stats Measure lines into a dict of named volumes."""
    if not aseg_stats.is_file():
        return {}
    text = aseg_stats.read_text()
    label_to_key = {
        "BrainSeg": "brain_vol",
        "TotalGray": "gm_vol",
        "CerebralWhiteMatter": "wm_vol",
        "CSF": "csf_vol",
        "EstimatedTotalIntraCranialVol": "etiv",
    }
    out: dict[str, float] = {}
    for line in text.splitlines():
        m = _ASEG_RE.search(line)
        if m:
            label, val = m.group(1), m.group(2)
            if label in label_to_key:
                out[label_to_key[label]] = float(val)
    return out


def _parse_elapsed(recon_all_log: Path) -> float | None:
    if not recon_all_log.is_file():
        return None
    for line in recon_all_log.read_text().splitlines():
        m = _ELAPSED_RE.search(line)
        if m:
            return float(m.group(1))
    return None


def compute_freesurfer(fs_subject_dir: Path) -> FreeSurferMetrics:
    """Compute FreeSurfer QC metrics from a recon-all subject directory."""
    if not fs_subject_dir.is_dir():
        return FreeSurferMetrics(
            status="MISSING",
            elapsed_hours=None,
            euler_lh=None, euler_rh=None, euler_mean=None,
            holes_lh=None, holes_rh=None, holes_mean=None,
            brain_vol=None, gm_vol=None, wm_vol=None, csf_vol=None, etiv=None,
        )

    status = parse_recon_all_status(fs_subject_dir / "scripts" / "recon-all-status.log")
    elapsed = _parse_elapsed(fs_subject_dir / "scripts" / "recon-all.log")
    euler = parse_euler_from_log(fs_subject_dir / "scripts" / "recon-all.log")
    aseg = parse_aseg_stats(fs_subject_dir / "stats" / "aseg.stats")

    if euler is None:
        euler_lh = euler_rh = euler_mean = None
        holes_lh = holes_rh = holes_mean = None
    else:
        euler_lh, euler_rh = euler
        euler_mean = (euler_lh + euler_rh) / 2.0
        holes_lh = (2 - euler_lh) // 2
        holes_rh = (2 - euler_rh) // 2
        holes_mean = (holes_lh + holes_rh) / 2.0

    return FreeSurferMetrics(
        status=status,
        elapsed_hours=elapsed,
        euler_lh=euler_lh,
        euler_rh=euler_rh,
        euler_mean=euler_mean,
        holes_lh=holes_lh,
        holes_rh=holes_rh,
        holes_mean=holes_mean,
        brain_vol=aseg.get("brain_vol"),
        gm_vol=aseg.get("gm_vol"),
        wm_vol=aseg.get("wm_vol"),
        csf_vol=aseg.get("csf_vol"),
        etiv=aseg.get("etiv"),
    )
```

- [ ] **Step 3.4: Run tests, verify pass**

```bash
uv run pytest tests/qa/test_freesurfer.py -v
```
Expected: 9 passing.

- [ ] **Step 3.5: Commit**

```bash
git add src/neuro_workflow/qa/metrics/freesurfer.py tests/qa/test_freesurfer.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): add FreeSurfer metrics module (Euler, holes, aseg.stats)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Output presence check module (TDD)

**Files:**
- Create: `src/neuro_workflow/qa/metrics/outputs.py`
- Create: `tests/qa/test_outputs.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/qa/test_outputs.py`:

```python
"""Tests for src/neuro_workflow/qa/metrics/outputs.py."""
import pytest

from neuro_workflow.qa.metrics.outputs import (
    OutputCheckResult,
    ScanID,
    check_expected_outputs,
)


def _make_scan_outputs(tmp_path, subject="sub-s03", session="ses-01",
                      task="rest", run="1", spaces=None):
    """Build a fake fmriprep derivatives tree with the listed output spaces."""
    func_dir = tmp_path / subject / session / "func"
    func_dir.mkdir(parents=True)
    base = f"{subject}_{session}_task-{task}_run-{run}"
    spaces = spaces or [""]  # "" = bold ref space (no _space- suffix)

    for space in spaces:
        suffix = f"_space-{space}" if space else ""
        if space.endswith("hemi-L_fsaverage6") or space.endswith("hemi-R_fsaverage6"):
            hemi = "L" if "hemi-L" in space else "R"
            (func_dir / f"{base}_hemi-{hemi}_space-fsaverage6_bold.func.gii").touch()
        elif space.endswith("hemi-L_fsnative") or space.endswith("hemi-R_fsnative"):
            hemi = "L" if "hemi-L" in space else "R"
            (func_dir / f"{base}_hemi-{hemi}_space-fsnative_bold.func.gii").touch()
        elif space == "fsLR_91k":
            (func_dir / f"{base}_space-fsLR_den-91k_bold.dtseries.nii").touch()
        elif space == "":
            (func_dir / f"{base}_desc-preproc_bold.nii.gz").touch()
        elif space.startswith("MNI152NLin2009cAsym_res-1"):
            (func_dir / f"{base}_space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz").touch()
        elif space.startswith("MNI152NLin6Asym_res-2"):
            (func_dir / f"{base}_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz").touch()
        elif space == "T1w":
            (func_dir / f"{base}_space-T1w_desc-preproc_bold.nii.gz").touch()
        elif space == "confounds":
            (func_dir / f"{base}_desc-confounds_timeseries.tsv").touch()
    return tmp_path


def test_check_expected_outputs_complete(tmp_path):
    fmriprep = _make_scan_outputs(tmp_path, spaces=[
        "", "MNI152NLin2009cAsym_res-1", "MNI152NLin6Asym_res-2", "T1w",
        "hemi-L_fsaverage6", "hemi-R_fsaverage6",
        "hemi-L_fsnative", "hemi-R_fsnative",
        "fsLR_91k", "confounds",
    ])
    result = check_expected_outputs(fmriprep, ScanID("sub-s03", "ses-01", "rest", "1"))
    assert result.complete
    assert result.missing == []


def test_check_expected_outputs_missing_some(tmp_path):
    # Only the bold ref + confounds; no MNI / surface / CIFTI
    fmriprep = _make_scan_outputs(tmp_path, spaces=["", "confounds"])
    result = check_expected_outputs(fmriprep, ScanID("sub-s03", "ses-01", "rest", "1"))
    assert not result.complete
    assert any("MNI152NLin2009cAsym" in m for m in result.missing)
    assert any("fsLR" in m for m in result.missing)


def test_check_expected_outputs_no_files_at_all(tmp_path):
    result = check_expected_outputs(tmp_path, ScanID("sub-s03", "ses-01", "rest", "1"))
    assert not result.complete
    assert len(result.missing) == 10  # all expected outputs missing
```

- [ ] **Step 4.2: Run tests, verify failure**

```bash
uv run pytest tests/qa/test_outputs.py -v
```
Expected: ImportError.

- [ ] **Step 4.3: Implement `outputs.py`**

Create `src/neuro_workflow/qa/metrics/outputs.py`:

```python
"""Check presence of expected fmriprep output files for a given scan."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScanID:
    subject: str
    session: str
    task: str
    run: str


@dataclass
class OutputCheckResult:
    complete: bool
    missing: list[str] = field(default_factory=list)


_EXPECTED_SUFFIXES: list[str] = [
    "{base}_desc-preproc_bold.nii.gz",
    "{base}_space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz",
    "{base}_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz",
    "{base}_space-T1w_desc-preproc_bold.nii.gz",
    "{base}_hemi-L_space-fsaverage6_bold.func.gii",
    "{base}_hemi-R_space-fsaverage6_bold.func.gii",
    "{base}_hemi-L_space-fsnative_bold.func.gii",
    "{base}_hemi-R_space-fsnative_bold.func.gii",
    "{base}_space-fsLR_den-91k_bold.dtseries.nii",
    "{base}_desc-confounds_timeseries.tsv",
]


def check_expected_outputs(fmriprep_dir: Path, scan: ScanID) -> OutputCheckResult:
    """Verify all expected output files exist for the given scan.

    Searches:
        <fmriprep_dir>/<subject>/<session>/func/<base>_<suffix>

    Returns:
        OutputCheckResult with complete=True when all files exist, otherwise
        complete=False and a list of missing filenames (relative to func dir).
    """
    base = f"{scan.subject}_{scan.session}_task-{scan.task}_run-{scan.run}"
    func_dir = fmriprep_dir / scan.subject / scan.session / "func"
    missing = [
        suffix.format(base=base)
        for suffix in _EXPECTED_SUFFIXES
        if not (func_dir / suffix.format(base=base)).is_file()
    ]
    return OutputCheckResult(complete=not missing, missing=missing)
```

- [ ] **Step 4.4: Run tests, verify pass**

```bash
uv run pytest tests/qa/test_outputs.py -v
```
Expected: 3 passing.

- [ ] **Step 4.5: Commit**

```bash
git add src/neuro_workflow/qa/metrics/outputs.py tests/qa/test_outputs.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): add output presence check module

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Cohort outlier detection module (TDD)

**Files:**
- Create: `src/neuro_workflow/qa/cohort.py`
- Create: `tests/qa/test_cohort.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/qa/test_cohort.py`:

```python
"""Tests for src/neuro_workflow/qa/cohort.py."""
from neuro_workflow.qa.cohort import cohort_euler_outliers
from neuro_workflow.qa.metrics.freesurfer import FreeSurferMetrics


def _fs(euler_mean):
    """Build a minimal FreeSurferMetrics with euler_mean only."""
    return FreeSurferMetrics(
        status="OK", elapsed_hours=None,
        euler_lh=None, euler_rh=None, euler_mean=euler_mean,
        holes_lh=None, holes_rh=None, holes_mean=None,
        brain_vol=None, gm_vol=None, wm_vol=None, csf_vol=None, etiv=None,
    )


def test_cohort_euler_outliers_flags_extreme_low():
    # Mostly around -100, one outlier at -1000
    metrics = {f"sub-{i:02d}": _fs(-100.0 + i) for i in range(20)}
    metrics["sub-bad"] = _fs(-1000.0)
    flagged = cohort_euler_outliers(metrics, n_sigma=2.0)
    assert "sub-bad" in flagged
    assert "sub-00" not in flagged


def test_cohort_euler_outliers_no_outliers():
    metrics = {f"sub-{i:02d}": _fs(-100.0 + i) for i in range(20)}
    flagged = cohort_euler_outliers(metrics, n_sigma=2.0)
    assert flagged == set()


def test_cohort_euler_outliers_skips_missing_euler():
    metrics = {
        "sub-A": _fs(-100.0),
        "sub-B": _fs(-105.0),
        "sub-C": _fs(None),         # missing — excluded from cohort
        "sub-bad": _fs(-1000.0),
    }
    flagged = cohort_euler_outliers(metrics, n_sigma=2.0)
    assert "sub-bad" in flagged
    assert "sub-C" not in flagged


def test_cohort_euler_outliers_high_threshold():
    # n_sigma=10 should flag nothing for a normal-ish distribution
    metrics = {f"sub-{i:02d}": _fs(-100.0 + i * 5) for i in range(20)}
    flagged = cohort_euler_outliers(metrics, n_sigma=10.0)
    assert flagged == set()
```

- [ ] **Step 5.2: Run tests, verify failure**

```bash
uv run pytest tests/qa/test_cohort.py -v
```
Expected: ImportError.

- [ ] **Step 5.3: Implement `cohort.py`**

Create `src/neuro_workflow/qa/cohort.py`:

```python
"""Cohort-relative outlier detection for FreeSurfer Euler numbers."""
from __future__ import annotations

import numpy as np

from neuro_workflow.qa.metrics.freesurfer import FreeSurferMetrics


def cohort_euler_outliers(
    metrics: dict[str, FreeSurferMetrics],
    n_sigma: float = 2.0,
) -> set[str]:
    """Identify subjects whose Euler number is unusually low for the cohort.

    Uses median absolute deviation (MAD): a subject is flagged if its
    `euler_mean` is more than `n_sigma * MAD` below the cohort median.

    Subjects with no Euler value are excluded from the cohort calculation
    and never flagged here (their FS status will already convey the issue).
    """
    values = {k: v.euler_mean for k, v in metrics.items() if v.euler_mean is not None}
    if not values:
        return set()

    arr = np.array(list(values.values()))
    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    if mad == 0.0:
        return set()
    cutoff = median - n_sigma * mad
    return {sub for sub, v in values.items() if v < cutoff}
```

- [ ] **Step 5.4: Run tests, verify pass**

```bash
uv run pytest tests/qa/test_cohort.py -v
```
Expected: 4 passing.

- [ ] **Step 5.5: Commit**

```bash
git add src/neuro_workflow/qa/cohort.py tests/qa/test_cohort.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): add cohort-relative Euler outlier detection (MAD-based)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Decisions TSV loader (TDD)

**Files:**
- Create: `src/neuro_workflow/qa/decisions.py`
- Create: `tests/qa/test_decisions.py`

- [ ] **Step 6.1: Write failing tests**

Create `tests/qa/test_decisions.py`:

```python
"""Tests for src/neuro_workflow/qa/decisions.py."""
from neuro_workflow.qa.decisions import Decision, ScanKey, load_decisions


def _write_tsv(tmp_path, content):
    p = tmp_path / "decisions.tsv"
    p.write_text(content)
    return p


def test_load_decisions_scan_level(tmp_path):
    p = _write_tsv(tmp_path, (
        "subject\tsession\ttask\trun\taction\treason\n"
        "sub-s03\tses-11\tstopSignalWDF\t1\texclude\tnon-monotonic onsets\n"
    ))
    result = load_decisions(p)
    key = ScanKey("sub-s03", "ses-11", "stopSignalWDF", "1")
    assert key in result
    assert result[key].action == "exclude"
    assert result[key].reason == "non-monotonic onsets"


def test_load_decisions_subject_level(tmp_path):
    p = _write_tsv(tmp_path, (
        "subject\tsession\ttask\trun\taction\treason\n"
        "sub-s1351\t-\t-\t-\tpass\tvisually inspected\n"
    ))
    result = load_decisions(p)
    assert "sub-s1351" in result
    assert result["sub-s1351"].action == "pass"


def test_load_decisions_missing_file_returns_empty(tmp_path):
    result = load_decisions(tmp_path / "nonexistent.tsv")
    assert result == {}


def test_load_decisions_invalid_action_raises(tmp_path):
    p = _write_tsv(tmp_path, (
        "subject\tsession\ttask\trun\taction\treason\n"
        "sub-s03\t-\t-\t-\tnonsense\twhatever\n"
    ))
    import pytest
    with pytest.raises(ValueError, match="invalid action"):
        load_decisions(p)


def test_load_decisions_skips_blank_lines(tmp_path):
    p = _write_tsv(tmp_path, (
        "subject\tsession\ttask\trun\taction\treason\n"
        "\n"
        "sub-s03\tses-11\tstopSignalWDF\t1\texclude\twhy\n"
    ))
    result = load_decisions(p)
    assert len(result) == 1
```

- [ ] **Step 6.2: Run tests, verify failure**

```bash
uv run pytest tests/qa/test_decisions.py -v
```
Expected: ImportError.

- [ ] **Step 6.3: Implement `decisions.py`**

Create `src/neuro_workflow/qa/decisions.py`:

```python
"""Load user QC decisions from a sidecar TSV."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Action = Literal["pass", "exclude", "review"]
_VALID_ACTIONS = {"pass", "exclude", "review"}


@dataclass(frozen=True)
class ScanKey:
    subject: str
    session: str
    task: str
    run: str


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str


def load_decisions(path: Path) -> dict[ScanKey | str, Decision]:
    """Read a QC decisions TSV.

    Schema (tab-separated):
        subject  session  task  run  action  reason

    Subject-level decisions use "-" for session/task/run; the key in the
    returned dict is the subject string. Scan-level decisions use a
    `ScanKey` as the dict key.

    Returns an empty dict if the file does not exist.
    Raises ValueError on invalid action values.
    """
    if not path.is_file():
        return {}

    out: dict[ScanKey | str, Decision] = {}
    with path.open() as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            if not row.get("subject"):
                continue
            action = row["action"].strip()
            if action not in _VALID_ACTIONS:
                raise ValueError(
                    f"invalid action {action!r} in {path}; "
                    f"valid: {sorted(_VALID_ACTIONS)}"
                )
            decision = Decision(action=action, reason=row.get("reason", "").strip())
            session = row.get("session", "-").strip()
            if session == "-" or not session:
                out[row["subject"]] = decision
            else:
                key = ScanKey(
                    subject=row["subject"],
                    session=session,
                    task=row["task"].strip(),
                    run=row["run"].strip(),
                )
                out[key] = decision
    return out
```

- [ ] **Step 6.4: Run tests, verify pass**

```bash
uv run pytest tests/qa/test_decisions.py -v
```
Expected: 5 passing.

- [ ] **Step 6.5: Commit**

```bash
git add src/neuro_workflow/qa/decisions.py tests/qa/test_decisions.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): add decisions TSV loader

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Reliability movies wrapper (TDD)

**Files:**
- Create: `src/neuro_workflow/qa/reliability_movies.py`
- Create: `tests/qa/test_reliability_movies.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/qa/test_reliability_movies.py`:

```python
"""Tests for src/neuro_workflow/qa/reliability_movies.py.

Mocks the bold_reliability_movies API so tests run without ffmpeg.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

from neuro_workflow.qa.reliability_movies import MovieResult, render_reliability_movies


def test_render_reliability_movies_success(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    # Mock FmriprepFrameSource and make_videos
    fake_group = MagicMock()
    fake_group.name = "sub-s03"
    fake_summary = MagicMock()
    fake_summary.path = out / "sub-s03.mp4"
    fake_summary.error = None

    with patch("neuro_workflow.qa.reliability_movies.FmriprepFrameSource") as FS, \
         patch("neuro_workflow.qa.reliability_movies.make_videos") as MV, \
         patch("neuro_workflow.qa.reliability_movies.get_renderer") as GR:
        FS.return_value.discover.return_value = [fake_group]
        MV.return_value = [fake_summary]
        GR.return_value = MagicMock()

        result = render_reliability_movies(deriv, out, ["sub-s03"])

    assert "sub-s03" in result
    assert result["sub-s03"].path == out / "sub-s03.mp4"
    assert result["sub-s03"].error is None


def test_render_reliability_movies_filters_subjects(tmp_path):
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    fake_a = MagicMock(); fake_a.name = "sub-A"
    fake_b = MagicMock(); fake_b.name = "sub-B"

    with patch("neuro_workflow.qa.reliability_movies.FmriprepFrameSource") as FS, \
         patch("neuro_workflow.qa.reliability_movies.make_videos") as MV, \
         patch("neuro_workflow.qa.reliability_movies.get_renderer") as GR:
        FS.return_value.discover.return_value = [fake_a, fake_b]
        MV.return_value = []
        GR.return_value = MagicMock()

        render_reliability_movies(deriv, out, ["sub-A"])

        # make_videos should be called with only the requested subject
        groups_passed = MV.call_args.kwargs["groups"]
        assert len(groups_passed) == 1
        assert groups_passed[0].name == "sub-A"


def test_render_reliability_movies_handles_per_subject_failure(tmp_path):
    """If make_videos raises for a subject, return error result instead of bubbling up."""
    out = tmp_path / "movies"
    deriv = tmp_path / "fmriprep_25.2.4"
    deriv.mkdir()

    fake_group = MagicMock(); fake_group.name = "sub-bad"

    with patch("neuro_workflow.qa.reliability_movies.FmriprepFrameSource") as FS, \
         patch("neuro_workflow.qa.reliability_movies.make_videos") as MV, \
         patch("neuro_workflow.qa.reliability_movies.get_renderer") as GR:
        FS.return_value.discover.return_value = [fake_group]
        MV.side_effect = RuntimeError("ffmpeg crashed")
        GR.return_value = MagicMock()

        result = render_reliability_movies(deriv, out, ["sub-bad"])

    assert "sub-bad" in result
    assert result["sub-bad"].path is None
    assert "ffmpeg crashed" in result["sub-bad"].error
```

- [ ] **Step 7.2: Run tests, verify failure**

```bash
uv run pytest tests/qa/test_reliability_movies.py -v
```
Expected: ImportError.

- [ ] **Step 7.3: Implement `reliability_movies.py`**

Create `src/neuro_workflow/qa/reliability_movies.py`:

```python
"""Wrapper around bold-reliability-movies for cohort QA report integration.

Catches per-subject failures so one bad subject doesn't abort the cohort.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from bold_reliability_movies import FmriprepFrameSource, make_videos
from bold_reliability_movies.renderers import get_renderer

log = logging.getLogger(__name__)


@dataclass
class MovieResult:
    path: Path | None
    error: str | None


def render_reliability_movies(
    fmriprep_dir: Path,
    output_movies_dir: Path,
    subjects: list[str],
) -> dict[str, MovieResult]:
    """Render one reliability movie per requested subject.

    Args:
        fmriprep_dir: fmriprep derivatives directory (input).
        output_movies_dir: where mp4 files are written.
        subjects: list of subject IDs (e.g., ["sub-s03"]) to render. Other
            subjects in the derivatives dir are ignored.

    Returns:
        Dict mapping subject ID → MovieResult. On error, MovieResult.path
        is None and .error contains a short message.
    """
    output_movies_dir.mkdir(parents=True, exist_ok=True)
    requested = set(subjects)

    source = FmriprepFrameSource(fmriprep_dir, group_by="subject")
    all_groups = source.discover()
    groups = [g for g in all_groups if g.name in requested]

    results: dict[str, MovieResult] = {s: MovieResult(None, "not discovered by brm") for s in subjects}

    if not groups:
        return results

    try:
        summaries = make_videos(
            groups=groups,
            renderer=get_renderer("mosaic"),
            out_dir=output_movies_dir,
            fps=2,
            codec="libx264",
        )
        for s in summaries:
            sub_id = getattr(s, "name", None) or getattr(s, "group_name", None)
            if sub_id is None:
                continue
            err = getattr(s, "error", None)
            results[sub_id] = MovieResult(
                path=Path(s.path) if not err and getattr(s, "path", None) else None,
                error=str(err) if err else None,
            )
    except Exception as exc:  # noqa: BLE001
        log.exception("brm make_videos failed; marking all requested subjects errored")
        for s in subjects:
            results[s] = MovieResult(None, str(exc))

    return results
```

- [ ] **Step 7.4: Run tests, verify pass**

```bash
uv run pytest tests/qa/test_reliability_movies.py -v
```
Expected: 3 passing.

- [ ] **Step 7.5: Commit**

```bash
git add src/neuro_workflow/qa/reliability_movies.py tests/qa/test_reliability_movies.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): add brm wrapper with per-subject error handling

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Vendor DataTables CSS/JS

**Files:**
- Create: `src/neuro_workflow/qa/templates/__init__.py`
- Create: `src/neuro_workflow/qa/templates/static/datatables.min.js`
- Create: `src/neuro_workflow/qa/templates/static/datatables.min.css`
- Create: `src/neuro_workflow/qa/templates/static/style.css`

- [ ] **Step 8.1: Make templates package**

```bash
mkdir -p /home/users/logben/neuro_workflow/src/neuro_workflow/qa/templates/static
touch /home/users/logben/neuro_workflow/src/neuro_workflow/qa/templates/__init__.py
```

- [ ] **Step 8.2: Vendor DataTables (download minified files)**

DataTables from https://datatables.net/download/. Pinned version: 2.1.8 (jQuery 3.7.1 + DataTables core, basic styling).

```bash
cd /home/users/logben/neuro_workflow/src/neuro_workflow/qa/templates/static
curl -fsSL -o datatables.min.css https://cdn.datatables.net/v/dt/jq-3.7.0/dt-2.1.8/datatables.min.css
curl -fsSL -o datatables.min.js  https://cdn.datatables.net/v/dt/jq-3.7.0/dt-2.1.8/datatables.min.js
ls -la datatables.min.{js,css}
# Expected: ~150-200 KB total
```

If `curl` fails (no internet from compute node), fall back: from a local browser, save the same URLs and `scp` to that path.

- [ ] **Step 8.3: Add minimal custom style.css**

Create `src/neuro_workflow/qa/templates/static/style.css`:

```css
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       margin: 1.5em; line-height: 1.4; color: #222; }
.banner { padding: 1em; background: #f5f5f5; border-radius: 6px; margin-bottom: 1em; }
.pill { display: inline-block; padding: 0.2em 0.6em; border-radius: 12px;
        font-size: 0.85em; margin-right: 0.4em; font-weight: 600; }
.pill.ok { background: #d4edda; color: #155724; }
.pill.warn { background: #fff3cd; color: #856404; }
.pill.fail { background: #f8d7da; color: #721c24; }
.flagged { background: #fff8e6; }
.excluded { text-decoration: line-through; opacity: 0.6; }
.review { background: #fff3cd; }
.svg-block { margin: 1em 0; }
.svg-block img { max-width: 100%; }
.cohort-bar { display: inline-block; height: 0.8em; vertical-align: middle;
              background: linear-gradient(to right, #d4edda, #fff3cd, #f8d7da); }
details { margin: 0.5em 0; padding: 0.5em; background: #fafafa; border-left: 3px solid #ddd; }
details[open] { background: #fff; }
summary { cursor: pointer; font-weight: 600; }
table.scan-table td.flag-cell { font-weight: 600; }
.mark-review-btn { font-size: 0.8em; padding: 0.2em 0.6em; }
video { display: block; margin: 1em 0; max-width: 100%; }
```

- [ ] **Step 8.4: Verify file sizes (sanity check)**

```bash
ls -la /home/users/logben/neuro_workflow/src/neuro_workflow/qa/templates/static/
```
Expected: `datatables.min.css` ≈ 30-50 KB, `datatables.min.js` ≈ 150-200 KB, `style.css` ≈ 1-2 KB.

- [ ] **Step 8.5: Commit**

```bash
git add src/neuro_workflow/qa/templates/__init__.py src/neuro_workflow/qa/templates/static/
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): vendor DataTables 2.1.8 + add custom QA stylesheet

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Cohort HTML template + render function (TDD)

**Files:**
- Create: `src/neuro_workflow/qa/templates/cohort.html.j2`
- Create: tests covered by Task 11 integration tests + structural inspection here

- [ ] **Step 9.1: Write failing structural test**

Create `tests/qa/test_templates.py`:

```python
"""Tests for src/neuro_workflow/qa/templates rendering."""
from neuro_workflow.qa.templates import render_cohort_html, render_subject_html
from neuro_workflow.qa.metrics.freesurfer import FreeSurferMetrics
from neuro_workflow.qa.metrics.motion import MotionMetrics
import pandas as pd


def _fs_ok(euler=-100.0):
    return FreeSurferMetrics(
        status="OK", elapsed_hours=10.0,
        euler_lh=int(euler), euler_rh=int(euler), euler_mean=euler,
        holes_lh=51, holes_rh=51, holes_mean=51.0,
        brain_vol=1100000.0, gm_vol=600000.0, wm_vol=500000.0,
        csf_vol=1500.0, etiv=1500000.0,
    )


def test_render_cohort_html_contains_subjects():
    rows = [
        {
            "subject": "sub-s03",
            "sessions": 12,
            "scans": 57,
            "fs_euler_mean": -100.0,
            "fs_holes_mean": 51.0,
            "fs_status": "OK",
            "scans_flagged_motion": 0,
            "scans_flagged_outputs": 0,
            "scan_flags_total": 0,
            "decision_action": "unset",
            "decision_reason": "",
            "outlier": False,
        },
    ]
    html = render_cohort_html(
        rows=rows, n_subjects=1, n_scans=57, n_flagged_scans=0,
        fmriprep_version="25.2.4",
    )
    assert "sub-s03" in html
    assert "DataTable" in html  # the JS library or its initialization
    assert "datatables.min.js" in html or "<script" in html


def test_render_cohort_html_marks_excluded():
    rows = [
        {"subject": "sub-bad", "sessions": 12, "scans": 50,
         "fs_euler_mean": -100.0, "fs_holes_mean": 51.0, "fs_status": "OK",
         "scans_flagged_motion": 0, "scans_flagged_outputs": 0,
         "scan_flags_total": 0, "decision_action": "exclude",
         "decision_reason": "manual exclusion", "outlier": False},
    ]
    html = render_cohort_html(rows=rows, n_subjects=1, n_scans=50,
                              n_flagged_scans=0, fmriprep_version="25.2.4")
    assert "excluded" in html.lower()
```

- [ ] **Step 9.2: Run tests, verify failure**

```bash
uv run pytest tests/qa/test_templates.py -v
```
Expected: ImportError on `neuro_workflow.qa.templates`.

- [ ] **Step 9.3: Add `render_cohort_html` to templates `__init__.py`**

Edit `src/neuro_workflow/qa/templates/__init__.py`:

```python
"""Jinja2 template rendering for QA HTML reports."""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

import jinja2

_TEMPLATE_DIR = Path(__file__).parent
_STATIC_DIR = _TEMPLATE_DIR / "static"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATE_DIR),
    autoescape=jinja2.select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _read_static(name: str) -> str:
    return (_STATIC_DIR / name).read_text()


def render_cohort_html(*, rows, n_subjects, n_scans, n_flagged_scans, fmriprep_version) -> str:
    template = _env.get_template("cohort.html.j2")
    return template.render(
        rows=rows,
        n_subjects=n_subjects,
        n_scans=n_scans,
        n_flagged_scans=n_flagged_scans,
        fmriprep_version=fmriprep_version,
        datatables_css=_read_static("datatables.min.css"),
        datatables_js=_read_static("datatables.min.js"),
        style_css=_read_static("style.css"),
    )


def render_subject_html(*, subject, fs_metrics, scans, fmriprep_version,
                        movie_relpath, decision_action, decision_reason,
                        embed_svg) -> str:
    template = _env.get_template("subject.html.j2")
    return template.render(
        subject=subject,
        fs_metrics=fs_metrics,
        scans=scans,
        fmriprep_version=fmriprep_version,
        movie_relpath=movie_relpath,
        decision_action=decision_action,
        decision_reason=decision_reason,
        embed_svg=embed_svg,
        style_css=_read_static("style.css"),
    )
```

- [ ] **Step 9.4: Create `cohort.html.j2`**

Create `src/neuro_workflow/qa/templates/cohort.html.j2`:

```jinja
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>QA Cohort Report — fmriprep {{ fmriprep_version }}</title>
<style>{{ datatables_css|safe }}</style>
<style>{{ style_css|safe }}</style>
</head>
<body>
<div class="banner">
  <h1>QA Cohort Report</h1>
  <p><b>fMRIPrep version:</b> {{ fmriprep_version }} —
     <b>Subjects:</b> {{ n_subjects }} —
     <b>Scans:</b> {{ n_scans }} —
     <b>Flagged scans:</b> {{ n_flagged_scans }}</p>
</div>

<table id="cohort" class="display">
  <thead>
    <tr>
      <th>Subject</th>
      <th>Sessions</th>
      <th>Scans</th>
      <th>FS Euler (mean)</th>
      <th>FS holes (mean)</th>
      <th>FS status</th>
      <th>Motion flags</th>
      <th>Output flags</th>
      <th>Total flags</th>
      <th>Decision</th>
      <th>Note</th>
    </tr>
  </thead>
  <tbody>
  {% for row in rows %}
    <tr class="{% if row.decision_action == 'exclude' %}excluded{% elif row.decision_action == 'review' %}review{% elif row.scan_flags_total > 0 %}flagged{% endif %}">
      <td><a href="subjects/{{ row.subject }}.html">{{ row.subject }}</a></td>
      <td>{{ row.sessions }}</td>
      <td>{{ row.scans }}</td>
      <td>{{ "%.0f"|format(row.fs_euler_mean) if row.fs_euler_mean is not none else "—" }}</td>
      <td>{{ "%.0f"|format(row.fs_holes_mean) if row.fs_holes_mean is not none else "—" }}</td>
      <td>{{ row.fs_status }}</td>
      <td>{{ row.scans_flagged_motion }}</td>
      <td>{{ row.scans_flagged_outputs }}</td>
      <td class="flag-cell">{{ row.scan_flags_total }}</td>
      <td>{{ row.decision_action }}</td>
      <td>{{ row.decision_reason }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>

<script>{{ datatables_js|safe }}</script>
<script>
$(function() {
  $('#cohort').DataTable({
    pageLength: 100,
    order: [[8, 'desc']],   // Total flags desc — flagged subjects on top
  });
});
</script>
</body>
</html>
```

- [ ] **Step 9.5: Run tests, verify pass**

```bash
uv run pytest tests/qa/test_templates.py::test_render_cohort_html_contains_subjects \
              tests/qa/test_templates.py::test_render_cohort_html_marks_excluded -v
```
Expected: 2 passing.

- [ ] **Step 9.6: Commit**

```bash
git add src/neuro_workflow/qa/templates/__init__.py src/neuro_workflow/qa/templates/cohort.html.j2 tests/qa/test_templates.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): add cohort HTML template + render_cohort_html

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Subject HTML template (TDD)

**Files:**
- Create: `src/neuro_workflow/qa/templates/subject.html.j2`
- Modify: `tests/qa/test_templates.py` (append)

- [ ] **Step 10.1: Append failing tests for subject template**

Append to `tests/qa/test_templates.py`:

```python
def test_render_subject_html_contains_fs_card():
    fs = _fs_ok(euler=-200)
    html = render_subject_html(
        subject="sub-s03",
        fs_metrics=fs,
        scans=[],
        fmriprep_version="25.2.4",
        movie_relpath="../movies/sub-s03.mp4",
        decision_action="unset",
        decision_reason="",
        embed_svg=lambda p: "",  # no SVGs in this minimal test
    )
    assert "sub-s03" in html
    assert "FreeSurfer" in html
    assert "Euler" in html
    assert "-200" in html


def test_render_subject_html_embeds_video():
    fs = _fs_ok()
    html = render_subject_html(
        subject="sub-s03",
        fs_metrics=fs,
        scans=[],
        fmriprep_version="25.2.4",
        movie_relpath="../movies/sub-s03.mp4",
        decision_action="unset",
        decision_reason="",
        embed_svg=lambda p: "",
    )
    assert "<video" in html
    assert "sub-s03.mp4" in html


def test_render_subject_html_auto_expands_flagged_scans():
    fs = _fs_ok()
    scans = [
        {
            "session": "ses-01", "task": "rest", "run": "1",
            "n_vols": 154, "fd_mean": 0.3, "fd_prop_over_05": 0.05,
            "dvars_mean": 1.2, "dvars_prop_over_15": 0.05,
            "n_motion_outliers": 2,
            "outputs_complete": True, "missing_outputs": [],
            "flagged": True, "flag_reasons": ["rest FD mean 0.300 > 0.2"],
            "decision_action": "unset", "decision_reason": "",
            "carpetplot_svg": "", "coreg_svg": "", "sdc_svg": "",
        }
    ]
    html = render_subject_html(
        subject="sub-s03",
        fs_metrics=fs,
        scans=scans,
        fmriprep_version="25.2.4",
        movie_relpath="../movies/sub-s03.mp4",
        decision_action="unset",
        decision_reason="",
        embed_svg=lambda p: "",
    )
    # Flagged scan's <details> should be open by default
    assert "<details open" in html
```

- [ ] **Step 10.2: Run tests, verify failure**

```bash
uv run pytest tests/qa/test_templates.py -v
```
Expected: 3 new tests fail.

- [ ] **Step 10.3: Create `subject.html.j2`**

Create `src/neuro_workflow/qa/templates/subject.html.j2`:

```jinja
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>QA Report — {{ subject }}</title>
<style>{{ style_css|safe }}</style>
</head>
<body>

<h1>{{ subject }}</h1>
<p><b>fMRIPrep version:</b> {{ fmriprep_version }}
{% if decision_action != 'unset' %}
  <span class="pill {{ 'fail' if decision_action == 'exclude' else 'warn' }}">
    Decision: {{ decision_action }} — {{ decision_reason }}
  </span>
{% endif %}
</p>

<h2>FreeSurfer reconstruction</h2>
<div class="fs-card">
  <p>
    <b>Status:</b>
    <span class="pill {{ 'ok' if fs_metrics.status == 'OK' else 'fail' }}">{{ fs_metrics.status }}</span>
    {% if fs_metrics.elapsed_hours is not none %}
    <b>Runtime:</b> {{ "%.1f"|format(fs_metrics.elapsed_hours) }}h
    {% endif %}
  </p>
  {% if fs_metrics.euler_mean is not none %}
  <p>
    <b>Euler:</b> lh={{ fs_metrics.euler_lh }}, rh={{ fs_metrics.euler_rh }},
    mean={{ "%.0f"|format(fs_metrics.euler_mean) }}.
    <b>Holes:</b> lh={{ fs_metrics.holes_lh }}, rh={{ fs_metrics.holes_rh }},
    mean={{ "%.1f"|format(fs_metrics.holes_mean) }}.
  </p>
  {% endif %}
  {% if fs_metrics.brain_vol %}
  <details>
    <summary>Volumes (aseg)</summary>
    <ul>
      <li>Brain: {{ "%.0f"|format(fs_metrics.brain_vol) }} mm³</li>
      <li>GM: {{ "%.0f"|format(fs_metrics.gm_vol) }} mm³</li>
      <li>WM: {{ "%.0f"|format(fs_metrics.wm_vol) }} mm³</li>
      <li>CSF: {{ "%.0f"|format(fs_metrics.csf_vol) }} mm³</li>
      <li>eTIV: {{ "%.0f"|format(fs_metrics.etiv) }} mm³</li>
    </ul>
  </details>
  {% endif %}
</div>

<h2>Reliability movie</h2>
<video controls width="720">
  <source src="{{ movie_relpath }}" type="video/mp4">
  Your browser does not support the video tag.
</video>

<h2>Per-scan</h2>
<table class="scan-table">
  <thead>
    <tr>
      <th>Session</th><th>Task</th><th>Run</th>
      <th>n_vols</th>
      <th>FD mean</th><th>%FD&gt;0.5</th>
      <th>DVARS mean</th><th>%std_DVARS&gt;1.5</th>
      <th>Outliers</th>
      <th>Outputs</th>
      <th>Flag</th>
      <th>Decision</th>
    </tr>
  </thead>
  <tbody>
  {% for scan in scans %}
    <tr class="{% if scan.flagged %}flagged{% endif %}">
      <td>{{ scan.session }}</td>
      <td>{{ scan.task }}</td>
      <td>{{ scan.run }}</td>
      <td>{{ scan.n_vols }}</td>
      <td>{{ "%.3f"|format(scan.fd_mean) }}</td>
      <td>{{ "%.1f"|format(scan.fd_prop_over_05 * 100) }}%</td>
      <td>{{ "%.3f"|format(scan.dvars_mean) }}</td>
      <td>{{ "%.1f"|format(scan.dvars_prop_over_15 * 100) }}%</td>
      <td>{{ scan.n_motion_outliers }}</td>
      <td>{{ "OK" if scan.outputs_complete else (scan.missing_outputs|length ~ " missing") }}</td>
      <td class="flag-cell">{% if scan.flagged %}flag{% else %}—{% endif %}</td>
      <td>{{ scan.decision_action }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>

<h2>Per-scan figures</h2>
{% for scan in scans %}
<details {% if scan.flagged %}open{% endif %}>
  <summary>{{ scan.session }} {{ scan.task }} run-{{ scan.run }}
    {% if scan.flagged %}<span class="pill warn">flagged: {{ scan.flag_reasons|join('; ') }}</span>{% endif %}
  </summary>

  {% if scan.carpetplot_svg %}
  <div class="svg-block"><h4>Carpet plot</h4>{{ scan.carpetplot_svg|safe }}</div>
  {% endif %}
  {% if scan.coreg_svg %}
  <div class="svg-block"><h4>Coregistration (BOLD ↔ T1w)</h4>{{ scan.coreg_svg|safe }}</div>
  {% endif %}
  {% if scan.sdc_svg %}
  <div class="svg-block"><h4>Susceptibility distortion correction</h4>{{ scan.sdc_svg|safe }}</div>
  {% endif %}

</details>
{% endfor %}

</body>
</html>
```

- [ ] **Step 10.4: Run tests, verify pass**

```bash
uv run pytest tests/qa/test_templates.py -v
```
Expected: 5 passing (2 cohort + 3 subject).

- [ ] **Step 10.5: Commit**

```bash
git add src/neuro_workflow/qa/templates/subject.html.j2 tests/qa/test_templates.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): add subject HTML template with FS card, video, scan figures

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Orchestrator (replace report.py)

**Files:**
- Modify: `src/neuro_workflow/qa/report.py` (full rewrite)
- Create: `tests/qa/test_report_orchestrator.py`

- [ ] **Step 11.1: Build a tiny fmriprep fixture**

Create `tests/qa/fixtures/__init__.py` (empty), then a fixture builder helper. Append to `tests/qa/test_report_orchestrator.py` (creating the file):

```python
"""Integration tests for src/neuro_workflow/qa/report.py orchestrator."""
import pandas as pd
from pathlib import Path
from unittest.mock import patch, MagicMock

from neuro_workflow.qa.report import build_reports
from neuro_workflow.qa.reliability_movies import MovieResult


def _build_fixture(tmp_path: Path) -> Path:
    """Build a minimal fmriprep derivatives tree with one subject + one scan."""
    deriv = tmp_path / "fmriprep_25.2.4"
    func_dir = deriv / "sub-s03" / "ses-01" / "func"
    func_dir.mkdir(parents=True)
    base = "sub-s03_ses-01_task-rest_run-1"

    # Confounds (the only file we actually parse)
    pd.DataFrame({
        "framewise_displacement": [None] + [0.1] * 9,
        "std_dvars": [None] + [1.0] * 9,
    }).to_csv(func_dir / f"{base}_desc-confounds_timeseries.tsv",
              sep="\t", index=False, na_rep="n/a")

    # Touch all expected outputs so check_expected_outputs returns complete
    for suffix in [
        f"{base}_desc-preproc_bold.nii.gz",
        f"{base}_space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz",
        f"{base}_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz",
        f"{base}_space-T1w_desc-preproc_bold.nii.gz",
        f"{base}_hemi-L_space-fsaverage6_bold.func.gii",
        f"{base}_hemi-R_space-fsaverage6_bold.func.gii",
        f"{base}_hemi-L_space-fsnative_bold.func.gii",
        f"{base}_hemi-R_space-fsnative_bold.func.gii",
        f"{base}_space-fsLR_den-91k_bold.dtseries.nii",
    ]:
        (func_dir / suffix).touch()

    # FreeSurfer
    fs = deriv / "sourcedata" / "freesurfer" / "sub-s03_ses-01"
    (fs / "scripts").mkdir(parents=True)
    (fs / "stats").mkdir(parents=True)
    (fs / "scripts" / "recon-all-status.log").write_text(
        "recon-all -s sub-s03_ses-01 finished without error at ...\n")
    (fs / "scripts" / "recon-all.log").write_text(
        "orig.nofix lheno = -100, rheno = -80\n"
        "#@#%# recon-all-run-time-hours 9.5\n")
    (fs / "stats" / "aseg.stats").write_text(
        "# Measure BrainSeg, BrainSegVol, Brain Segmentation Volume, 1100000.0, mm^3\n"
        "# Measure TotalGray, TotalGrayVol, Total gray matter volume, 600000.0, mm^3\n"
        "# Measure CerebralWhiteMatter, CerebralWhiteMatterVol, Cerebral White Matter Volume, 500000.0, mm^3\n"
        "# Measure CSF, CSFVol, CSF Volume, 1500.0, mm^3\n"
        "# Measure EstimatedTotalIntraCranialVol, eTIV, Estimated Total Intracranial Volume, 1500000.0, mm^3\n")
    return deriv


def test_build_reports_emits_cohort_and_subject_html(tmp_path):
    deriv = _build_fixture(tmp_path)
    out = tmp_path / "qa_html"

    with patch("neuro_workflow.qa.report.render_reliability_movies") as MV:
        MV.return_value = {"sub-s03": MovieResult(out / "movies/sub-s03.mp4", None)}
        build_reports(
            fmriprep_dir=deriv,
            output_dir=out,
            subjects=["sub-s03"],
            decisions_path=None,
            no_reliability_movies=False,
            euler_n_sigma=2.0,
        )

    assert (out / "cohort.html").is_file()
    assert (out / "cohort.tsv").is_file()
    assert (out / "subjects" / "sub-s03.html").is_file()


def test_build_reports_skips_brm_when_no_reliability_movies(tmp_path):
    deriv = _build_fixture(tmp_path)
    out = tmp_path / "qa_html"

    with patch("neuro_workflow.qa.report.render_reliability_movies") as MV:
        build_reports(
            fmriprep_dir=deriv,
            output_dir=out,
            subjects=["sub-s03"],
            decisions_path=None,
            no_reliability_movies=True,
            euler_n_sigma=2.0,
        )
        MV.assert_not_called()

    assert (out / "subjects" / "sub-s03.html").is_file()


def test_build_reports_renders_decision_from_tsv(tmp_path):
    deriv = _build_fixture(tmp_path)
    out = tmp_path / "qa_html"
    decisions = tmp_path / "decisions.tsv"
    decisions.write_text(
        "subject\tsession\ttask\trun\taction\treason\n"
        "sub-s03\t-\t-\t-\texclude\tmanual call\n"
    )

    with patch("neuro_workflow.qa.report.render_reliability_movies") as MV:
        MV.return_value = {"sub-s03": MovieResult(out / "movies/sub-s03.mp4", None)}
        build_reports(
            fmriprep_dir=deriv,
            output_dir=out,
            subjects=["sub-s03"],
            decisions_path=decisions,
            no_reliability_movies=False,
            euler_n_sigma=2.0,
        )

    cohort_html = (out / "cohort.html").read_text()
    assert "exclude" in cohort_html
    assert "manual call" in cohort_html
    # Excluded styling applied (see style.css):
    assert "excluded" in cohort_html
```

- [ ] **Step 11.2: Run tests, verify failure**

```bash
uv run pytest tests/qa/test_report_orchestrator.py -v
```
Expected: ImportError on `neuro_workflow.qa.report.build_reports` (still exists from old report.py but with different signature/behavior).

- [ ] **Step 11.3: Replace `report.py` contents**

Overwrite `src/neuro_workflow/qa/report.py`:

```python
"""QA report orchestrator — produces HTML cohort dashboard.

Delegates to:
- metrics/ for per-scan and per-subject metric extraction
- cohort.py for cohort-relative outlier flagging
- decisions.py for sidecar decision TSV
- reliability_movies.py for brm integration
- templates/ for Jinja2-rendered HTML output
"""
from __future__ import annotations

import csv
import logging
import re
from dataclasses import asdict
from pathlib import Path

from neuro_workflow.qa.cohort import cohort_euler_outliers
from neuro_workflow.qa.decisions import Decision, ScanKey, load_decisions
from neuro_workflow.qa.metrics.freesurfer import FreeSurferMetrics, compute_freesurfer
from neuro_workflow.qa.metrics.motion import MotionMetrics, compute_motion
from neuro_workflow.qa.metrics.outputs import OutputCheckResult, ScanID, check_expected_outputs
from neuro_workflow.qa.reliability_movies import MovieResult, render_reliability_movies
from neuro_workflow.qa.templates import render_cohort_html, render_subject_html

log = logging.getLogger(__name__)

_CONFOUNDS_RE = re.compile(
    r"(sub-\w+)_(ses-\w+)_task-(\w+)_run-(\w+)_desc-confounds_timeseries\.tsv"
)


def _discover_subjects(fmriprep_dir: Path) -> list[str]:
    return sorted(p.name for p in fmriprep_dir.glob("sub-*") if p.is_dir())


def _discover_scans(fmriprep_dir: Path, subject: str) -> list[ScanID]:
    out = []
    for confounds in (fmriprep_dir / subject).rglob("*_desc-confounds_timeseries.tsv"):
        m = _CONFOUNDS_RE.search(confounds.name)
        if m:
            out.append(ScanID(subject=m.group(1), session=m.group(2),
                              task=m.group(3), run=m.group(4)))
    return sorted(out, key=lambda s: (s.session, s.task, s.run))


def _find_fs_dir(fmriprep_dir: Path, subject: str) -> Path | None:
    """Find the FreeSurfer subject directory; supports per-session naming."""
    fs_root = fmriprep_dir / "sourcedata" / "freesurfer"
    if not fs_root.is_dir():
        return None
    candidates = list(fs_root.glob(f"{subject}_*"))
    if not candidates:
        candidates = list(fs_root.glob(f"{subject}"))
    if not candidates:
        return None
    # Prefer one that finished without error
    for c in candidates:
        status_log = c / "scripts" / "recon-all-status.log"
        if status_log.is_file() and "finished without error" in status_log.read_text():
            return c
    return candidates[0]


def _is_motion_flagged(motion: MotionMetrics, task: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    is_rest = task == "rest"
    if is_rest and motion.fd_mean > 0.2:
        reasons.append(f"rest FD mean {motion.fd_mean:.3f} > 0.2")
    if not is_rest and motion.fd_prop_over_05 > 0.20:
        reasons.append(f"%FD>0.5 = {motion.fd_prop_over_05*100:.1f}% > 20%")
    if motion.dvars_prop_over_15 > 0.20:
        reasons.append(f"%std_DVARS>1.5 = {motion.dvars_prop_over_15*100:.1f}% > 20%")
    return bool(reasons), reasons


def _scan_dict(scan: ScanID, motion: MotionMetrics, outputs: OutputCheckResult,
               decision: Decision | None) -> dict:
    flagged_motion, motion_reasons = _is_motion_flagged(motion, scan.task)
    flagged_outputs = not outputs.complete
    flag_reasons = list(motion_reasons)
    if flagged_outputs:
        flag_reasons.append(f"{len(outputs.missing)} missing output(s)")
    flagged = flagged_motion or flagged_outputs
    return {
        "session": scan.session, "task": scan.task, "run": scan.run,
        "n_vols": motion.n_vols,
        "fd_mean": motion.fd_mean, "fd_prop_over_05": motion.fd_prop_over_05,
        "dvars_mean": motion.dvars_mean, "dvars_prop_over_15": motion.dvars_prop_over_15,
        "n_motion_outliers": motion.n_motion_outliers,
        "outputs_complete": outputs.complete,
        "missing_outputs": outputs.missing,
        "flagged": flagged, "flag_reasons": flag_reasons,
        "flagged_motion": flagged_motion, "flagged_outputs": flagged_outputs,
        "decision_action": decision.action if decision else "unset",
        "decision_reason": decision.reason if decision else "",
        "carpetplot_svg": "", "coreg_svg": "", "sdc_svg": "",  # filled below
    }


def _embed_svg(path: Path) -> str:
    """Inline an SVG file as a string; empty if missing."""
    if not path.is_file():
        return ""
    try:
        return path.read_text()
    except OSError:
        return ""


def _attach_svgs(scan_dict: dict, fmriprep_dir: Path, subject: str) -> None:
    figures = fmriprep_dir / subject / "figures"
    base = f"{subject}_{scan_dict['session']}_task-{scan_dict['task']}_run-{scan_dict['run']}"
    scan_dict["carpetplot_svg"] = _embed_svg(figures / f"{base}_desc-carpetplot_bold.svg")
    scan_dict["coreg_svg"] = _embed_svg(figures / f"{base}_desc-coreg_bold.svg")
    scan_dict["sdc_svg"] = _embed_svg(figures / f"{base}_desc-sdc_bold.svg")


def build_reports(
    *,
    fmriprep_dir: Path,
    output_dir: Path,
    subjects: list[str] | None = None,
    decisions_path: Path | None = None,
    no_reliability_movies: bool = False,
    euler_n_sigma: float = 2.0,
) -> None:
    """Build cohort + per-subject HTML reports.

    Args:
        fmriprep_dir: fmriprep derivatives root.
        output_dir: where qa_html/ artifacts go.
        subjects: subset to process (default: all subjects in fmriprep_dir).
        decisions_path: optional sidecar TSV with QC decisions.
        no_reliability_movies: skip brm invocation.
        euler_n_sigma: MAD threshold for cohort Euler outliers.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "subjects").mkdir(exist_ok=True)
    (output_dir / "movies").mkdir(exist_ok=True)

    if subjects is None:
        subjects = _discover_subjects(fmriprep_dir)

    decisions = load_decisions(decisions_path) if decisions_path else {}

    # 1) Compute FS metrics per subject
    fs_metrics: dict[str, FreeSurferMetrics] = {}
    for sub in subjects:
        fs_dir = _find_fs_dir(fmriprep_dir, sub)
        fs_metrics[sub] = compute_freesurfer(fs_dir) if fs_dir else compute_freesurfer(Path("/nonexistent"))

    # 2) Cohort outlier set
    outliers = cohort_euler_outliers(fs_metrics, n_sigma=euler_n_sigma)

    # 3) Reliability movies (one per subject)
    movies: dict[str, MovieResult] = {}
    if not no_reliability_movies:
        movies = render_reliability_movies(fmriprep_dir, output_dir / "movies", subjects)

    # 4) Per-subject scan metrics + render subject HTML
    cohort_rows = []
    n_scans_total = 0
    n_flagged_scans_total = 0

    for sub in subjects:
        scans = _discover_scans(fmriprep_dir, sub)
        scan_dicts = []
        for scan in scans:
            confounds = (fmriprep_dir / sub / scan.session / "func"
                         / f"{sub}_{scan.session}_task-{scan.task}_run-{scan.run}_desc-confounds_timeseries.tsv")
            motion = compute_motion(confounds)
            outputs = check_expected_outputs(fmriprep_dir, scan)

            scan_decision = decisions.get(ScanKey(sub, scan.session, scan.task, scan.run))
            d = _scan_dict(scan, motion, outputs, scan_decision)
            _attach_svgs(d, fmriprep_dir, sub)
            scan_dicts.append(d)

        n_scans_total += len(scan_dicts)
        n_flagged_scans_total += sum(1 for s in scan_dicts if s["flagged"])

        # Subject-level decision
        sub_decision = decisions.get(sub)
        sub_action = sub_decision.action if sub_decision else "unset"
        sub_reason = sub_decision.reason if sub_decision else ""

        movie_result = movies.get(sub)
        movie_relpath = (
            f"../movies/{movie_result.path.name}"
            if movie_result and movie_result.path
            else ""
        )

        subject_html = render_subject_html(
            subject=sub,
            fs_metrics=fs_metrics[sub],
            scans=scan_dicts,
            fmriprep_version=fmriprep_dir.name.replace("fmriprep_", ""),
            movie_relpath=movie_relpath,
            decision_action=sub_action,
            decision_reason=sub_reason,
            embed_svg=_embed_svg,
        )
        (output_dir / "subjects" / f"{sub}.html").write_text(subject_html)

        cohort_rows.append({
            "subject": sub,
            "sessions": len({s.session for s in scans}),
            "scans": len(scan_dicts),
            "fs_euler_mean": fs_metrics[sub].euler_mean,
            "fs_holes_mean": fs_metrics[sub].holes_mean,
            "fs_status": fs_metrics[sub].status,
            "scans_flagged_motion": sum(1 for s in scan_dicts if s["flagged_motion"]),
            "scans_flagged_outputs": sum(1 for s in scan_dicts if s["flagged_outputs"]),
            "scan_flags_total": sum(1 for s in scan_dicts if s["flagged"]),
            "decision_action": sub_action,
            "decision_reason": sub_reason,
            "outlier": sub in outliers,
        })

    # 5) Render cohort HTML + TSV
    cohort_html = render_cohort_html(
        rows=cohort_rows,
        n_subjects=len(subjects),
        n_scans=n_scans_total,
        n_flagged_scans=n_flagged_scans_total,
        fmriprep_version=fmriprep_dir.name.replace("fmriprep_", ""),
    )
    (output_dir / "cohort.html").write_text(cohort_html)

    with (output_dir / "cohort.tsv").open("w", newline="") as f:
        if cohort_rows:
            writer = csv.DictWriter(f, fieldnames=list(cohort_rows[0].keys()), delimiter="\t")
            writer.writeheader()
            writer.writerows(cohort_rows)
```

- [ ] **Step 11.4: Run tests, verify pass**

```bash
uv run pytest tests/qa/test_report_orchestrator.py -v
```
Expected: 3 passing.

- [ ] **Step 11.5: Run all qa tests together**

```bash
uv run pytest tests/qa/ -v
```
Expected: all passing (~25 tests).

- [ ] **Step 11.6: Commit**

```bash
git add src/neuro_workflow/qa/report.py tests/qa/test_report_orchestrator.py tests/qa/fixtures/__init__.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): replace report.py with HTML cohort dashboard orchestrator

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Update CLI script

**Files:**
- Modify: `scripts/qa_report.py`

- [ ] **Step 12.1: Replace `scripts/qa_report.py` contents**

```python
#!/usr/bin/env python
"""Generate QA HTML cohort dashboard from fmriprep derivatives.

Usage:
    uv run python scripts/qa_report.py \\
        --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \\
        [--output-dir PATH] \\
        [--subjects sub-s03 sub-s10 ...] \\
        [--decisions PATH] \\
        [--no-reliability-movies] \\
        [--euler-n-sigma 2.0]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from neuro_workflow.qa.report import build_reports


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fmriprep-dir", required=True, type=Path,
                        help="fmriprep derivatives directory "
                             "(e.g. <bids>/derivatives/fmriprep_25.2.4)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory (default: <fmriprep-dir>/qa_html)")
    parser.add_argument("--subjects", nargs="+", default=None,
                        help="Restrict to these subjects (default: all)")
    parser.add_argument("--decisions", type=Path, default=None,
                        help="Path to qc_decisions.tsv (sidecar TSV with QC decisions)")
    parser.add_argument("--no-reliability-movies", action="store_true",
                        help="Skip brm reliability movie generation")
    parser.add_argument("--euler-n-sigma", type=float, default=2.0,
                        help="Cohort MAD multiplier for Euler outlier detection (default 2.0)")
    args = parser.parse_args()

    fmriprep_dir: Path = args.fmriprep_dir
    if not fmriprep_dir.is_dir():
        print(f"Error: fmriprep derivatives not found: {fmriprep_dir}", file=sys.stderr)
        return 1

    output_dir: Path = args.output_dir or (fmriprep_dir / "qa_html")

    build_reports(
        fmriprep_dir=fmriprep_dir,
        output_dir=output_dir,
        subjects=args.subjects,
        decisions_path=args.decisions,
        no_reliability_movies=args.no_reliability_movies,
        euler_n_sigma=args.euler_n_sigma,
    )
    print(f"Wrote QA HTML to {output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 12.2: Smoke-test the CLI on the fixture**

```bash
cd /home/users/logben/neuro_workflow
uv run python scripts/qa_report.py --help
```
Expected: argparse prints help text including all flags.

- [ ] **Step 12.3: Commit**

```bash
git add scripts/qa_report.py
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
feat(qa): update CLI for HTML cohort dashboard

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: End-to-end smoke test on real s03 derivatives

**Files:**
- Create (if not present): `config/manifests/qc_decisions.tsv`

This is an operational verification, not a unit test. Run the new CLI on the real s03 derivatives to confirm the full pipeline produces a valid HTML report.

- [ ] **Step 13.1: Stage a tiny decisions TSV (optional)**

```bash
mkdir -p /home/users/logben/neuro_workflow/config/manifests
cat > /home/users/logben/neuro_workflow/config/manifests/qc_decisions.tsv <<'EOF'
subject	session	task	run	action	reason
sub-s03	-	-	-	pass	test entry
EOF
```

- [ ] **Step 13.2: Run on real s03**

```bash
cd /home/users/logben/neuro_workflow
module load cairo ffmpeg 2>&1 | tail -2
export LD_LIBRARY_PATH="/share/software/user/open/cairo/1.14.10/lib:${LD_LIBRARY_PATH}"

uv run python scripts/qa_report.py \
  --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
  --output-dir /scratch/users/logben/qa_html_test \
  --subjects sub-s03 \
  --decisions config/manifests/qc_decisions.tsv \
  --no-reliability-movies   # skip brm for the smoke test; faster
```

Expected:
- Exit 0.
- Output: `Wrote QA HTML to /scratch/users/logben/qa_html_test`.

- [ ] **Step 13.3: Verify expected output structure**

```bash
ls /scratch/users/logben/qa_html_test/
ls /scratch/users/logben/qa_html_test/subjects/
```
Expected:
- `cohort.html`, `cohort.tsv`, `subjects/` dir, `movies/` dir.
- `subjects/sub-s03.html` exists.

- [ ] **Step 13.4: Spot-check cohort.html content**

```bash
grep -c "DataTable" /scratch/users/logben/qa_html_test/cohort.html
grep -c "sub-s03" /scratch/users/logben/qa_html_test/cohort.html
```
Expected: both ≥ 1.

- [ ] **Step 13.5: Spot-check sub-s03.html content**

```bash
grep -c "FreeSurfer" /scratch/users/logben/qa_html_test/subjects/sub-s03.html
grep -c "Euler" /scratch/users/logben/qa_html_test/subjects/sub-s03.html
grep -c "Reliability movie" /scratch/users/logben/qa_html_test/subjects/sub-s03.html
grep -c "<details" /scratch/users/logben/qa_html_test/subjects/sub-s03.html
```
Expected: all ≥ 1.

- [ ] **Step 13.6: Verify size sane**

```bash
du -sh /scratch/users/logben/qa_html_test/*
du -sh /scratch/users/logben/qa_html_test/subjects/sub-s03.html
```
Expected: cohort.html ~50–500 KB, subject HTML 5–15 MB (with embedded SVGs).

- [ ] **Step 13.7: Commit decisions TSV stub if used**

```bash
git add config/manifests/qc_decisions.tsv
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
docs(qa): add qc_decisions.tsv stub for QA report integration

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Cleanup — remove obsolete code paths

**Files:**
- Modify: `src/neuro_workflow/qa/__init__.py` (if it imports anything from old report.py that's gone)
- Verify: no callers depend on old `build_subject_report` / `build_cohort_summary` signatures

- [ ] **Step 14.1: Search for callers of old API**

```bash
cd /home/users/logben/neuro_workflow
grep -rn "build_subject_report\|build_cohort_summary\|write_suggested_exclusions\|QaReportQa" \
   src/ tests/ scripts/ 2>/dev/null
```
Expected: matches only inside the new report.py if any remain — there should be none. If matches found in other files, follow up to fix the callers.

- [ ] **Step 14.2: Confirm `qa/__init__.py` is clean**

```bash
cat /home/users/logben/neuro_workflow/src/neuro_workflow/qa/__init__.py
```
Expected: doesn't import any removed symbols. If it does, edit to drop them.

- [ ] **Step 14.3: Final test run**

```bash
uv run pytest tests/qa/ tests/scripts/ tests/pipelines/ -v
```
Expected: all green (no broken imports from old report.py callers).

- [ ] **Step 14.4: Commit if any cleanup required**

```bash
git add <whatever was changed>
git -c commit.gpgsign=false commit -m "$(cat <<'EOF'
chore(qa): remove obsolete report.py API exports

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Implemented in |
|---|---|
| Output layout (cohort.html + subjects/ + movies/) | Task 11 (build_reports), Task 13 (smoke test verification) |
| CLI flags (--fmriprep-dir, --output-dir, --subjects, --decisions, --no-reliability-movies, --euler-n-sigma) | Task 12 |
| Module structure (metrics/, decisions, cohort, reliability_movies, templates) | Tasks 2, 3, 4, 5, 6, 7, 9, 10 |
| Cohort table columns | Task 9 (cohort.html.j2) |
| Per-subject HTML structure | Task 10 (subject.html.j2) |
| Motion metrics | Task 2 |
| FreeSurfer metrics (Euler, holes, status, runtime, volumes) | Task 3 |
| Outputs check across spaces | Task 4 |
| Cohort outlier detection (MAD, n_sigma) | Task 5 |
| Decisions TSV loader | Task 6 |
| Reliability movies wrapper | Task 7 |
| Vendored DataTables | Task 8 |
| Error handling (missing FS, missing confounds, brm failures) | embedded across Tasks 3, 7, 11 |
| Tests (unit + integration) | Tasks 2-7, 9-11 |

**Placeholder scan:** No "TBD", "TODO", "implement later". Every step has actual code or actual commands.

**Type consistency:**
- `MotionMetrics` defined in Task 2; used in Tasks 11 (orchestrator) consistently.
- `FreeSurferMetrics` defined in Task 3; used in Tasks 5, 11 consistently.
- `OutputCheckResult` and `ScanID` defined in Task 4; used in Task 11.
- `ScanKey` and `Decision` defined in Task 6; used in Task 11.
- `MovieResult` defined in Task 7; used in Task 11.
- `render_cohort_html` and `render_subject_html` signatures match between Task 9 (definition) and Task 11 (call site).

---

## Notes for the engineer

- The repo uses `uv run` (Python 3.13). All shell snippets assume `cd /home/users/logben/neuro_workflow` first.
- Cluster modules required at runtime: `cairo` (for SVG inlining as text — actually we read svg files directly, so cairo is NOT needed for the new HTML report; only the old PDF report needed cairosvg) and `ffmpeg` (for brm).
- The new HTML report does NOT use cairosvg. SVGs are read as text and embedded as `<svg>...</svg>` directly in HTML — browsers render them natively. This is a meaningful simplification vs the old PDF approach.
- `bold-reliability-movies` is installed as a `uv tool` in this user's environment (Python 3.12 venv at `~/.local/share/uv/tools/bold-reliability-movies/`). For project tests we mock it; for production use we depend on it via the qa extras.
