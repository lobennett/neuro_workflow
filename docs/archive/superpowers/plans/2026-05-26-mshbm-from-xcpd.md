# MSHBM From XCP-D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a prep pipeline that converts XCP-D 26.0.2 `desc-denoised` CIFTI outputs (fsLR_den-91k, unsmoothed) into fsaverage6 NIfTI inputs for the existing MSHBM training wrapper. Replaces the lev1-task-residual + Du2025-postproc pipeline.

**Architecture:** Single Python driver script + a small testable helper module. Each (subject × session × task × hemi) cell is processed by a short subprocess chain: `wb_command -cifti-separate` → `-metric-resample` → `-metric-smoothing` → Python wrap as (V, 1, 1, T) NIfTI. SLURM array per-subject. MSHBM training infrastructure reused unchanged.

**Tech Stack:** Python 3, `wb_command` (Connectome Workbench module), templateflow spheres + pial/white surfaces, nibabel, numpy, SLURM.

**Reference spec:** `docs/superpowers/specs/2026-05-26-mshbm-from-xcpd-design.md`

---

## Pre-flight notes

**Source data**:
- Discovery: `/scratch/users/logben/discovery_bids/derivatives/xcp_d_26.0.2/sub-{s03,s10,s19,s29,s43}/` (verified complete)
- Validation: `/scratch/users/logben/validation_bids/derivatives/xcp_d_26.0.2/sub-{41 subjects}/` (verified complete)

**Templateflow paths** (already cached at `~/.cache/templateflow/`):
- `tpl-fsLR/tpl-fsLR_space-fsaverage_hemi-{L,R}_den-32k_sphere.surf.gii`
- `tpl-fsaverage/tpl-fsaverage_hemi-{L,R}_den-41k_sphere.surf.gii`
- `tpl-fsaverage/tpl-fsaverage_hemi-{L,R}_den-41k_pial.surf.gii`
- `tpl-fsaverage/tpl-fsaverage_hemi-{L,R}_den-41k_white.surf.gii`

**Output directories** (will be created):
- `/scratch/users/logben/mshbm_inputs_discovery_xcpd/`
- `/scratch/users/logben/mshbm_inputs_validation_xcpd/`
- `/scratch/users/logben/mshbm_inputs_pooled_xcpd/` (symlinks pointing into the two above)
- `/scratch/users/logben/mshbm_training_discovery_xcpd/`
- `/scratch/users/logben/mshbm_training_pooled_xcpd/`

**Module loads on compute nodes**: `module load workbench/1.5.0` (precedent in `xcpd.sbatch`).

---

### Task 1: Scaffold helper module + test file

**Files:**
- Create: `src/neuro_workflow/analysis/mshbm/from_xcpd.py`
- Create: `tests/analysis/mshbm/test_from_xcpd.py`

- [ ] **Step 1.1: Write failing import test**

Create `tests/analysis/mshbm/test_from_xcpd.py`:

```python
"""Tests for the XCP-D → MSHBM prep helpers."""
from __future__ import annotations


def test_module_imports():
    """Smoke import — verifies the package layout is sane."""
    from neuro_workflow.analysis.mshbm import from_xcpd  # noqa: F401
```

- [ ] **Step 1.2: Run the test to verify it fails**

```bash
uv run pytest tests/analysis/mshbm/test_from_xcpd.py -v
```
Expected: FAILS with `ModuleNotFoundError: No module named 'neuro_workflow.analysis.mshbm.from_xcpd'`.

- [ ] **Step 1.3: Create the skeleton module**

`src/neuro_workflow/analysis/mshbm/from_xcpd.py`:

```python
"""Helpers for converting XCP-D denoised CIFTI outputs into MSHBM fsaverage6 NIfTIs.

Pure-Python utilities — wb_command orchestration lives in
``scripts/mshbm_from_xcpd.py`` to keep this module easy to test.
"""
from __future__ import annotations

from pathlib import Path
```

- [ ] **Step 1.4: Re-run the test — expect PASS**

```bash
uv run pytest tests/analysis/mshbm/test_from_xcpd.py -v
```
Expected: 1 passed.

- [ ] **Step 1.5: Commit**

```bash
git add tests/analysis/mshbm/test_from_xcpd.py src/neuro_workflow/analysis/mshbm/from_xcpd.py
git commit -m "$(cat <<'EOF'
test(mshbm): scaffold from_xcpd helpers + import smoke test

Empty module + import test for the upcoming XCP-D → MSHBM prep
helpers. Pure-Python utilities (file discovery, gifti↔nifti wrapper,
sphere path resolution) will live here; wb_command orchestration
stays in scripts/mshbm_from_xcpd.py.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: TDD `discover_xcpd_cells` helper

**Files:**
- Modify: `tests/analysis/mshbm/test_from_xcpd.py`
- Modify: `src/neuro_workflow/analysis/mshbm/from_xcpd.py`

- [ ] **Step 2.1: Write failing test**

Append to `tests/analysis/mshbm/test_from_xcpd.py`:

```python
from pathlib import Path


