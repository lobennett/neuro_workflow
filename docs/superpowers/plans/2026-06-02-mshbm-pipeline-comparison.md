# MSHBM Pipeline Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce three DU15NET MSHBM individual parcellations for sub-s10 — iProc (ME-tedana), fMRIPrep→XCP-D, and fMRIPrep+bandpass — all on FreeSurfer 7.3.2 surfaces, fsaverage6, full task+rest, 2mm-FWHM smoothing, an identical scan set, and identical MSHBM config; then quantify how much the functional-preprocessing pipeline alone changes the parcellation.

**Architecture:** Re-point iProc at fMRIPrep 25.2.4's FS 7.3.2 recon and re-run iProc surface stages into a separate `iproc_fs7` tree. Build per-arm MSHBM fsaverage6 inputs via three tested adapter modules in `src/neuro_workflow/analysis/mshbm/` (`from_iproc.py` extended, new `from_fmriprep.py`, existing `from_xcpd.py` reused). Restrict all arms to a common scan set, run MSHBM three times via the `~/network_glm/PrecisionNetworkMapping` clone, and compare with a new tested `compare.py` quality module.

**Tech stack:** Python 3.13 + `uv`, pytest (TDD), nibabel/numpy/scipy, FreeSurfer 7.3.2 + Connectome Workbench (`wb_command`), CBIG MSHBM (MATLAB), SLURM (Sherlock, `normal`/`russpold` partitions — never `owners`).

**Conventions:**
- All Python run via `uv run python` / `uv run pytest`.
- Module functions stay pure (numpy/path logic); `wb_command`/FreeSurfer orchestration lives in `scripts/` drivers (matches `from_iproc.py`/`from_xcpd.py`).
- Tests mirror `tests/analysis/mshbm/`.
- Commit after each green step.
- SLURM courtesy: cap concurrent footprint, prefer `normal`, never `owners`.

**Paths (constants used throughout):**
- iProc root: `/scratch/users/logben/discovery_bids/derivatives/iproc`
- iProc FS7 rerun tree: `/scratch/users/logben/discovery_bids/derivatives/iproc_fs7`
- fMRIPrep 25.2.4: `/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4`
- fMRIPrep FS 7.3.2 subject: `…/fmriprep_25.2.4/sourcedata/freesurfer/sub-s10_ses-09`
- XCP-D: `/scratch/users/logben/discovery_bids/derivatives/xcp_d_26.0.2`
- Existing XCP-D MSHBM inputs: `/scratch/users/logben/mshbm_inputs_discovery_xcpd/sub-s10`
- MSHBM codedir: `/home/users/logben/network_glm/PrecisionNetworkMapping`
- Comparison root: `/scratch/users/logben/mshbm_compare_s10`
- Arm input dirs: `/scratch/users/logben/mshbm_inputs_{iproc_fs7,fmriprep_bp}/sub-s10` (+ reused xcpd)
- Arm MSHBM outputs: `/scratch/users/logben/mshbm_output_{iproc_fs7,xcpd,fmriprep_bp}_s10`

---

## Phase 0 — iProc FreeSurfer-swap rerun (operational)

These tasks run existing tooling on SLURM; they are gated, not test-first.

### Task 0.1: Confirm XCP-D arm provenance (gate)

**Files:** none (verification).

- [ ] **Step 1: Confirm the existing XCP-D MSHBM inputs derive from fMRIPrep 25.2.4 / FS 7.3.2**

Run:
```bash
# dataset_description of the XCP-D that fed the inputs
cat /scratch/users/logben/discovery_bids/derivatives/xcp_d_26.0.2/dataset_description.json 2>/dev/null | grep -iE 'fmriprep|freesurfer|GeneratedBy|version' | head
# and confirm the inputs reference 25.2.4 / 12 sessions for s10
ls /scratch/users/logben/mshbm_inputs_discovery_xcpd/sub-s10/lh*fsaverage6_sm*.nii.gz | wc -l
```
Expected: XCP-D generated from fMRIPrep 25.2.4 (FS 7.3.2); ≥12 lh session files for s10.

- [ ] **Step 2: Record the decision**