def test_discover_xcpd_cells_returns_per_task_concatenated(tmp_path):
    """One Cell per (session × task) for `desc-denoised` files
    WITHOUT a `_run-N` token (the combine-runs concatenated variant)."""
    from neuro_workflow.analysis.mshbm.from_xcpd import discover_xcpd_cells, Cell

    sub_root = tmp_path / 'sub-s10'
    (sub_root / 'ses-01' / 'func').mkdir(parents=True)
    (sub_root / 'ses-02' / 'func').mkdir(parents=True)

    # Cells we want — no _run-N
    keep = [
        'ses-01/func/sub-s10_ses-01_task-rest_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
        'ses-01/func/sub-s10_ses-01_task-flanker_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
        'ses-02/func/sub-s10_ses-02_task-rest_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
    ]
    # Cells we want to skip — per-run variants
    skip = [
        'ses-01/func/sub-s10_ses-01_task-rest_run-1_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
        'ses-01/func/sub-s10_ses-01_task-flanker_run-1_space-fsLR_den-91k_desc-denoised_bold.dtseries.nii',
    ]
    for rel in keep + skip:
        (sub_root / rel).touch()

    cells = discover_xcpd_cells(sub_root)
    assert len(cells) == 3
    assert all(isinstance(c, Cell) for c in cells)
    assert {(c.session, c.task) for c in cells} == {
        ('ses-01', 'rest'),
        ('ses-01', 'flanker'),
        ('ses-02', 'rest'),
    }


def test_discover_xcpd_cells_empty_root_returns_empty_list(tmp_path):
    from neuro_workflow.analysis.mshbm.from_xcpd import discover_xcpd_cells
    assert discover_xcpd_cells(tmp_path) == []
```

- [ ] **Step 2.2: Run test — verify failure**

```bash
uv run pytest tests/analysis/mshbm/test_from_xcpd.py -v
```
Expected: 2 failures — `discover_xcpd_cells` and `Cell` not defined.

- [ ] **Step 2.3: Implement**

Add to `src/neuro_workflow/analysis/mshbm/from_xcpd.py`:

```python
import re
from dataclasses import dataclass


_CELL_RE = re.compile(
    r'^sub-(?P<sub>[A-Za-z0-9]+)_'
    r'(?P<ses>ses-[A-Za-z0-9]+)_'
    r'task-(?P<task>[A-Za-z0-9]+)_'
    r'space-fsLR_den-91k_desc-denoised_bold\.dtseries\.nii$'
)


@dataclass(frozen=True)
class Cell:
    """One (session, task) cell for one subject."""
    session: str
    task: str
    dtseries: Path


def discover_xcpd_cells(subject_root: Path) -> list[Cell]:
    """Find all `desc-denoised` CIFTIs for a subject, per-task concatenated only.

    Skips per-run variants (filenames containing `_run-N_`) — XCP-D was run
    with --combine-runs, so the no-run-suffix file is the concatenation.
    """
    cells: list[Cell] = []
    for path in sorted(Path(subject_root).rglob('*_desc-denoised_bold.dtseries.nii')):
        m = _CELL_RE.match(path.name)
        if not m:
            continue
        cells.append(Cell(session=m.group('ses'), task=m.group('task'), dtseries=path))
    return cells
```

- [ ] **Step 2.4: Run test — verify pass**

```bash
uv run pytest tests/analysis/mshbm/test_from_xcpd.py -v
```
Expected: 3 passed.

- [ ] **Step 2.5: Commit**

```bash
git add tests/analysis/mshbm/test_from_xcpd.py src/neuro_workflow/analysis/mshbm/from_xcpd.py
git commit -m "$(cat <<'EOF'
feat(mshbm): discover_xcpd_cells helper

Enumerates per-(session, task) XCP-D `desc-denoised_bold.dtseries.nii`
files for one subject, skipping per-run variants since XCP-D was run
with --combine-runs and the no-run-suffix file is the concatenated form
that MSHBM should consume.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: TDD `gifti_to_mshbm_nifti` wrapper

**Files:**
- Modify: `tests/analysis/mshbm/test_from_xcpd.py`
- Modify: `src/neuro_workflow/analysis/mshbm/from_xcpd.py`

- [ ] **Step 3.1: Write failing test**

Append to `tests/analysis/mshbm/test_from_xcpd.py`:

```python
import nibabel as nib
import numpy as np


def test_gifti_to_mshbm_nifti_shape_and_dtype(tmp_path):
    """A (V, T) GIFTI → (V, 1, 1, T) float32 NIfTI."""
    from neuro_workflow.analysis.mshbm.from_xcpd import gifti_to_mshbm_nifti

    # Synthetic per-vertex time series: 100 vertices × 50 TRs
    V, T = 100, 50
    data = np.arange(V * T, dtype=np.float32).reshape(V, T)
    darrays = [
        nib.gifti.GiftiDataArray(data=data[:, t].astype(np.float32),
                                  intent='NIFTI_INTENT_NONE')
        for t in range(T)
    ]
    gii = nib.gifti.GiftiImage(darrays=darrays)
    gii_path = tmp_path / 'lh.func.gii'
    nib.save(gii, str(gii_path))

    out = tmp_path / 'lh.nii.gz'
    gifti_to_mshbm_nifti(gii_path, out)

    img = nib.load(str(out))
    assert img.shape == (V, 1, 1, T)
    assert img.get_fdata().dtype in (np.float32, np.float64)
    # Round-trip the data
    arr = img.get_fdata().reshape(V, T)
    np.testing.assert_allclose(arr, data)
```

- [ ] **Step 3.2: Run test — verify failure**

Expected: `gifti_to_mshbm_nifti` not defined.

- [ ] **Step 3.3: Implement**

Add to `src/neuro_workflow/analysis/mshbm/from_xcpd.py`:

```python
import nibabel as nib
import numpy as np


def gifti_to_mshbm_nifti(gifti_path: Path, out_path: Path) -> Path:
    """Load a per-vertex GIFTI time series and write (V, 1, 1, T) NIfTI.

    MSHBM's CBIG MATLAB wrapper consumes per-hemi time series shaped as
    a 4-D NIfTI with the time axis last and singleton y/z. This helper
    builds that volume from a GIFTI with one DataArray per TR.
    """
    gii = nib.load(str(gifti_path))
    cols = [da.data.astype(np.float32) for da in gii.darrays]
    if not cols:
        raise ValueError(f'No data arrays in {gifti_path}')
    arr = np.stack(cols, axis=-1)  # (V, T)
    arr_4d = arr.reshape(arr.shape[0], 1, 1, arr.shape[1])
    img = nib.Nifti1Image(arr_4d, affine=np.eye(4))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(img, str(out_path))
    return out_path
```

- [ ] **Step 3.4: Run test — verify pass**

Expected: 4 passed.

- [ ] **Step 3.5: Commit**

```bash
git add tests/analysis/mshbm/test_from_xcpd.py src/neuro_workflow/analysis/mshbm/from_xcpd.py
git commit -m "$(cat <<'EOF'
feat(mshbm): gifti_to_mshbm_nifti wrapper

Loads a per-vertex GIFTI time series (one DataArray per TR) and writes
a 4-D NIfTI (V, 1, 1, T) at the path MSHBM's CBIG wrapper expects.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: TDD `templateflow_paths` resolver

**Files:**
- Modify: `tests/analysis/mshbm/test_from_xcpd.py`
- Modify: `src/neuro_workflow/analysis/mshbm/from_xcpd.py`

- [ ] **Step 4.1: Write failing test**

Append:

```python
def test_templateflow_paths_returns_existing_spheres():
    """Resolves the sphere + pial + white paths from the templateflow cache."""
    from neuro_workflow.analysis.mshbm.from_xcpd import templateflow_paths

    paths = templateflow_paths()
    for hemi in ('L', 'R'):
        assert paths[hemi]['fsLR_sphere'].is_file(), paths[hemi]['fsLR_sphere']
        assert paths[hemi]['fsaverage6_sphere'].is_file(), paths[hemi]['fsaverage6_sphere']
        assert paths[hemi]['fsaverage6_pial'].is_file(), paths[hemi]['fsaverage6_pial']
        assert paths[hemi]['fsaverage6_white'].is_file(), paths[hemi]['fsaverage6_white']
```

- [ ] **Step 4.2: Run test — verify failure**

Expected: `templateflow_paths` not defined.

- [ ] **Step 4.3: Implement**

Add to `src/neuro_workflow/analysis/mshbm/from_xcpd.py`:

```python
import os


def _templateflow_root() -> Path:
    """Resolve the templateflow cache root, honoring TEMPLATEFLOW_HOME."""
    root = os.environ.get('TEMPLATEFLOW_HOME')
    if root:
        return Path(root)
    return Path.home() / '.cache' / 'templateflow'


def templateflow_paths() -> dict[str, dict[str, Path]]:
    """Return the fsLR / fsaverage sphere + pial + white paths per hemi.

    Keys: 'L', 'R' → dict with keys 'fsLR_sphere' (32k registered to
    fsaverage), 'fsaverage6_sphere' (41k), 'fsaverage6_pial', 'fsaverage6_white'.
    """
    root = _templateflow_root()
    out: dict[str, dict[str, Path]] = {}
    for hemi in ('L', 'R'):
        out[hemi] = {
            'fsLR_sphere': root / 'tpl-fsLR' /
                f'tpl-fsLR_space-fsaverage_hemi-{hemi}_den-32k_sphere.surf.gii',
            'fsaverage6_sphere': root / 'tpl-fsaverage' /
                f'tpl-fsaverage_hemi-{hemi}_den-41k_sphere.surf.gii',
            'fsaverage6_pial': root / 'tpl-fsaverage' /
                f'tpl-fsaverage_hemi-{hemi}_den-41k_pial.surf.gii',
            'fsaverage6_white': root / 'tpl-fsaverage' /
                f'tpl-fsaverage_hemi-{hemi}_den-41k_white.surf.gii',
        }
    return out