If 25.2.4-derived → reuse `mshbm_inputs_discovery_xcpd/sub-s10` as the XCP-D arm (no rebuild). If not → flag for an XCP-D refresh (out of this plan's happy path; stop and consult). Write the finding to `/scratch/users/logben/mshbm_compare_s10/xcpd_provenance.txt`.

### Task 0.2: Ingest fMRIPrep FS 7.3.2 into iProc + conformed-space gate

**Files:**
- Create: `/scratch/users/logben/discovery_bids/derivatives/iproc_fs7/fs/s10/09_009` (FS subject for the rerun)
- Create: `scripts/iproc_ingest_fmriprep_fs.sh`

- [ ] **Step 1: Write the ingest script**

```bash
#!/bin/bash
# scripts/iproc_ingest_fmriprep_fs.sh — copy fMRIPrep FS 7.3.2 recon into the
# iproc_fs7 FS tree under iProc's session-id name (09_009), so iProc uses the
# better surfaces for bbregister + projection.
set -euo pipefail
SRC=/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s10_ses-09
DST=/scratch/users/logben/discovery_bids/derivatives/iproc_fs7/fs/s10/09_009
mkdir -p "$(dirname "$DST")"
cp -a "$SRC" "$DST"
# fsaverage6 symlink iProc expects alongside the subject
ln -sfn "$FREESURFER_HOME/subjects/fsaverage6" \
  /scratch/users/logben/discovery_bids/derivatives/iproc_fs7/fs/s10/fsaverage6
echo "ingested FS7.3.2 -> $DST"
```

- [ ] **Step 2: Run ingest (module load freesurfer first)**

Run:
```bash
module load biology freesurfer/8.1.0
bash scripts/iproc_ingest_fmriprep_fs.sh
```
Expected: `ingested FS7.3.2 -> …/iproc_fs7/fs/s10/09_009`.

- [ ] **Step 3: Conformed-space gate**

Run:
```bash
module load biology freesurfer/8.1.0
mri_info --cras --dim /scratch/users/logben/discovery_bids/derivatives/iproc_fs7/fs/s10/09_009/mri/orig.mgz
mri_info --cras --dim /scratch/users/logben/discovery_bids/derivatives/iproc/fs/s10/09_009/mri/orig.mgz
```
Expected: both report 256×256×256, 1mm, identical c_ras. (FreeSurfer conforms to a fixed space regardless of version — confirms iProc's `--regheader` projection will be geometrically valid against the swapped recon.) If they differ, STOP — the projection geometry assumption is broken.

### Task 0.3: Re-run iProc T1_warp → combine → tedana → filter into iproc_fs7

**Files:**
- Modify: iProc conf to point `SUBJECTS_DIR`/output at `iproc_fs7` (a copied conf, e.g. `/scratch/users/logben/iProc/configs/s10_fs7.conf`)
- Use: `scripts/iproc_scatter.py`, `scripts/iproc_tedana_scatter.py`

- [ ] **Step 1: Create the FS7 iProc config** — copy the working s10 conf, change `mri_data`/`fs` roots to the `iproc_fs7` tree, keep all other params identical. Verify with a diff that only the path roots changed.

- [ ] **Step 2: Run `T1_warp_and_mask` (bbregister against FS7.3.2)**

Run the iProc stage for s10 with the FS7 conf (single short job, `normal`):
```bash
cd /scratch/users/logben/iProc
sbatch --partition=normal --time=02:00:00 --mem=32G \
  --wrap="apptainer exec --bind /scratch,/oak container/iproc.sif \
  python iProc.py T1_warp_and_mask configs/s10_fs7.conf"
```
Expected: completes; new `bbregister` `.dat`/`.lta` under the iproc_fs7 tree.

- [ ] **Step 3: Run `combine_and_apply_warp` (scatter, throttled)**

Run via `iproc_scatter.py submit-rest --stage combine_and_apply_warp` against the FS7 scatter root (mirror the prior campaign's invocation), `--partition normal,russpold`, capped footprint. Verify all 57 scans produce MNI111 + NAT111 combined volumes.

- [ ] **Step 4: Run tedana (MNI + NAT) via `iproc_tedana_scatter.py`**

Run the 114-unit tedana stage against the iproc_fs7 combined outputs (MNI 160G/10h; NAT 240G), throttled. Gate: 114/114 `desc-denoised_bold.nii.gz` present.

- [ ] **Step 5: Run `filter_and_project` (scatter)**

Run `iproc_scatter.py submit-rest --stage filter_and_project` against the FS7 scatter root, `--partition russpold,normal`. (The done-detection glob fix `lh.*bpss_fsaverage6_sm*` is already in `iproc_scatter.py`.)

### Task 0.4: iProc-FS7 surface QC (gate)

**Files:** none (verification); writes `/scratch/users/logben/mshbm_compare_s10/iproc_fs7_qc.txt`.

- [ ] **Step 1: Re-measure SurfaceHoles + count outputs**

Run:
```bash
IPFS=/scratch/users/logben/discovery_bids/derivatives/iproc_fs7/fs/s10/09_009
grep -E 'SurfaceHoles,' "$IPFS/stats/aseg.stats"   # expect ~9 (matches fMRIPrep FS7.3.2)
ROOT=/scratch/users/logben/discovery_bids/derivatives/iproc_fs7/mri_data/s10/FS6
ls "$ROOT"/*/*/{lh,rh}.*fsaverage6*.nii.gz 2>/dev/null | wc -l   # expect 456 (57x8)
```
Expected: SurfaceHoles ≈ 9 (not 51); 456 surface files. Write results to the QC file. If holes are still ~51 or surfaces < 456, STOP.

---

## Phase 1 — MSHBM input builders (TDD)

### Task 1.1: Extend `from_iproc.py` discovery to all task+rest scans

**Files:**
- Modify: `src/neuro_workflow/analysis/mshbm/from_iproc.py`
- Test: `tests/analysis/mshbm/test_from_iproc.py`

- [ ] **Step 1: Write failing tests for a task+rest discovery function**

Add to `tests/analysis/mshbm/test_from_iproc.py`:
```python
def test_discover_iproc_scans_includes_task_and_rest(tmp_path):
    from neuro_workflow.analysis.mshbm.from_iproc import discover_iproc_scans
    fs6 = tmp_path / "mri_data" / "s10" / "FS6"
    # one rest, one task scan, both hemis
    specs = [("01", "REST_004", "004", "REST"),
             ("01", "FLANKER_009", "009", "FLANKER")]
    for ses, cell, run, _ in specs:
        d = fs6 / ses / cell
        d.mkdir(parents=True)
        for hemi in ("lh", "rh"):
            (d / f"{hemi}.{ses}_bld{run}_tedana_bpss_fsaverage6_sm0p0.nii.gz").touch()
    scans = discover_iproc_scans(tmp_path / "mri_data" / "s10")
    tasks = sorted(s.task for s in scans)
    assert tasks == ["FLANKER", "REST"]
    assert all(s.lh_path.name.startswith("lh") and s.rh_path.name.startswith("rh")
               for s in scans)

def test_make_mshbm_name_uses_task_label():
    from neuro_workflow.analysis.mshbm.from_iproc import make_mshbm_name
    # task label now flows into the name (was hardcoded task-rest)
    n = make_mshbm_name("lh", "01", "009", task="flanker")
    assert n == "lh_ses-01_task-flanker_run-009_nat_resid_bpss_fsaverage6_sm0.nii.gz"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/analysis/mshbm/test_from_iproc.py -k 'task_and_rest or task_label' -v`
Expected: FAIL (`discover_iproc_scans` not defined; `make_mshbm_name` has no `task` kwarg).

- [ ] **Step 3: Implement the generalization**

In `from_iproc.py`: (a) broaden the regex to capture the cell's task, (b) add `discover_iproc_scans`, (c) add an optional `task` arg to `make_mshbm_name` (default `"rest"` for back-compat). Replace the rest-only internals:

```python
# new regex: capture task token from the cell dir, run from filename
_IPROC_SURF_RE = re.compile(
    r"^(?P<hemi>lh|rh)\.(?P<ses>\d+)_bld(?P<run>\d+)_"
    r"tedana_bpss_fsaverage6_sm0p0\.nii\.gz$"
)

@dataclass(frozen=True)
class IprocScan:
    session: str
    run: str
    task: str          # e.g. "REST", "FLANKER"
    lh_path: Path
    rh_path: Path

def make_mshbm_name(hemi: str, session: str, run: str, task: str = "rest") -> str:
    if hemi not in HEMI_MAP:
        raise ValueError(f"Unexpected hemi {hemi!r}; expected 'lh' or 'rh'")
    return (f"{hemi}_ses-{session}_task-{task}_run-{run}"
            f"_nat_resid_bpss_fsaverage6_sm0.nii.gz")

def discover_iproc_scans(iproc_subject_root: Path) -> list["IprocScan"]:
    """All task+rest fsaverage6 scans under FS6/<ses>/<TASK>_<run>/."""
    fs6_root = Path(iproc_subject_root) / "FS6"
    pairs: dict[tuple[str, str, str], dict[str, Path]] = {}
    for hemi in ("lh", "rh"):
        for p in fs6_root.glob(f"*/*/{hemi}.*_tedana_bpss_fsaverage6_sm0p0.nii.gz"):
            m = _IPROC_SURF_RE.match(p.name)
            if not m:
                continue
            task = p.parent.name.rsplit("_", 1)[0]   # "FLANKER_009" -> "FLANKER"
            key = (m.group("ses"), m.group("run"), task)
            pairs.setdefault(key, {})[hemi] = p
    scans = []
    for (ses, run, task), h in sorted(pairs.items()):
        if "lh" in h and "rh" in h:
            scans.append(IprocScan(session=ses, run=run, task=task,
                                   lh_path=h["lh"], rh_path=h["rh"]))
    return scans
```
Keep the existing `discover_iproc_rest` as a thin wrapper (`[s for s in discover_iproc_scans(...) if s.task == "REST"]`) so old tests/callers still pass.

- [ ] **Step 4: Run the full module test file**

Run: `uv run pytest tests/analysis/mshbm/test_from_iproc.py -v`
Expected: all pass (new + existing 7).

- [ ] **Step 5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/from_iproc.py tests/analysis/mshbm/test_from_iproc.py
git commit -m "feat(mshbm): from_iproc discovers all task+rest scans (not just rest)"
```

### Task 1.2: Shared 2mm fsaverage6 surface-smoothing helper

**Files:**
- Create: `src/neuro_workflow/analysis/mshbm/surfsmooth.py`
- Test: `tests/analysis/mshbm/test_surfsmooth.py`

The smoothing itself is a `wb_command` call (lives in drivers), but the array⇄GIFTI marshalling is pure and testable.

- [ ] **Step 1: Write failing test for the array→func.gii→array round-trip helper**

```python
import numpy as np, nibabel as nib
from neuro_workflow.analysis.mshbm.surfsmooth import array_to_func_gii, func_gii_to_array

def test_func_gii_roundtrip(tmp_path):
    arr = np.random.default_rng(0).standard_normal((40962, 7)).astype(np.float32)
    p = tmp_path / "x.func.gii"
    array_to_func_gii(arr, p)
    back = func_gii_to_array(p)
    assert back.shape == (40962, 7)
    np.testing.assert_allclose(back, arr, rtol=1e-5)
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/analysis/mshbm/test_surfsmooth.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement marshalling helpers + the FWHM→sigma constant**

```python
"""fsaverage6 surface smoothing marshalling for MSHBM inputs.

Pure array<->GIFTI helpers; the actual wb_command -metric-smoothing call lives
in the driver scripts (per module/script split convention).
"""
from __future__ import annotations
from pathlib import Path
import nibabel as nib
import numpy as np

FWHM_2MM_SIGMA = 2.0 / 2.3548200450309493  # FWHM(mm) -> Gaussian sigma(mm)

def array_to_func_gii(arr: np.ndarray, out_path: Path) -> Path:
    """Write (V, T) float32 as a .func.gii (one DataArray per column)."""
    arr = np.asarray(arr, dtype=np.float32)
    darrays = [nib.gifti.GiftiDataArray(arr[:, t].copy(),
               intent="NIFTI_INTENT_TIME_SERIES") for t in range(arr.shape[1])]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.gifti.GiftiImage(darrays=darrays), str(out_path))
    return out_path

def func_gii_to_array(path: Path) -> np.ndarray:
    """Load a .func.gii to (V, T) float32."""
    g = nib.load(str(path))
    return np.stack([d.data.astype(np.float32) for d in g.darrays], axis=-1)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/analysis/mshbm/test_surfsmooth.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/surfsmooth.py tests/analysis/mshbm/test_surfsmooth.py
git commit -m "feat(mshbm): surfsmooth array<->func.gii marshalling helpers"
```

### Task 1.3: `from_fmriprep.py` — discovery + naming (TDD)

**Files:**
- Create: `src/neuro_workflow/analysis/mshbm/from_fmriprep.py`
- Test: `tests/analysis/mshbm/test_from_fmriprep.py`

- [ ] **Step 1: Write failing tests for discovery + naming**

```python
from neuro_workflow.analysis.mshbm.from_fmriprep import (
    discover_fmriprep_scans, make_mshbm_name,
)

def test_make_mshbm_name():
    assert make_mshbm_name("lh", "01", "1", "flanker") == \
        "lh_ses-01_task-flanker_run-1_nat_resid_bpss_fsaverage6_sm0.nii.gz"

def test_discover_pairs_hemis_and_finds_confounds(tmp_path):
    func = tmp_path / "sub-s10" / "ses-01" / "func"
    func.mkdir(parents=True)
    base = "sub-s10_ses-01_task-flanker_run-1"
    for hemi in ("L", "R"):
        (func / f"{base}_hemi-{hemi}_space-fsaverage6_bold.func.gii").touch()
    (func / f"{base}_desc-confounds_timeseries.tsv").touch()
    (func / f"{base}_hemi-L_space-fsaverage6_bold.json").write_text('{"RepetitionTime":1.49}')
    scans = discover_fmriprep_scans(tmp_path, "s10")
    assert len(scans) == 1
    s = scans[0]
    assert (s.session, s.task, s.run) == ("01", "flanker", "1")
    assert s.confounds_tsv.name.endswith("_desc-confounds_timeseries.tsv")
    assert s.tr == 1.49
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/analysis/mshbm/test_from_fmriprep.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement discovery + naming**

```python
"""Build MSHBM fsaverage6 inputs from fMRIPrep surface BOLD + mshbm.preproc.

Arm 3 of the pipeline comparison: fMRIPrep's own fsaverage6 GIFTIs (FS 7.3.2)
denoised with the lab's mshbm.preproc (confound regression + bandpass) and 2mm
smoothing — no XCP-D. Pure discovery/naming here; wb_command + heavy array work
in scripts/mshbm_inputs_from_fmriprep.py.
"""
from __future__ import annotations
import json, re
from dataclasses import dataclass
from pathlib import Path

HEMI_MAP = {"lh": "lh", "rh": "rh"}
_BOLD_RE = re.compile(
    r"^sub-(?P<sub>[A-Za-z0-9]+)_ses-(?P<ses>[A-Za-z0-9]+)_"
    r"task-(?P<task>[A-Za-z0-9]+)(?:_run-(?P<run>[A-Za-z0-9]+))?"
    r"_hemi-L_space-fsaverage6_bold\.func\.gii$"
)

@dataclass(frozen=True)
class FmriprepScan:
    session: str
    task: str
    run: str
    lh_path: Path
    rh_path: Path
    confounds_tsv: Path
    tr: float

def make_mshbm_name(hemi: str, session: str, run: str, task: str) -> str:
    if hemi not in HEMI_MAP:
        raise ValueError(f"bad hemi {hemi!r}")
    return (f"{hemi}_ses-{session}_task-{task}_run-{run}"
            f"_nat_resid_bpss_fsaverage6_sm0.nii.gz")

def discover_fmriprep_scans(fmriprep_dir: Path, subject: str) -> list[FmriprepScan]:
    subj = subject if subject.startswith("sub-") else f"sub-{subject}"
    out: list[FmriprepScan] = []
    for lh in sorted((fmriprep_dir / subj).glob(
            "ses-*/func/*_hemi-L_space-fsaverage6_bold.func.gii")):
        m = _BOLD_RE.match(lh.name)
        if not m:
            continue
        rh = Path(str(lh).replace("hemi-L", "hemi-R"))
        if not rh.exists():
            continue
        run = m.group("run") or "1"
        prefix = lh.name.split("_hemi-L_")[0]
        conf = lh.parent / f"{prefix}_desc-confounds_timeseries.tsv"
        js = lh.with_suffix("").with_suffix(".json")  # *_bold.json
        tr = float(json.loads(js.read_text())["RepetitionTime"]) if js.exists() else float("nan")
        out.append(FmriprepScan(m.group("ses"), m.group("task"), run,
                                lh, rh, conf, tr))
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/analysis/mshbm/test_from_fmriprep.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/from_fmriprep.py tests/analysis/mshbm/test_from_fmriprep.py
git commit -m "feat(mshbm): from_fmriprep discovery + naming"
```

### Task 1.4: `from_fmriprep.py` — preproc composition (TDD)

**Files:**
- Modify: `src/neuro_workflow/analysis/mshbm/from_fmriprep.py`
- Test: `tests/analysis/mshbm/test_from_fmriprep.py`

- [ ] **Step 1: Write a failing test for the denoise composition**

```python
import numpy as np, pandas as pd
from neuro_workflow.analysis.mshbm.from_fmriprep import denoise_timeseries

def test_denoise_runs_regress_then_bandpass():
    rng = np.random.default_rng(0)
    V, T = 50, 120
    Y = rng.standard_normal((V, T)).astype(np.float32)
    # minimal du2025 confound columns
    base = ["trans_x","trans_y","trans_z","rot_x","rot_y","rot_z",
            "global_signal","csf","white_matter"]
    cols = base + [c+"_derivative1" for c in base]
    conf = pd.DataFrame(rng.standard_normal((T, len(cols))), columns=cols)
    out = denoise_timeseries(Y, conf, tr=1.49)
    assert out.shape == (V, T)
    assert np.isfinite(out).all()
    # bandpass removes the DC: each vertex near zero-mean
    assert np.allclose(out.mean(axis=1), 0, atol=1e-3)
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/analysis/mshbm/test_from_fmriprep.py -k denoise -v`
Expected: FAIL (`denoise_timeseries` not defined).

- [ ] **Step 3: Implement the composition (regress → bandpass)**

Add to `from_fmriprep.py`:
```python
import numpy as np, pandas as pd
from neuro_workflow.analysis.mshbm.preproc import (
    regress_confounds, bandpass_filter, build_regressor_matrix_du2025,
)

def denoise_timeseries(Y: np.ndarray, confounds_df: pd.DataFrame, tr: float,
                       lowcut: float = 0.009, highcut: float = 0.08) -> np.ndarray:
    """Regress du2025 nuisance set then bandpass. Y is (V, T)."""
    X = build_regressor_matrix_du2025(confounds_df)   # (T, 18)
    Y = regress_confounds(Y, X)                        # adds intercept+detrend
    Y = bandpass_filter(Y, tr=tr, lowcut=lowcut, highcut=highcut)
    return np.nan_to_num(Y, nan=0.0).astype(np.float32)
```
(Note: `build_regressor_matrix_du2025` matches the lab/Du MSHBM convention; GSR included. This is the documented arm choice.)

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/analysis/mshbm/test_from_fmriprep.py -k denoise -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/from_fmriprep.py tests/analysis/mshbm/test_from_fmriprep.py
git commit -m "feat(mshbm): from_fmriprep denoise (du2025 regress + bandpass)"
```

### Task 1.5: Driver scripts (operational, smoke-tested)

**Files:**
- Modify: `scripts/mshbm_inputs_from_iproc.py` (add `--smooth-fwhm 2` path)
- Create: `scripts/mshbm_inputs_from_fmriprep.py`

- [ ] **Step 1: Add 2mm smoothing to the iProc driver**

In `scripts/mshbm_inputs_from_iproc.py`: after `iproc_surf_to_mshbm_nifti` produces the canonical `(V,1,1,T)` array, when `--smooth-fwhm 2` is set, (a) `array_to_func_gii`, (b) `wb_command -metric-smoothing <fsaverage6_midthickness_hemi> <in.func.gii> <FWHM_2MM_SIGMA> <out.func.gii>`, (c) `func_gii_to_array`, (d) reshape to `(V,1,1,T)` and save. Reuse `templateflow_paths()` + `_ensure_midthickness()` from `from_xcpd`/its driver for the midthickness surfaces. Use `discover_iproc_scans` (all task+rest) and `make_mshbm_name(..., task=scan.task.lower())`.

- [ ] **Step 2: Write the fMRIPrep driver**

`scripts/mshbm_inputs_from_fmriprep.py`: for each `FmriprepScan` and hemi — load `func.gii` → `(V,T)`; read confounds tsv (`pd.read_csv(sep="\t")`); `denoise_timeseries(Y, conf, tr=scan.tr)`; `array_to_func_gii`; `wb_command -metric-smoothing` (2mm, fsaverage6 midthickness); `func_gii_to_array`; reshape to `(V,1,1,T)`; save to `<output>/sub-s10/<make_mshbm_name>`. Mirror the CLI/logging style of `mshbm_inputs_from_iproc.py`.

- [ ] **Step 3: Smoke-test the fMRIPrep driver on ONE scan**

Run (FS/workbench modules loaded):
```bash
module load biology freesurfer/8.1.0 workbench 2>/dev/null
uv run python scripts/mshbm_inputs_from_fmriprep.py \
  --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
  --subject s10 --output-dir /scratch/users/logben/mshbm_inputs_fmriprep_bp \
  --only ses-01_task-flanker_run-1 --verbose
```
Expected: 2 files written, shape `(40962,1,1,T)`, finite. (Add a `--only <prefix>` filter for the smoke test.)

- [ ] **Step 4: Commit**

```bash
git add scripts/mshbm_inputs_from_iproc.py scripts/mshbm_inputs_from_fmriprep.py
git commit -m "feat(mshbm): task+rest+2mm iproc driver; fmriprep-bandpass input driver"
```

---

## Phase 2 — Common scan set + MSHBM runs

### Task 2.1: Common-scan-set intersection module (TDD)

**Files:**
- Create: `src/neuro_workflow/analysis/mshbm/scanset.py`
- Test: `tests/analysis/mshbm/test_scanset.py`

- [ ] **Step 1: Write failing test**

```python
from neuro_workflow.analysis.mshbm.scanset import common_scan_set

def test_common_scan_set_intersects_and_reports_dropped():
    iproc = {("01","rest","004"), ("01","flanker","009"), ("02","rest","004")}
    xcpd  = {("01","rest","004"), ("01","flanker","009")}
    fbp   = {("01","rest","004"), ("01","flanker","009"), ("02","rest","004")}
    common, dropped = common_scan_set({"iproc": iproc, "xcpd": xcpd, "fbp": fbp})
    assert common == {("01","rest","004"), ("01","flanker","009")}
    assert dropped == {"xcpd": set(), "iproc": {("02","rest","004")},
                       "fbp": {("02","rest","004")}}
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/analysis/mshbm/test_scanset.py -v` → FAIL.

- [ ] **Step 3: Implement**

```python
"""Common-scan-set intersection across MSHBM arms.

A (session, task, run) cell enters MSHBM only if present in EVERY arm, so all
arms feed byte-identical data. Cells dropped by any arm are reported per-arm.
"""
from __future__ import annotations

Cell = tuple[str, str, str]   # (session, task, run)

def common_scan_set(arm_cells: dict[str, set[Cell]]):
    common = set.intersection(*arm_cells.values()) if arm_cells else set()
    dropped = {arm: (cells - common) for arm, cells in arm_cells.items()}
    return common, dropped
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/analysis/mshbm/test_scanset.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/scanset.py tests/analysis/mshbm/test_scanset.py
git commit -m "feat(mshbm): common-scan-set intersection across arms"
```

### Task 2.2: Build all three arms' inputs + apply common scan set (operational)

**Files:** writes arm input dirs + `…/mshbm_compare_s10/scanset_manifest.tsv`.

- [ ] **Step 1: Build iProc-FS7 inputs (task+rest, 2mm)**

```bash
module load biology freesurfer/8.1.0 workbench 2>/dev/null
uv run python scripts/mshbm_inputs_from_iproc.py \
  --iproc-dir /scratch/users/logben/discovery_bids/derivatives/iproc_fs7 \
  --subject s10 --smooth-fwhm 2 \
  --output-dir /scratch/users/logben/mshbm_inputs_iproc_fs7
```
Expected: ~57×2 files for sub-s10.

- [ ] **Step 2: Build fMRIPrep+bandpass inputs (all task+rest)**

Run the fMRIPrep driver (Task 1.5 Step 3 command without `--only`). Expected: one pair per fMRIPrep task+rest scan.

- [ ] **Step 3: Compute the common scan set + write manifest**

Write a small one-off (`scripts/mshbm_build_scanset.py`) that globs each arm's `sub-s10/lh*` files, parses `(ses,task,run)`, calls `common_scan_set`, writes `scanset_manifest.tsv` (columns: ses, task, run, in_iproc, in_xcpd, in_fbp, in_common), and **deletes/excludes** non-common files from each arm's input dir (or copies common-only into `…_common/` subdirs). Gate: print the common count and per-arm dropped counts; STOP if common count is implausibly low (< 10 sessions).

- [ ] **Step 4: Commit the manifest + helper**

```bash
git add scripts/mshbm_build_scanset.py
git commit -m "feat(mshbm): build common scan set + manifest across arms"
cp /scratch/users/logben/mshbm_compare_s10/scanset_manifest.tsv docs/  # provenance copy (optional)
```

### Task 2.3: Run MSHBM for all three arms + per-arm QC (operational, gated)

**Files:** writes the three `mshbm_output_*_s10` trees.

- [ ] **Step 1: Launch each arm**

For each arm dir, build a one-row CSV (`sub-s10,<inputs_parent>/`) and launch:
```bash
CODEDIR=/home/users/logben/network_glm/PrecisionNetworkMapping
for arm in iproc_fs7 fmriprep_bp; do
  OUT=/scratch/users/logben/mshbm_output_${arm}_s10; mkdir -p "$OUT"
  printf 'sub-s10,/scratch/users/logben/mshbm_inputs_%s/\n' "$arm" > "$OUT/sub_list.csv"
  MSHBM_GROUP_BY_SESSION=1 bash "$CODEDIR/MSHBM/run_MSHBM.sh" "$OUT/sub_list.csv" "$OUT" "$CODEDIR"
done
# XCP-D arm: reuse existing inputs
OUT=/scratch/users/logben/mshbm_output_xcpd_s10; mkdir -p "$OUT"
printf 'sub-s10,/scratch/users/logben/mshbm_inputs_discovery_xcpd/\n' > "$OUT/sub_list.csv"
MSHBM_GROUP_BY_SESSION=1 bash "$CODEDIR/MSHBM/run_MSHBM.sh" "$OUT/sub_list.csv" "$OUT" "$CODEDIR"
```
(Each `Prep` auto-submits `Training`. Watch for the MATLAB error-swallow: grep each Prep `.err` for `Error`/`Undefined` before trusting the chained Training — cancel a stray Training if Prep errored.)

- [ ] **Step 2: Per-arm parcellation QC gate**

For each arm, load `…/ind_parcellation/sub-s10/sub-s10_MSHBM_{lh,rh}.label.gii` and assert: 15 networks present both hemis; largest-network share < ~25%; medial wall = 0. Write to `…/mshbm_compare_s10/parcellation_qc.tsv`. STOP on any degenerate arm.

---

## Phase 3 — Quality comparison module (TDD)

### Task 3.1: `compare.py` — cross-arm agreement + Dice (TDD)

**Files:**
- Create: `src/neuro_workflow/analysis/mshbm/compare.py`
- Test: `tests/analysis/mshbm/test_compare.py`

- [ ] **Step 1: Write failing tests**

```python
import numpy as np
from neuro_workflow.analysis.mshbm.compare import vertex_agreement, dice_per_network

def test_vertex_agreement_ignores_medial_wall():
    a = np.array([0,1,1,2,3]); b = np.array([0,1,2,2,3])
    # cortex = labels>0 in both -> indices 1,2,3,4; matches at 1,3,4 -> 3/4
    assert abs(vertex_agreement(a, b) - 0.75) < 1e-9

def test_dice_per_network():
    a = np.array([1,1,2,2]); b = np.array([1,2,2,2])
    d = dice_per_network(a, b, n_networks=2)
    assert abs(d[0] - (2*1)/(2+1)) < 1e-9   # net1: inter1, |A|2 |B|1
    assert abs(d[1] - (2*2)/(2+3)) < 1e-9   # net2: inter2, |A|2 |B|3
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/analysis/mshbm/test_compare.py -v` → FAIL.

- [ ] **Step 3: Implement**

```python
"""Quality + agreement metrics for MSHBM parcellation arms.

Network labels are aligned across arms by the shared DU15NET prior, so
vertex-wise agreement and per-network Dice are meaningful.
"""
from __future__ import annotations
import numpy as np

def vertex_agreement(a: np.ndarray, b: np.ndarray) -> float:
    """% of vertices labeled (>0) in BOTH that share the same label."""
    both = (a > 0) & (b > 0)
    return float(np.mean(a[both] == b[both])) if both.any() else float("nan")

def dice_per_network(a: np.ndarray, b: np.ndarray, n_networks: int = 15) -> np.ndarray:
    out = np.full(n_networks, np.nan)
    for n in range(1, n_networks + 1):
        A = a == n; B = b == n
        s = A.sum() + B.sum()
        if s:
            out[n-1] = 2 * np.sum(A & B) / s
    return out
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/compare.py tests/analysis/mshbm/test_compare.py
git commit -m "feat(mshbm): compare.py cross-arm agreement + Dice"
```

### Task 3.2: `compare.py` — within-parcel functional homogeneity (TDD)

**Files:** Modify `compare.py`; Test `tests/analysis/mshbm/test_compare.py`.

- [ ] **Step 1: Write failing test**

```python
import numpy as np
from neuro_workflow.analysis.mshbm.compare import parcel_homogeneity

def test_parcel_homogeneity_perfect_when_identical_ts():
    # 2 parcels; within each, all vertices share an identical timeseries -> homog 1
    ts = np.zeros((6, 50)); rng = np.random.default_rng(0)
    a = rng.standard_normal(50); b = rng.standard_normal(50)
    ts[:3] = a; ts[3:] = b
    labels = np.array([1,1,1,2,2,2])
    h = parcel_homogeneity(ts, labels)
    assert abs(h - 1.0) < 1e-6
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement**

```python
def parcel_homogeneity(ts: np.ndarray, labels: np.ndarray) -> float:
    """Mean within-parcel functional homogeneity.

    For each parcel: correlate every vertex's timeseries with the parcel-mean
    timeseries, average those correlations; then average across parcels weighted
    by parcel size. ts is (V, T) on the SAME vertices as `labels` (V,).
    """
    vals, weights = [], []
    for n in np.unique(labels[labels > 0]):
        idx = np.where(labels == n)[0]
        if idx.size < 2:
            continue
        P = ts[idx]                      # (p, T)
        P = P - P.mean(axis=1, keepdims=True)
        mean_ts = P.mean(axis=0)
        mean_ts = mean_ts - mean_ts.mean()
        denom = (np.linalg.norm(P, axis=1) * np.linalg.norm(mean_ts))
        denom[denom == 0] = np.nan
        r = (P @ mean_ts) / denom
        vals.append(np.nanmean(r)); weights.append(idx.size)
    if not vals:
        return float("nan")
    return float(np.average(vals, weights=weights))
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/compare.py tests/analysis/mshbm/test_compare.py
git commit -m "feat(mshbm): within-parcel functional homogeneity metric"
```

### Task 3.3: `compare.py` — input tSNR (TDD)

**Files:** Modify `compare.py`; Test `tests/analysis/mshbm/test_compare.py`.

- [ ] **Step 1: Write failing test**

```python
import numpy as np
from neuro_workflow.analysis.mshbm.compare import temporal_snr

def test_temporal_snr():
    ts = np.ones((4, 100)) * 5.0
    ts[:, ::2] += 1.0   # mean 5.5, std 0.5 -> tSNR 11
    out = temporal_snr(ts)
    assert out.shape == (4,)
    assert np.allclose(out, 11.0, atol=0.2)
```

- [ ] **Step 2: Run to verify fail** — FAIL.

- [ ] **Step 3: Implement**

```python
def temporal_snr(ts: np.ndarray) -> np.ndarray:
    """Per-vertex tSNR = mean/std over time. (V, T) -> (V,)."""
    mu = ts.mean(axis=1)
    sd = ts.std(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(sd > 0, mu / sd, 0.0)
    return out.astype(np.float64)
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: Commit**

```bash
git add src/neuro_workflow/analysis/mshbm/compare.py tests/analysis/mshbm/test_compare.py
git commit -m "feat(mshbm): per-vertex tSNR metric"
```

### Task 3.4: Comparison report driver (operational/visual)

**Files:**
- Create: `scripts/mshbm_compare_arms.py`
- Output: `…/mshbm_compare_s10/{metrics.tsv, parcellation_compare.png, homogeneity_dice.png}`

- [ ] **Step 1: Write the report driver**

`scripts/mshbm_compare_arms.py` loads the four label sets (iProc-FS6 baseline, iProc-FS7, XCP-D, fMRIPrep+bandpass), and for every arm pair computes `vertex_agreement` + mean/per-network `dice_per_network`; for each arm computes `parcel_homogeneity` (on that arm's concatenated common-scanset input surfaces) + mean `temporal_snr`; writes `metrics.tsv`; renders the 4-row surface figure (reuse the nilearn `plot_surf_roi` + `tab20`-derived 15-color map from this session's `sub-s10_parcellation_compare.png`) and a homogeneity/Dice bar chart.

- [ ] **Step 2: Run it**

```bash
uv run python scripts/mshbm_compare_arms.py --subject s10 \
  --out-dir /scratch/users/logben/mshbm_compare_s10
```
Expected: `metrics.tsv` with one row per arm/arm-pair; two PNGs written.

- [ ] **Step 3: Sanity-read the metrics** — confirm homogeneity values are in [0,1], Dice in [0,1], tSNR positive; the iProc-FS7 vs iProc-FS6 Dice quantifies the FS-swap effect, and arm homogeneities answer "which pipeline yields the more functionally coherent parcellation."

- [ ] **Step 4: Commit**

```bash
git add scripts/mshbm_compare_arms.py
git commit -m "feat(mshbm): 3-arm comparison report (metrics + figures)"
```

### Task 3.5: Full module test sweep + final commit

- [ ] **Step 1: Run the whole mshbm test suite**

Run: `uv run pytest tests/analysis/mshbm/ -v`
Expected: all green (from_iproc, from_fmriprep, surfsmooth, scanset, compare).

- [ ] **Step 2: Commit any fixups + update memory pointer** — record completion in the project memory (`mshbm_iproc_s10.md` / a new comparison memory) with the metrics summary.

---

## Verification gates (summary — STOP if any fails)

1. **Task 0.1** — XCP-D arm confirmed fMRIPrep-25.2.4-derived (else refresh out of scope).
2. **Task 0.2 Step 3** — iProc FS7 conformed space matches FS6 (256³/1mm/c_ras).
3. **Task 0.4** — iProc-FS7 SurfaceHoles ≈ 9 (not 51) + 456 surfaces.
4. **Task 2.2 Step 3** — common scan set count plausible (≥10 sessions).
5. **Task 2.3 Step 2** — each arm's parcellation non-degenerate (15 nets, balanced).

## Cohort extension (post-pilot)

Once s10 validates: loop the `--subject` parameter across the discovery (then validation) subjects for Tasks 0.2–2.3 and the comparison. No new components; the iProc FS-swap rerun is the per-subject cost driver and should reuse `iproc_scatter.py` throttling.

## Out of scope (from spec)

GLM task residuals; new nuisance models; re-running fMRIPrep/XCP-D from scratch; non-15-network resolutions.