```

- [ ] **Step 4.4: Run test**

Expected: 5 passed.

- [ ] **Step 4.5: Commit**

```bash
git add tests/analysis/mshbm/test_from_xcpd.py src/neuro_workflow/analysis/mshbm/from_xcpd.py
git commit -m "$(cat <<'EOF'
feat(mshbm): templateflow_paths resolver for sphere/pial/white

Returns paths to the four templateflow surface files per hemi needed
for the fsLR_32k → fsaverage6 resampling + smoothing chain.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Driver script `scripts/mshbm_from_xcpd.py`

**Files:**
- Create: `scripts/mshbm_from_xcpd.py`

- [ ] **Step 5.1: Write the driver**

Create `scripts/mshbm_from_xcpd.py`:

```python
"""Convert one subject's XCP-D denoised CIFTIs into MSHBM fsaverage6 inputs.

For each (session × task) cell, runs:
    wb_command -cifti-separate  (split L/R from CIFTI)
    wb_command -metric-resample (fsLR_32k → fsaverage6, BARYCENTRIC)
    wb_command -metric-smoothing (2mm FWHM on midthickness)
    python: wrap as (V, 1, 1, T) NIfTI for MSHBM

The fsaverage6 midthickness surfaces are pial+white averages, computed
once and cached at <output_dir>/.fsaverage6_midthickness_{L,R}.surf.gii.
"""
from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from neuro_workflow.analysis.mshbm.from_xcpd import (
    Cell,
    discover_xcpd_cells,
    gifti_to_mshbm_nifti,
    templateflow_paths,
)

logger = logging.getLogger(__name__)

# 2mm FWHM → sigma = 2 / 2.355 ≈ 0.849
SMOOTHING_SIGMA_MM = 2.0 / 2.355


def _run(cmd: list[str]) -> None:
    logger.debug('+ %s', ' '.join(str(c) for c in cmd))
    subprocess.run(cmd, check=True)


def _ensure_midthickness(out_dir: Path, paths: dict[str, dict[str, Path]]) -> dict[str, Path]:
    """Build (or cache) fsaverage6 midthickness per hemi."""
    midthk: dict[str, Path] = {}
    for hemi in ('L', 'R'):
        target = out_dir / f'.fsaverage6_midthickness_{hemi}.surf.gii'
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            _run([
                'wb_command', '-surface-average',
                str(target),
                '-surf', str(paths[hemi]['fsaverage6_pial']),
                '-surf', str(paths[hemi]['fsaverage6_white']),
            ])
        midthk[hemi] = target
    return midthk


def _process_cell(
    cell: Cell,
    subject: str,
    out_dir: Path,
    paths: dict[str, dict[str, Path]],
    midthk: dict[str, Path],
    work_dir: Path,
) -> None:
    """Run cifti-separate → metric-resample → metric-smoothing → nifti wrap
    for both hemispheres of one cell."""
    cifti_label = {'L': 'CORTEX_LEFT', 'R': 'CORTEX_RIGHT'}
    short = {'L': 'lh', 'R': 'rh'}

    # Step 1: split CIFTI → two per-hemi GIFTIs (fsLR_32k)
    sep_lh = work_dir / 'sep_lh.func.gii'
    sep_rh = work_dir / 'sep_rh.func.gii'
    _run([
        'wb_command', '-cifti-separate', str(cell.dtseries), 'COLUMN',
        '-metric', cifti_label['L'], str(sep_lh),
        '-metric', cifti_label['R'], str(sep_rh),
    ])

    for hemi, sep in (('L', sep_lh), ('R', sep_rh)):
        # Step 2: resample fsLR_32k → fsaverage6
        resampled = work_dir / f'resampled_{hemi}.func.gii'
        _run([
            'wb_command', '-metric-resample',
            str(sep),
            str(paths[hemi]['fsLR_sphere']),
            str(paths[hemi]['fsaverage6_sphere']),
            'BARYCENTRIC',
            str(resampled),
        ])

        # Step 3: smooth 2mm FWHM on fsaverage6 midthickness
        smoothed = work_dir / f'smoothed_{hemi}.func.gii'
        _run([
            'wb_command', '-metric-smoothing',
            str(midthk[hemi]),
            str(resampled),
            f'{SMOOTHING_SIGMA_MM:.6f}',
            str(smoothed),
        ])

        # Step 4: wrap as (V, 1, 1, T) NIfTI for MSHBM
        sub_dir = out_dir / f'sub-{subject}'
        out_path = sub_dir / f'{short[hemi]}_{cell.session}_task-{cell.task}_xcpd_fsaverage6_sm2.nii.gz'
        gifti_to_mshbm_nifti(smoothed, out_path)
        logger.info('  wrote %s', out_path.relative_to(out_dir))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--xcpd-dir', type=Path, required=True,
                   help='XCP-D derivatives root (contains sub-{XXX}/...)')
    p.add_argument('--subject', required=True,
                   help='Subject label without sub- prefix (e.g. s10)')
    p.add_argument('--output-dir', type=Path, required=True,
                   help='MSHBM input root (will create sub-{XXX}/ inside)')
    p.add_argument('--verbose', action='store_true')
    args = p.parse_args(argv)

    logging.basicConfig(
        format='%(asctime)s %(levelname)s: %(message)s', datefmt='%H:%M:%S',
        level=logging.DEBUG if args.verbose else logging.INFO,
    )

    if not shutil.which('wb_command'):
        logger.error('wb_command not on PATH — load the workbench module first')
        return 2

    subject_root = args.xcpd_dir / f'sub-{args.subject}'
    if not subject_root.is_dir():
        logger.error('No XCP-D output for sub-%s at %s', args.subject, subject_root)
        return 1

    cells = discover_xcpd_cells(subject_root)
    if not cells:
        logger.error('No desc-denoised CIFTIs found under %s', subject_root)
        return 1
    logger.info('Found %d cells for sub-%s', len(cells), args.subject)

    paths = templateflow_paths()
    midthk = _ensure_midthickness(args.output_dir, paths)

    with tempfile.TemporaryDirectory(prefix='mshbm_xcpd_') as work_dir_str:
        work_dir = Path(work_dir_str)
        for i, cell in enumerate(cells, 1):
            logger.info('[%d/%d] sub-%s %s task-%s', i, len(cells),
                        args.subject, cell.session, cell.task)
            _process_cell(cell, args.subject, args.output_dir, paths, midthk, work_dir)

    logger.info('done sub-%s', args.subject)
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 5.2: Smoke test the script's argparse + helper invocation (no real wb_command)**

Run from login node (will fail at `wb_command` check but verifies imports + CLI):

```bash
uv --directory /home/users/logben/neuro_workflow run python \
  scripts/mshbm_from_xcpd.py \
  --xcpd-dir /scratch/users/logben/discovery_bids/derivatives/xcp_d_26.0.2 \
  --subject s10 \
  --output-dir /tmp/mshbm_xcpd_smoke 2>&1 | tail -5
```

Expected: either "wb_command not on PATH" (exit 2) or runs (if workbench is module-loaded). Either way, no Python exceptions.

- [ ] **Step 5.3: Commit**

```bash
git add scripts/mshbm_from_xcpd.py
git commit -m "$(cat <<'EOF'
feat(mshbm): mshbm_from_xcpd.py driver

Per-subject driver that consumes XCP-D denoised CIFTIs and emits
MSHBM-ready fsaverage6 (V, 1, 1, T) NIfTIs via the wb_command chain:
  cifti-separate → metric-resample (BARYCENTRIC, 32k→41k) →
  metric-smoothing (σ=0.849, 2mm FWHM on midthickness).
fsaverage6 midthickness is built once per output dir from
templateflow pial+white via wb_command -surface-average.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: SLURM array wrapper sbatch

**Files:**
- Create: `/scratch/groups/russpold/logben/mshbm_from_xcpd.sbatch`

- [ ] **Step 6.1: Write the sbatch**

```bash
#!/bin/bash
#SBATCH -J mshbm_from_xcpd
#SBATCH --time=02:00:00
#SBATCH -n 1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH -p russpold
#SBATCH -o /scratch/users/logben/mshbm_inputs_{cohort}_xcpd/logs/%x-%A-%a.out
#SBATCH -e /scratch/users/logben/mshbm_inputs_{cohort}_xcpd/logs/%x-%A-%a.err

# Variables that need to be set when submitting:
#   COHORT=discovery|validation   (replaces {cohort})
#   XCPD_DIR=<path>               (XCP-D derivatives root)
#   OUTPUT_DIR=<path>             (MSHBM input root, e.g. mshbm_inputs_discovery_xcpd)
#   SUBJECTS_FILE=<path>          (one subject label per line, no sub- prefix)

set -uo pipefail

module load uv
module load workbench/1.5.0

SUBJECT=$(sed "${SLURM_ARRAY_TASK_ID}q;d" "$SUBJECTS_FILE")
SUBJECT=$(echo "$SUBJECT" | xargs)  # strip whitespace

mkdir -p "$OUTPUT_DIR/logs"

echo "[$(date '+%H:%M:%S')] task ${SLURM_ARRAY_TASK_ID} → sub-${SUBJECT}"

uv --directory /home/users/logben/neuro_workflow run python \
    /home/users/logben/neuro_workflow/scripts/mshbm_from_xcpd.py \
    --xcpd-dir "$XCPD_DIR" \
    --subject "$SUBJECT" \
    --output-dir "$OUTPUT_DIR" \
    --verbose

echo "[$(date '+%H:%M:%S')] done sub-${SUBJECT}"
```

Note: this template uses placeholders. Submission is via `sbatch --export=...` setting the env vars + `--array=1-N --output=... --error=...`.

- [ ] **Step 6.2: Verify sbatch syntax**

```bash
sbatch --test-only /scratch/groups/russpold/logben/mshbm_from_xcpd.sbatch 2>&1 | head -5
```

Expected: dry-run validation without submitting.

---

### Task 7: Smoke run on sub-s10

**Files:** none (operational)

- [ ] **Step 7.1: Run on a single subject, single cell at first**

Run a one-cell smoke directly (skip array overhead):

```bash
sbatch --wait \
  --partition=russpold --time=00:30:00 --mem=8G --cpus-per-task=2 \
  --output=/scratch/users/logben/mshbm_inputs_discovery_xcpd/logs/smoke-%j.out \
  --error=/scratch/users/logben/mshbm_inputs_discovery_xcpd/logs/smoke-%j.err \
  --wrap="module load uv workbench/1.5.0 && \
    mkdir -p /scratch/users/logben/mshbm_inputs_discovery_xcpd/logs && \
    uv --directory /home/users/logben/neuro_workflow run python \
      /home/users/logben/neuro_workflow/scripts/mshbm_from_xcpd.py \
      --xcpd-dir /scratch/users/logben/discovery_bids/derivatives/xcp_d_26.0.2 \
      --subject s10 \
      --output-dir /scratch/users/logben/mshbm_inputs_discovery_xcpd \
      --verbose"
```

- [ ] **Step 7.2: Verify file inventory**

```bash
ls /scratch/users/logben/mshbm_inputs_discovery_xcpd/sub-s10/ | wc -l
ls /scratch/users/logben/mshbm_inputs_discovery_xcpd/sub-s10/ | head -10
```

Expected: ~100-140 files (12 sessions × ~5-7 tasks × 2 hemis ≈ 120-180 cells × 2 = 240-360 GIFTIs in flight; final NIfTI count = cells × 2 hemis ≈ 120-180). Filenames follow `{lh,rh}_ses-{NN}_task-{T}_xcpd_fsaverage6_sm2.nii.gz`.

- [ ] **Step 7.3: Sanity-check one output's shape**

```bash
uv --directory /home/users/logben/neuro_workflow run python -c "
import nibabel as nib
img = nib.load('/scratch/users/logben/mshbm_inputs_discovery_xcpd/sub-s10/lh_ses-01_task-rest_xcpd_fsaverage6_sm2.nii.gz')
print('shape:', img.shape)
print('expected: (40962, 1, 1, T)')
"
```

Expected: shape (40962, 1, 1, T_rest) where T_rest matches XCP-D's rest TR count.

- [ ] **Step 7.4: Visual sign-off (manual)**

Open in Workbench on local machine — load one output on fsaverage6 pial. Confirm signal looks anatomically plausible. **STOP and report to user for sign-off before proceeding to Task 8.**

---

### Task 8: Discovery N=5 prep + MSHBM training

**Files:**
- Create: `/scratch/users/logben/mshbm_inputs_discovery_xcpd/subjects.txt`
- Create: `/scratch/users/logben/mshbm_training_discovery_xcpd/sub_list.csv`

- [ ] **Step 8.1: Build subjects file**

```bash
mkdir -p /scratch/users/logben/mshbm_inputs_discovery_xcpd
cat > /scratch/users/logben/mshbm_inputs_discovery_xcpd/subjects.txt <<EOF
s03
s10
s19
s29
s43
EOF
```

- [ ] **Step 8.2: Submit prep array**

```bash
sbatch --array=1-5 --export=ALL,\
COHORT=discovery,\
XCPD_DIR=/scratch/users/logben/discovery_bids/derivatives/xcp_d_26.0.2,\
OUTPUT_DIR=/scratch/users/logben/mshbm_inputs_discovery_xcpd,\
SUBJECTS_FILE=/scratch/users/logben/mshbm_inputs_discovery_xcpd/subjects.txt \
  --output=/scratch/users/logben/mshbm_inputs_discovery_xcpd/logs/%x-%A-%a.out \
  --error=/scratch/users/logben/mshbm_inputs_discovery_xcpd/logs/%x-%A-%a.err \
  /scratch/groups/russpold/logben/mshbm_from_xcpd.sbatch
```

Wait for completion. Each subject ~15-25 min, parallel up to russpold limit.

- [ ] **Step 8.3: Verify inventory across all 5 subjects**

```bash
for s in s03 s10 s19 s29 s43; do
  n=$(ls /scratch/users/logben/mshbm_inputs_discovery_xcpd/sub-$s/*.nii.gz 2>/dev/null | wc -l)
  echo "sub-$s : $n .nii.gz files"
done
```

Expected: each subject 100-180 files (some sessions may be missing tasks legitimately).

- [ ] **Step 8.4: Build MSHBM sub_list.csv**

```bash
mkdir -p /scratch/users/logben/mshbm_training_discovery_xcpd
cat > /scratch/users/logben/mshbm_training_discovery_xcpd/sub_list.csv <<EOF
sub-s03,/scratch/users/logben/mshbm_inputs_discovery_xcpd/
sub-s10,/scratch/users/logben/mshbm_inputs_discovery_xcpd/
sub-s19,/scratch/users/logben/mshbm_inputs_discovery_xcpd/
sub-s29,/scratch/users/logben/mshbm_inputs_discovery_xcpd/
sub-s43,/scratch/users/logben/mshbm_inputs_discovery_xcpd/
EOF
```

- [ ] **Step 8.5: Submit MSHBM training**

```bash
SUBLIST=/scratch/users/logben/mshbm_training_discovery_xcpd/sub_list.csv
OUTDIR=/scratch/users/logben/mshbm_training_discovery_xcpd
CODEDIR=/home/users/logben/network_glm/PrecisionNetworkMapping

mkdir -p $OUTDIR/log

# Submit prep step which auto-chains training (bigmem 384G via the patched
# MSHBM_Params_Training.sh from prior work).
sbatch -o $OUTDIR/log/MSHBM_Prep_%j.out \
       -e $OUTDIR/log/MSHBM_Prep_%j.err \
       $CODEDIR/MSHBM/MSHBM_Params_Training_Prep.sh \
       $SUBLIST $OUTDIR $CODEDIR
```

Wait for completion (~2h: 1h prep + 1h training).

- [ ] **Step 8.6: Verify outputs**

```bash
find /scratch/users/logben/mshbm_training_discovery_xcpd -name 'Params_Final.mat'
find /scratch/users/logben/mshbm_training_discovery_xcpd -name '*_MSHBM.dlabel.nii' | head -10
```

Expected: 1 Params_Final.mat + 5 per-subject .dlabel.nii files.

---

### Task 9: Validation N=41 prep

**Files:**
- Create: `/scratch/users/logben/mshbm_inputs_validation_xcpd/subjects.txt`

- [ ] **Step 9.1: Build validation subjects file**

```bash
mkdir -p /scratch/users/logben/mshbm_inputs_validation_xcpd
uv --directory /home/users/logben/neuro_workflow run python -c "
import json
with open('/home/users/logben/neuro_workflow/config/pipeline_config.json') as f:
    cfg = json.load(f)
for sub in sorted(cfg['samples']['validation'], key=lambda s: int(s.lstrip('s'))):
    print(sub)
" > /scratch/users/logben/mshbm_inputs_validation_xcpd/subjects.txt
wc -l /scratch/users/logben/mshbm_inputs_validation_xcpd/subjects.txt
```

Expected: 41 lines.

- [ ] **Step 9.2: Submit validation prep array**

```bash
sbatch --array=1-41 --export=ALL,\
COHORT=validation,\
XCPD_DIR=/scratch/users/logben/validation_bids/derivatives/xcp_d_26.0.2,\
OUTPUT_DIR=/scratch/users/logben/mshbm_inputs_validation_xcpd,\
SUBJECTS_FILE=/scratch/users/logben/mshbm_inputs_validation_xcpd/subjects.txt \
  --output=/scratch/users/logben/mshbm_inputs_validation_xcpd/logs/%x-%A-%a.out \
  --error=/scratch/users/logben/mshbm_inputs_validation_xcpd/logs/%x-%A-%a.err \
  /scratch/groups/russpold/logben/mshbm_from_xcpd.sbatch
```

Wait for completion (~2-4h with russpold queue depth).

- [ ] **Step 9.3: Verify inventory**

```bash
for s in $(cat /scratch/users/logben/mshbm_inputs_validation_xcpd/subjects.txt); do
  n=$(ls /scratch/users/logben/mshbm_inputs_validation_xcpd/sub-$s/*.nii.gz 2>/dev/null | wc -l)
  echo "sub-$s : $n"
done | tee /scratch/users/logben/mshbm_inputs_validation_xcpd/inventory.tsv
```

Expected: each subject 80-180 files. Investigate any subject < 30 files (likely missing sessions).

---

### Task 10: Pooled N=46 MSHBM training

**Files:**
- Create: `/scratch/users/logben/mshbm_inputs_pooled_xcpd/` (symlink farm)
- Create: `/scratch/users/logben/mshbm_training_pooled_xcpd/sub_list.csv`

- [ ] **Step 10.1: Build pooled input dir via symlinks**

```bash
mkdir -p /scratch/users/logben/mshbm_inputs_pooled_xcpd
cd /scratch/users/logben/mshbm_inputs_pooled_xcpd
for s in s03 s10 s19 s29 s43; do
  ln -sfn /scratch/users/logben/mshbm_inputs_discovery_xcpd/sub-$s sub-$s
done
for s in $(cat /scratch/users/logben/mshbm_inputs_validation_xcpd/subjects.txt); do
  ln -sfn /scratch/users/logben/mshbm_inputs_validation_xcpd/sub-$s sub-$s
done
ls -l /scratch/users/logben/mshbm_inputs_pooled_xcpd/ | wc -l
```

Expected: 47 (46 symlinks + header line).

- [ ] **Step 10.2: Build pooled sub_list.csv**

```bash
mkdir -p /scratch/users/logben/mshbm_training_pooled_xcpd
{
  for s in s03 s10 s19 s29 s43; do
    echo "sub-$s,/scratch/users/logben/mshbm_inputs_pooled_xcpd/"
  done
  for s in $(cat /scratch/users/logben/mshbm_inputs_validation_xcpd/subjects.txt); do
    echo "sub-$s,/scratch/users/logben/mshbm_inputs_pooled_xcpd/"
  done
} > /scratch/users/logben/mshbm_training_pooled_xcpd/sub_list.csv
wc -l /scratch/users/logben/mshbm_training_pooled_xcpd/sub_list.csv
```

Expected: 46 lines.

- [ ] **Step 10.3: Bump MSHBM_Params_Training.sh memory to 512G for N=46**

```bash
sed -i 's/#SBATCH --mem=384G/#SBATCH --mem=512G/' \
    /home/users/logben/network_glm/PrecisionNetworkMapping/MSHBM/MSHBM_Params_Training.sh
sed -i 's/#SBATCH -c 4/#SBATCH -c 8/' \
    /home/users/logben/network_glm/PrecisionNetworkMapping/MSHBM/MSHBM_Params_Training.sh
grep -E '#SBATCH' /home/users/logben/network_glm/PrecisionNetworkMapping/MSHBM/MSHBM_Params_Training.sh | head -9
```

Expected output should show `--mem=512G` and `-c 8`. Walltime stays at 12h (prior N=46 run finished in ~4h).

- [ ] **Step 10.4: Submit pooled MSHBM training**

```bash
SUBLIST=/scratch/users/logben/mshbm_training_pooled_xcpd/sub_list.csv
OUTDIR=/scratch/users/logben/mshbm_training_pooled_xcpd
CODEDIR=/home/users/logben/network_glm/PrecisionNetworkMapping

mkdir -p $OUTDIR/log
sbatch -o $OUTDIR/log/MSHBM_Prep_%j.out \
       -e $OUTDIR/log/MSHBM_Prep_%j.err \
       $CODEDIR/MSHBM/MSHBM_Params_Training_Prep.sh \
       $SUBLIST $OUTDIR $CODEDIR
```

Wait ~4-8h.

- [ ] **Step 10.5: Verify pooled outputs**

```bash
find /scratch/users/logben/mshbm_training_pooled_xcpd -name 'Params_Final.mat'
N=$(find /scratch/users/logben/mshbm_training_pooled_xcpd -name '*_MSHBM.dlabel.nii' | wc -l)
echo "Per-subject .dlabel.nii: $N (expected 46)"
```

Expected: 1 Params_Final.mat + 46 per-subject parcellations.

---

### Task 11: Documentation + memory update

**Files:**
- Modify: `~/.claude/projects/.../memory/MEMORY.md`
- Create: memory entry for the XCP-D→MSHBM pipeline
- Modify: `docs/MSHBM-PIPELINE.md` (if it exists) — add section pointing at new path

- [ ] **Step 11.1: Add memory file**

Create `~/.claude/projects/-home-users-logben-neuro-workflow/memory/mshbm_from_xcpd_pipeline.md`:

```markdown
---
name: MSHBM from XCP-D denoised data
description: Pipeline converting XCP-D 26.0.2 desc-denoised CIFTIs into fsaverage6 NIfTIs for MSHBM; replaces lev1-task-residual + Du2025 path
type: project
---

(Brief summary of pipeline, output paths, training outputs, and any lessons.)
```

- [ ] **Step 11.2: Add MEMORY.md index entry**

Append one-line entry to the Index section.

- [ ] **Step 11.3: Commit + push**

```bash
git add docs/MSHBM-PIPELINE.md  # only if it exists and was updated
git commit -m "docs(mshbm): note XCP-D-based MSHBM pipeline as the new default"
git push
```

---

## Self-Review

**Spec coverage** — every spec section maps to a task:

| Spec section | Task(s) |
|---|---|
| Helper module + tests | 1, 2, 3, 4 |
| Driver script | 5 |
| SLURM array wrapper | 6 |
| Smoke on s10 | 7 |
| Discovery N=5 prep + train | 8 |
| Validation N=41 prep | 9 |
| Pooled N=46 train | 10 |
| Documentation | 11 |

**Placeholder scan**: No "TBD" or "implement later". Each task has actual code or commands. The memory file body in Step 11.1 says "(Brief summary…)" — that's intentional; the content depends on outcomes from Tasks 7-10.

**Type consistency**: `Cell` dataclass (Task 2) used in `_process_cell` (Task 5). `templateflow_paths()` return shape `dict[str, dict[str, Path]]` used by `_ensure_midthickness` and `_process_cell`. NIfTI shape `(V, 1, 1, T)` and filename pattern `{lh,rh}_ses-{NN}_task-{T}_xcpd_fsaverage6_sm2.nii.gz` consistent across spec, driver, smoke-test verify, and sub_list construction.

**Risks**:
- wb_command version mismatch — pinned via `module load workbench/1.5.0`, consistent with `xcpd.sbatch`.
- Memory pressure for N=46 — Task 10.3 bumps mem to 512G/8cpu per prior successful run.
- Missing templateflow files — Task 4 unit test exercises the resolver, so a missing file would surface at test time.
- Long-running validation prep array — Task 9 explicitly waits and verifies inventory before pooled training.

---

## Execution

Plan complete. Choose execution approach:

1. **Subagent-Driven (recommended)** — fresh subagent per task with two-stage review
2. **Inline Execution** — execute in this session with checkpoints
