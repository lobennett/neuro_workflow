# fmriprep QA + surface-quality exclusions — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run `qa_report` on both cohorts at BIDS-compliant paths, diagnose high-hole subjects from existing fmriprep+FreeSurfer logs, attempt one round of SynthStrip + recon-all for skull-strip-suspected cases, propagate fixed recons through fmriprep + lev1(surface) + prep-mshbm, and produce a regenerated `EXCLUSIONS.md` mirroring every auto-exclude in compiled lockfiles.

**Architecture:** Five new scripts (`triage_surface_quality`, `diagnose_high_hole_subjects`, `synthstrip_recon_all`, `render_exclusions_md`, `render_surface_fix_status`). Reuse existing `qa_report`, exclusion generators (`motion`, `behavioral`, `qa_decisions`), `compile_exclusions`, and the `neuro-run` submit machinery for fmriprep / lev1 / prep-mshbm reruns. All QA outputs go under `<bids_root>/derivatives/qa_reports[_post_fix]/`. No version bumps — fmriprep 25.2.4, FreeSurfer 8.1.0 throughout.

**Tech Stack:** Python 3.13, pandas (cohort.tsv parsing), pytest, bash/sbatch (recon-all + fmriprep reruns). FreeSurfer 8.1.0 (recon-all, mri_synthstrip, mris_euler_number). Existing neuro_workflow CLIs.

**Spec:** `docs/superpowers/specs/2026-05-15-fmriprep-qa-and-surface-quality-exclusions-design.md`

---

## File map

| File | Change |
|---|---|
| `scripts/triage_surface_quality.py` | Create — read cohort.tsv, emit candidate-list of high-hole subjects |
| `scripts/diagnose_high_hole_subjects.py` | Create — inspect recon-all logs + fmriprep work-dir per subject, write SURFACE-DIAGNOSIS.md, emit fix-list vs straight-exclude list |
| `scripts/synthstrip_recon_all.sbatch` | Create — per-subject SLURM script: mri_synthstrip → recon-all → mris_euler_number |
| `scripts/render_exclusions_md.py` | Create — read compiled_exclusions.json (both cohorts), regenerate EXCLUSIONS.md grouped by source |
| `scripts/render_surface_fix_status.py` | Create — read pre + post cohort.tsv, emit SURFACE-FIX-STATUS.md table |
| `tests/scripts/test_triage_surface_quality.py` | Create — 3 tests |
| `tests/scripts/test_diagnose_high_hole_subjects.py` | Create — 2 tests |
| `tests/scripts/test_render_exclusions_md.py` | Create — 2 tests |
| `tests/scripts/test_render_surface_fix_status.py` | Create — 2 tests |
| `config/manifests/qc_decisions.tsv` | Modify — append rows for unfixable subjects (post-fix manual step) |
| `docs/EXCLUSIONS.md` | Regenerate — output of render_exclusions_md.py |
| `docs/SURFACE-DIAGNOSIS.md` | Create — output of diagnose_high_hole_subjects.py |
| `docs/SURFACE-FIX-STATUS.md` | Create — output of render_surface_fix_status.py |

---

## Task 1: Scaffold test scaffolding for `triage_surface_quality`

**Files:**
- Create: `tests/scripts/test_triage_surface_quality.py`

- [ ] **Step 1.1: Create test file with import smoke test**

Write `/home/users/logben/neuro_workflow/tests/scripts/test_triage_surface_quality.py`:

```python
"""Tests for scripts/triage_surface_quality.py."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def test_triage_module_imports():
    """The script's main function can be imported."""
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, 'find_high_hole_subjects')
    assert hasattr(mod, 'main')
```

- [ ] **Step 1.2: Run — expect ImportError (script doesn't exist yet)**

```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/scripts/test_triage_surface_quality.py -v
```

Expected: FAIL with `FileNotFoundError` or import error.

- [ ] **Step 1.3: Create stub script with the expected exports**

Write `/home/users/logben/neuro_workflow/scripts/triage_surface_quality.py`:

```python
"""Triage subjects by pre-fix Euler hole count from a qa_report cohort.tsv.

Outputs a candidate-list of subjects with pre-fix holes above threshold.
Used as input to diagnose_high_hole_subjects.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def find_high_hole_subjects(cohort_tsv: Path, threshold: int) -> pd.DataFrame:
    """Read a cohort.tsv and return rows where mean pre-fix holes > threshold."""
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 1.4: Run test — expect pass**

```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/scripts/test_triage_surface_quality.py -v
```

Expected: 1 passed.

- [ ] **Step 1.5: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add scripts/triage_surface_quality.py tests/scripts/test_triage_surface_quality.py
git commit -m "feat(qa): scaffold triage_surface_quality script + import test

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: TDD `find_high_hole_subjects` filter

**Files:**
- Modify: `tests/scripts/test_triage_surface_quality.py`
- Modify: `scripts/triage_surface_quality.py`

- [ ] **Step 2.1: Append failing tests**

Append to `tests/scripts/test_triage_surface_quality.py`:

```python
def test_find_high_hole_subjects_filters_by_threshold(tmp_path):
    """Returns rows where (lh_holes + rh_holes) / 2 > threshold."""
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    df = pd.DataFrame([
        {'subject': 'sub-s03', 'lh_holes': 184, 'rh_holes': 140},
        {'subject': 'sub-s10', 'lh_holes': 2, 'rh_holes': 7},
        {'subject': 'sub-s19', 'lh_holes': 13, 'rh_holes': 4},
    ])
    tsv = tmp_path / 'cohort.tsv'
    df.to_csv(tsv, sep='\t', index=False)

    result = mod.find_high_hole_subjects(tsv, threshold=100)
    assert list(result['subject']) == ['sub-s03']
    assert result.iloc[0]['mean_holes'] == 162.0


def test_find_high_hole_subjects_empty_when_none_exceed(tmp_path):
    """Returns empty DataFrame when no subjects exceed threshold."""
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    df = pd.DataFrame([
        {'subject': 'sub-s10', 'lh_holes': 2, 'rh_holes': 7},
        {'subject': 'sub-s19', 'lh_holes': 13, 'rh_holes': 4},
    ])
    tsv = tmp_path / 'cohort.tsv'
    df.to_csv(tsv, sep='\t', index=False)

    result = mod.find_high_hole_subjects(tsv, threshold=100)
    assert len(result) == 0
```

- [ ] **Step 2.2: Run — expect 2 fails (NotImplementedError)**

```bash
uv run pytest tests/scripts/test_triage_surface_quality.py -v
```

- [ ] **Step 2.3: Implement**

In `scripts/triage_surface_quality.py`, replace the `find_high_hole_subjects` body:

```python
def find_high_hole_subjects(cohort_tsv: Path, threshold: int) -> pd.DataFrame:
    """Read a cohort.tsv and return rows where mean pre-fix holes > threshold."""
    df = pd.read_csv(cohort_tsv, sep='\t')
    df['mean_holes'] = (df['lh_holes'] + df['rh_holes']) / 2
    return df.loc[df['mean_holes'] > threshold].reset_index(drop=True)
```

- [ ] **Step 2.4: Run — expect pass**

Expected: 3 passed.

- [ ] **Step 2.5: Commit**

```bash
git add scripts/triage_surface_quality.py tests/scripts/test_triage_surface_quality.py
git commit -m "feat(qa): triage_surface_quality.find_high_hole_subjects filter

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Add `main()` CLI to triage script

**Files:**
- Modify: `tests/scripts/test_triage_surface_quality.py`
- Modify: `scripts/triage_surface_quality.py`

- [ ] **Step 3.1: Append failing test**

```python
def test_main_writes_markdown_to_stdout(tmp_path, capsys):
    """main() prints a markdown table of flagged subjects."""
    import sys
    import importlib.util
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'triage_surface_quality.py'
    spec = importlib.util.spec_from_file_location('triage_surface_quality', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    df = pd.DataFrame([
        {'subject': 'sub-s03', 'lh_holes': 184, 'rh_holes': 140},
        {'subject': 'sub-s10', 'lh_holes': 2, 'rh_holes': 7},
    ])
    tsv = tmp_path / 'cohort.tsv'
    df.to_csv(tsv, sep='\t', index=False)

    sys.argv = ['triage_surface_quality', '--cohort-tsv', str(tsv), '--threshold', '100']
    rc = mod.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert 'sub-s03' in out
    assert 'sub-s10' not in out  # below threshold
    assert '| subject' in out  # markdown table header
```

- [ ] **Step 3.2: Run — expect fail (NotImplementedError)**

- [ ] **Step 3.3: Implement `main()`**

Replace the `main()` body in `scripts/triage_surface_quality.py`:

```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort-tsv', type=Path, required=True,
                        help='Path to qa_report cohort.tsv')
    parser.add_argument('--threshold', type=int, default=100,
                        help='Mean pre-fix Euler hole count threshold (default 100)')
    args = parser.parse_args()

    result = find_high_hole_subjects(args.cohort_tsv, args.threshold)
    if len(result) == 0:
        print(f'No subjects exceed {args.threshold} mean pre-fix holes.')
        return 0

    cols = ['subject', 'lh_holes', 'rh_holes', 'mean_holes']
    print(result[cols].to_markdown(index=False))
    return 0
```

- [ ] **Step 3.4: Run — expect pass**

Expected: 4 passed.

- [ ] **Step 3.5: Commit**

```bash
git add scripts/triage_surface_quality.py tests/scripts/test_triage_surface_quality.py
git commit -m "feat(qa): triage_surface_quality CLI emits markdown table

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Scaffold `diagnose_high_hole_subjects.py`

**Files:**
- Create: `tests/scripts/test_diagnose_high_hole_subjects.py`
- Create: `scripts/diagnose_high_hole_subjects.py`

- [ ] **Step 4.1: Create test scaffold**

Write `/home/users/logben/neuro_workflow/tests/scripts/test_diagnose_high_hole_subjects.py`:

```python
"""Tests for scripts/diagnose_high_hole_subjects.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'diagnose_high_hole_subjects.py'
    spec = importlib.util.spec_from_file_location('diagnose', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_module_imports():
    mod = _load_module()
    assert hasattr(mod, 'diagnose_subject')
    assert hasattr(mod, 'main')
```

- [ ] **Step 4.2: Run — expect FileNotFoundError**

```bash
uv run pytest tests/scripts/test_diagnose_high_hole_subjects.py -v
```

- [ ] **Step 4.3: Create script scaffold**

Write `/home/users/logben/neuro_workflow/scripts/diagnose_high_hole_subjects.py`:

```python
"""Inspect recon-all logs for high-hole subjects to identify root cause.

For each subject above the hole threshold, scan recon-all.log + recon-all-status.log,
classify likely cause (skull-strip / motion / unknown), and emit a markdown report.
The classification drives the fix-vs-exclude decision for downstream steps.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


CauseCategory = Literal['skull_strip', 'motion', 'unknown', 'log_missing']


@dataclass
class DiagnosisResult:
    subject: str
    fs_subject: str
    pre_fix_holes_mean: float
    cause: CauseCategory
    evidence: str


def diagnose_subject(
    subjects_dir: Path, fs_subject: str, pre_fix_holes_mean: float,
) -> DiagnosisResult:
    """Inspect recon-all logs for one subject; return diagnosis."""
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 4.4: Run — expect pass**

Expected: 1 passed.

- [ ] **Step 4.5: Commit**

```bash
git add scripts/diagnose_high_hole_subjects.py tests/scripts/test_diagnose_high_hole_subjects.py
git commit -m "feat(qa): scaffold diagnose_high_hole_subjects script

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: TDD `diagnose_subject` classifier

**Files:**
- Modify: `tests/scripts/test_diagnose_high_hole_subjects.py`
- Modify: `scripts/diagnose_high_hole_subjects.py`

- [ ] **Step 5.1: Append failing test**

```python
def test_diagnose_subject_classifies_skull_strip(tmp_path):
    """recon-all.log with 'Topology fixer' + brainmask issues → skull_strip."""
    mod = _load_module()
    sd = tmp_path / 'fs'
    fs_subj = 'sub-s03_ses-05'
    scripts = sd / fs_subj / 'scripts'
    scripts.mkdir(parents=True)
    (scripts / 'recon-all.log').write_text(
        'mri_watershed: brainmask too aggressive\n'
        'WARNING: skull-stripping may have removed brain tissue\n'
        'Topology fixer found 324 defects\n'
        'recon-all -all finished without error\n'
    )
    (scripts / 'recon-all-status.log').write_text(
        'recon-all -s sub-s03_ses-05 finished without error at Sun Apr  5 12:34:56 PDT 2026\n'
    )

    result = mod.diagnose_subject(sd, fs_subj, pre_fix_holes_mean=162.0)
    assert result.subject == 'sub-s03'
    assert result.cause == 'skull_strip'
    assert '324 defects' in result.evidence


def test_diagnose_subject_classifies_unknown_when_no_log(tmp_path):
    """Missing recon-all.log → cause='log_missing'."""
    mod = _load_module()
    sd = tmp_path / 'fs'
    (sd / 'sub-sXX_ses-01').mkdir(parents=True)

    result = mod.diagnose_subject(sd, 'sub-sXX_ses-01', pre_fix_holes_mean=150.0)
    assert result.cause == 'log_missing'
```

- [ ] **Step 5.2: Run — expect fail (NotImplementedError)**

- [ ] **Step 5.3: Implement `diagnose_subject`**

Add to `scripts/diagnose_high_hole_subjects.py`:

```python
_SKULL_STRIP_PATTERNS = [
    re.compile(r'brainmask.+(too aggressive|failed|removed brain)', re.I),
    re.compile(r'skull.?strip.+(may have|might have|aggressive)', re.I),
    re.compile(r'mri_watershed.+(error|warn)', re.I),
]

_MOTION_PATTERNS = [
    re.compile(r'motion artifact', re.I),
    re.compile(r'image.+severely motion.?corrupted', re.I),
]


def diagnose_subject(
    subjects_dir: Path, fs_subject: str, pre_fix_holes_mean: float,
) -> DiagnosisResult:
    subject = fs_subject.split('_ses-')[0]
    log_path = subjects_dir / fs_subject / 'scripts' / 'recon-all.log'
    if not log_path.exists():
        return DiagnosisResult(
            subject=subject, fs_subject=fs_subject,
            pre_fix_holes_mean=pre_fix_holes_mean,
            cause='log_missing',
            evidence=f'recon-all.log not found at {log_path}',
        )

    text = log_path.read_text(errors='replace')
    skull_hits = [p.search(text) for p in _SKULL_STRIP_PATTERNS]
    skull_hits = [m for m in skull_hits if m]
    motion_hits = [p.search(text) for p in _MOTION_PATTERNS]
    motion_hits = [m for m in motion_hits if m]

    defects_match = re.search(r'Topology fixer found (\d+) defects?', text)
    defects_str = f'{defects_match.group(1)} defects' if defects_match else ''

    if skull_hits:
        evidence = '; '.join([m.group(0)[:80] for m in skull_hits])
        if defects_str:
            evidence = f'{evidence}; {defects_str}'
        return DiagnosisResult(subject, fs_subject, pre_fix_holes_mean,
                               cause='skull_strip', evidence=evidence)
    if motion_hits:
        evidence = '; '.join([m.group(0)[:80] for m in motion_hits])
        return DiagnosisResult(subject, fs_subject, pre_fix_holes_mean,
                               cause='motion', evidence=evidence)
    return DiagnosisResult(subject, fs_subject, pre_fix_holes_mean,
                           cause='unknown',
                           evidence=f'no diagnostic pattern matched; {defects_str or "no defect line"}')
```

- [ ] **Step 5.4: Run — expect pass**

Expected: 3 passed.

- [ ] **Step 5.5: Commit**

```bash
git add scripts/diagnose_high_hole_subjects.py tests/scripts/test_diagnose_high_hole_subjects.py
git commit -m "feat(qa): diagnose_subject classifies recon-all failures

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `main()` for diagnose + markdown report

**Files:**
- Modify: `scripts/diagnose_high_hole_subjects.py`

- [ ] **Step 6.1: Implement `main()`**

Replace `main()` in `scripts/diagnose_high_hole_subjects.py`:

```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subjects-dir', type=Path, required=True,
                        help='FreeSurfer SUBJECTS_DIR (e.g. <bids>/derivatives/fmriprep_*/sourcedata/freesurfer)')
    parser.add_argument('--cohort-tsv', type=Path, required=True,
                        help='qa_report cohort.tsv (provides per-subject hole counts)')
    parser.add_argument('--threshold', type=int, default=100,
                        help='Mean pre-fix holes threshold (default 100)')
    parser.add_argument('--output-md', type=Path, default=None,
                        help='Optional: write report to markdown file')
    args = parser.parse_args()

    import pandas as pd
    df = pd.read_csv(args.cohort_tsv, sep='\t')
    df['mean_holes'] = (df['lh_holes'] + df['rh_holes']) / 2
    flagged = df.loc[df['mean_holes'] > args.threshold]

    if len(flagged) == 0:
        print(f'No subjects exceed {args.threshold} mean pre-fix holes; nothing to diagnose.')
        return 0

    results = []
    for _, row in flagged.iterrows():
        # Map bare BIDS subject (sub-s03) to FreeSurfer subject (sub-s03_ses-05)
        candidates = sorted(args.subjects_dir.glob(f'{row["subject"]}_ses-*'))
        candidates = [c for c in candidates if c.is_dir()]
        if not candidates:
            results.append(DiagnosisResult(
                subject=row['subject'], fs_subject='(none)',
                pre_fix_holes_mean=row['mean_holes'],
                cause='log_missing',
                evidence='No FreeSurfer subject dir found',
            ))
            continue
        fs_subj = candidates[0].name
        results.append(diagnose_subject(args.subjects_dir, fs_subj, row['mean_holes']))

    lines = [
        '# Surface diagnosis — high-hole subjects',
        '',
        f'Threshold: mean pre-fix holes > {args.threshold}',
        '',
        '| Subject | FS subject | Mean holes | Cause | Evidence |',
        '|---|---|---|---|---|',
    ]
    for r in results:
        lines.append(f'| {r.subject} | {r.fs_subject} | {r.pre_fix_holes_mean:.1f} | {r.cause} | {r.evidence} |')

    md = '\n'.join(lines) + '\n'
    if args.output_md:
        args.output_md.write_text(md)
        print(f'Wrote {args.output_md}')
    else:
        print(md)

    n_fix = sum(1 for r in results if r.cause == 'skull_strip')
    n_excl = len(results) - n_fix
    print(f'\nFix attempts (skull_strip cause): {n_fix}', file=sys.stderr)
    print(f'Direct exclusions (other causes): {n_excl}', file=sys.stderr)
    return 0
```

- [ ] **Step 6.2: Run all diagnose tests + sanity check the CLI**

```bash
uv run pytest tests/scripts/test_diagnose_high_hole_subjects.py -v
```

Expected: 3 passed (no new tests; smoke + 2 existing).

- [ ] **Step 6.3: Commit**

```bash
git add scripts/diagnose_high_hole_subjects.py
git commit -m "feat(qa): diagnose CLI emits SURFACE-DIAGNOSIS.md table

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Write `synthstrip_recon_all.sbatch` template

**Files:**
- Create: `scripts/synthstrip_recon_all.sbatch`

- [ ] **Step 7.1: Create the sbatch template**

Write `/home/users/logben/neuro_workflow/scripts/synthstrip_recon_all.sbatch`:

```bash
#!/bin/bash
#SBATCH -J synthstrip_recon
#SBATCH -p russpold
#SBATCH -t 14:00:00
#SBATCH --mem=16G
#SBATCH -c 4
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err

# Required environment variables (pass via --export or sbatch ENV=...):
#   SUBJ            BIDS subject (e.g. sub-s03)
#   T1W_INPUT       absolute path to subject's preproc T1w NIfTI (1mm)
#   ORIG_SD         original FreeSurfer SUBJECTS_DIR (for fs_subject name lookup)
#   FIX_SD          target FreeSurfer SUBJECTS_DIR for the fixed recon
#                   (e.g. <bids>/derivatives/freesurfer_fix)
#
# Output:
#   $FIX_SD/${SUBJ}_fix/  — full FreeSurfer recon
#   $FIX_SD/${SUBJ}_fix/pre_fix_holes.txt — pre-fix Euler hole counts (.orig.nofix)
#   $FIX_SD/${SUBJ}_fix/post_fix_holes.txt — post-fix Euler hole counts (.orig)

set -euo pipefail
module load biology freesurfer/8.1.0

: "${SUBJ:?SUBJ is required}"
: "${T1W_INPUT:?T1W_INPUT is required}"
: "${FIX_SD:?FIX_SD is required}"

mkdir -p "$FIX_SD"
export SUBJECTS_DIR="$FIX_SD"

WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

echo "=== mri_synthstrip on $T1W_INPUT ==="
mri_synthstrip -i "$T1W_INPUT" -o "$WORK/brain_synthstrip.nii.gz"

echo "=== recon-all (FreeSurfer 8.1.0) ==="
recon-all -all \
    -i "$WORK/brain_synthstrip.nii.gz" \
    -subjid "${SUBJ}_fix" \
    -sd "$FIX_SD"

OUT="$FIX_SD/${SUBJ}_fix"

echo "=== pre-fix Euler hole counts (.orig.nofix) ==="
for hemi in lh rh; do
    line=$(mris_euler_number "$OUT/surf/${hemi}.orig.nofix" 2>/dev/null | grep -oE '[0-9]+ holes')
    echo "$hemi $line"
done > "$OUT/pre_fix_holes.txt"

echo "=== post-fix Euler hole counts (.orig) ==="
for hemi in lh rh; do
    line=$(mris_euler_number "$OUT/surf/${hemi}.orig" 2>/dev/null | grep -oE '[0-9]+ holes')
    echo "$hemi $line"
done > "$OUT/post_fix_holes.txt"

echo "DONE: $OUT"
cat "$OUT/pre_fix_holes.txt"
echo "---"
cat "$OUT/post_fix_holes.txt"
```

- [ ] **Step 7.2: Make executable + commit**

```bash
chmod +x /home/users/logben/neuro_workflow/scripts/synthstrip_recon_all.sbatch
git add scripts/synthstrip_recon_all.sbatch
git commit -m "feat(qa): synthstrip_recon_all sbatch template

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

(Operational verification — the sbatch's correctness — happens in Task 11 against the real recon. No unit test for a SLURM-only artifact.)

---

## Task 8: Scaffold `render_surface_fix_status.py`

**Files:**
- Create: `tests/scripts/test_render_surface_fix_status.py`
- Create: `scripts/render_surface_fix_status.py`

- [ ] **Step 8.1: Create test scaffold + implementation**

Write `/home/users/logben/neuro_workflow/tests/scripts/test_render_surface_fix_status.py`:

```python
"""Tests for scripts/render_surface_fix_status.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'render_surface_fix_status.py'
    spec = importlib.util.spec_from_file_location('render_status', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_render_status_keep_vs_exclude(tmp_path):
    """Subjects fixed below threshold → KEEP; still above → EXCLUDE."""
    mod = _load_module()

    pre = pd.DataFrame([
        {'subject': 'sub-s03', 'lh_holes': 184, 'rh_holes': 140},
        {'subject': 'sub-sXX', 'lh_holes': 220, 'rh_holes': 195},
    ])
    post = pd.DataFrame([
        {'subject': 'sub-s03', 'lh_holes': 12, 'rh_holes': 8},
        {'subject': 'sub-sXX', 'lh_holes': 198, 'rh_holes': 170},
    ])
    pre_tsv = tmp_path / 'pre.tsv'; pre.to_csv(pre_tsv, sep='\t', index=False)
    post_tsv = tmp_path / 'post.tsv'; post.to_csv(post_tsv, sep='\t', index=False)

    md = mod.render_status(pre_tsv, post_tsv, threshold=100)
    assert 'sub-s03' in md
    assert 'KEEP' in md
    assert 'sub-sXX' in md
    assert 'EXCLUDE' in md


def test_render_status_handles_only_subjects_in_post(tmp_path):
    """Subjects in post.tsv but not in pre.tsv are skipped (shouldn't happen but be safe)."""
    mod = _load_module()
    pre = pd.DataFrame([{'subject': 'sub-s03', 'lh_holes': 184, 'rh_holes': 140}])
    post = pd.DataFrame([
        {'subject': 'sub-s03', 'lh_holes': 12, 'rh_holes': 8},
        {'subject': 'sub-other', 'lh_holes': 5, 'rh_holes': 3},
    ])
    pre_tsv = tmp_path / 'pre.tsv'; pre.to_csv(pre_tsv, sep='\t', index=False)
    post_tsv = tmp_path / 'post.tsv'; post.to_csv(post_tsv, sep='\t', index=False)

    md = mod.render_status(pre_tsv, post_tsv, threshold=100)
    assert 'sub-s03' in md
    assert 'sub-other' not in md
```

Write `/home/users/logben/neuro_workflow/scripts/render_surface_fix_status.py`:

```python
"""Render the SURFACE-FIX-STATUS.md table comparing pre- vs post-fix hole counts."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


def render_status(pre_tsv: Path, post_tsv: Path, threshold: int) -> str:
    pre = pd.read_csv(pre_tsv, sep='\t')
    post = pd.read_csv(post_tsv, sep='\t')
    pre['mean_holes'] = (pre['lh_holes'] + pre['rh_holes']) / 2
    post['mean_holes'] = (post['lh_holes'] + post['rh_holes']) / 2

    rows = []
    for _, p in pre.iterrows():
        q = post.loc[post['subject'] == p['subject']]
        if len(q) == 0:
            continue
        q = q.iloc[0]
        decision = 'KEEP' if q['mean_holes'] <= threshold else 'EXCLUDE'
        rows.append({
            'subject': p['subject'],
            'pre': f"{int(p['lh_holes'])}/{int(p['rh_holes'])}/{p['mean_holes']:.0f}",
            'post': f"{int(q['lh_holes'])}/{int(q['rh_holes'])}/{q['mean_holes']:.0f}",
            'decision': decision,
        })

    lines = [
        '# Surface fix status',
        '',
        f'Threshold: mean post-fix Euler holes ≤ {threshold} → KEEP',
        '',
        '| Subject | Pre LH/RH/Mean | Post LH/RH/Mean | Decision |',
        '|---|---|---|---|',
    ]
    for r in rows:
        lines.append(f'| {r["subject"]} | {r["pre"]} | {r["post"]} | {r["decision"]} |')
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pre-cohort-tsv', type=Path, required=True)
    parser.add_argument('--post-cohort-tsv', type=Path, required=True)
    parser.add_argument('--threshold', type=int, default=100)
    parser.add_argument('--output-md', type=Path, default=None)
    args = parser.parse_args()

    md = render_status(args.pre_cohort_tsv, args.post_cohort_tsv, args.threshold)
    if args.output_md:
        args.output_md.write_text(md)
        print(f'Wrote {args.output_md}')
    else:
        print(md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 8.2: Run tests**

```bash
uv run pytest tests/scripts/test_render_surface_fix_status.py -v
```

Expected: 2 passed.

- [ ] **Step 8.3: Commit**

```bash
git add scripts/render_surface_fix_status.py tests/scripts/test_render_surface_fix_status.py
git commit -m "feat(qa): render_surface_fix_status report

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 9: Scaffold + TDD `render_exclusions_md.py`

**Files:**
- Create: `tests/scripts/test_render_exclusions_md.py`
- Create: `scripts/render_exclusions_md.py`

- [ ] **Step 9.1: Test + implementation**

Write `/home/users/logben/neuro_workflow/tests/scripts/test_render_exclusions_md.py`:

```python
"""Tests for scripts/render_exclusions_md.py."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'render_exclusions_md.py'
    spec = importlib.util.spec_from_file_location('render_excl', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sample_compiled():
    return {
        'entries': [
            {'subject': 'sub-s03', 'session': '-', 'task': '-', 'run': '-',
             'source': 'qa_decisions', 'reason': 'surface_quality: 324 holes'},
            {'subject': 'sub-s10', 'session': '04', 'task': 'cuedTS', 'run': '1',
             'source': 'motion', 'reason': 'mean FD > 0.5'},
            {'subject': 'sub-s10', 'session': '07', 'task': 'rest', 'run': '1',
             'source': 'behavioral', 'reason': 'omission > 25%'},
        ],
    }


def test_render_md_groups_by_source(tmp_path):
    mod = _load_module()
    p = tmp_path / 'compiled.json'
    p.write_text(json.dumps(_sample_compiled()))

    md = mod.render_md({'discovery': p})
    assert '## discovery' in md
    assert '### Source: qa_decisions' in md
    assert '### Source: motion' in md
    assert '### Source: behavioral' in md
    assert 'sub-s03' in md
    assert 'mean FD > 0.5' in md


def test_render_md_handles_multiple_cohorts(tmp_path):
    mod = _load_module()
    p_disc = tmp_path / 'disc.json'
    p_disc.write_text(json.dumps(_sample_compiled()))
    p_val = tmp_path / 'val.json'
    p_val.write_text(json.dumps({'entries': []}))

    md = mod.render_md({'discovery': p_disc, 'validation': p_val})
    assert '## discovery' in md
    assert '## validation' in md
    assert '(no exclusions)' in md  # validation section
```

Write `/home/users/logben/neuro_workflow/scripts/render_exclusions_md.py`:

```python
"""Regenerate EXCLUSIONS.md from compiled_exclusions.json (both cohorts).

Reads the committed lockfile for each cohort, groups entries by source
(motion / behavioral / qa_decisions / etc.), produces a markdown table per
source per cohort. Manual notes in a `## Manual notes` section are preserved.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


_AUTO_HEADER = '<!-- AUTO-GENERATED by scripts/render_exclusions_md.py — do not edit above this line -->'
_MANUAL_HEADER = '## Manual notes (preserved across regenerations)'


def render_md(compiled_paths: dict[str, Path]) -> str:
    lines = ['# Exclusions', '', _AUTO_HEADER, '']
    for cohort, path in compiled_paths.items():
        lines.append(f'## {cohort}')
        lines.append('')
        if not path.exists():
            lines.append(f'(lockfile not found: {path})')
            lines.append('')
            continue
        data = json.loads(path.read_text())
        entries = data.get('entries', [])
        if not entries:
            lines.append('(no exclusions)')
            lines.append('')
            continue

        # Group by source
        by_source: dict[str, list] = defaultdict(list)
        for e in entries:
            by_source[e['source']].append(e)

        for source in sorted(by_source.keys()):
            lines.append(f'### Source: {source}')
            lines.append('')
            lines.append('| Subject | Session | Task | Run | Reason |')
            lines.append('|---|---|---|---|---|')
            for e in by_source[source]:
                lines.append(
                    f"| {e['subject']} | {e.get('session', '-')} | "
                    f"{e.get('task', '-')} | {e.get('run', '-')} | {e.get('reason', '')} |"
                )
            lines.append('')
    return '\n'.join(lines) + '\n'


def _preserve_manual_notes(existing_md: str | None) -> str:
    if existing_md is None or _MANUAL_HEADER not in existing_md:
        return _MANUAL_HEADER + '\n\n(none)\n'
    return existing_md[existing_md.index(_MANUAL_HEADER):]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiled', nargs='+', required=True,
                        help='cohort=path/to/compiled_exclusions.json pairs '
                             '(e.g., discovery=~/.neuro_workflow/.../compiled_exclusions.json)')
    parser.add_argument('--output-md', type=Path, required=True,
                        help='Path to EXCLUSIONS.md to write')
    args = parser.parse_args()

    compiled_paths: dict[str, Path] = {}
    for pair in args.compiled:
        cohort, path = pair.split('=', 1)
        compiled_paths[cohort] = Path(path).expanduser()

    auto = render_md(compiled_paths)
    existing = args.output_md.read_text() if args.output_md.exists() else None
    manual = _preserve_manual_notes(existing)
    args.output_md.write_text(auto + '\n' + manual)
    print(f'Wrote {args.output_md}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 9.2: Run tests**

```bash
uv run pytest tests/scripts/test_render_exclusions_md.py -v
```

Expected: 2 passed.

- [ ] **Step 9.3: Commit**

```bash
git add scripts/render_exclusions_md.py tests/scripts/test_render_exclusions_md.py
git commit -m "feat(qa): render_exclusions_md regenerator with manual-notes preservation

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 10: Operational — run qa_report on both cohorts

**Files:** None (operational SLURM)

- [ ] **Step 10.1: Submit discovery qa_report at new canonical path**

```bash
cd /home/users/logben/neuro_workflow
mkdir -p /scratch/users/logben/discovery_bids/derivatives/qa_reports
sbatch --wrap='module load uv; cd /home/users/logben/neuro_workflow && uv run python scripts/qa_report.py \
    --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
    --output-dir /scratch/users/logben/discovery_bids/derivatives/qa_reports \
    --no-reliability-movies' \
    -J qa_report_discovery -p russpold -t 02:00:00 --mem=16G \
    -o /scratch/users/logben/discovery_bids/derivatives/qa_reports/qa_report-%j.out \
    -e /scratch/users/logben/discovery_bids/derivatives/qa_reports/qa_report-%j.err
```

- [ ] **Step 10.2: Submit validation qa_report**

```bash
mkdir -p /scratch/users/logben/validation_bids/derivatives/qa_reports
sbatch --wrap='module load uv; cd /home/users/logben/neuro_workflow && uv run python scripts/qa_report.py \
    --fmriprep-dir /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4 \
    --output-dir /scratch/users/logben/validation_bids/derivatives/qa_reports \
    --no-reliability-movies' \
    -J qa_report_validation -p russpold -t 04:00:00 --mem=16G \
    -o /scratch/users/logben/validation_bids/derivatives/qa_reports/qa_report-%j.out \
    -e /scratch/users/logben/validation_bids/derivatives/qa_reports/qa_report-%j.err
```

- [ ] **Step 10.3: Wait for both to complete + sanity check**

```bash
# Verify both cohort.tsv files exist
ls -la /scratch/users/logben/discovery_bids/derivatives/qa_reports/cohort.tsv
ls -la /scratch/users/logben/validation_bids/derivatives/qa_reports/cohort.tsv
```

Expected: both files present, non-empty.

---

## Task 11: Run triage + diagnose on both cohorts

**Files:**
- Create: `docs/SURFACE-DIAGNOSIS.md` (output)

- [ ] **Step 11.1: Run triage on discovery**

```bash
cd /home/users/logben/neuro_workflow
uv run python scripts/triage_surface_quality.py \
    --cohort-tsv /scratch/users/logben/discovery_bids/derivatives/qa_reports/cohort.tsv \
    --threshold 100
```

Expected: prints markdown table of subjects with mean pre-fix holes > 100. Save the output.

- [ ] **Step 11.2: Run triage on validation**

```bash
uv run python scripts/triage_surface_quality.py \
    --cohort-tsv /scratch/users/logben/validation_bids/derivatives/qa_reports/cohort.tsv \
    --threshold 100
```

- [ ] **Step 11.3: Run diagnosis on each cohort**

```bash
mkdir -p docs

uv run python scripts/diagnose_high_hole_subjects.py \
    --subjects-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer \
    --cohort-tsv /scratch/users/logben/discovery_bids/derivatives/qa_reports/cohort.tsv \
    --threshold 100 \
    --output-md docs/SURFACE-DIAGNOSIS-discovery.md

uv run python scripts/diagnose_high_hole_subjects.py \
    --subjects-dir /scratch/users/logben/validation_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer \
    --cohort-tsv /scratch/users/logben/validation_bids/derivatives/qa_reports/cohort.tsv \
    --threshold 100 \
    --output-md docs/SURFACE-DIAGNOSIS-validation.md
```

- [ ] **Step 11.4: Commit the diagnosis reports**

```bash
git add docs/SURFACE-DIAGNOSIS-discovery.md docs/SURFACE-DIAGNOSIS-validation.md
git commit -m "docs(qa): SURFACE-DIAGNOSIS reports for high-hole subjects

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 12: Submit SynthStrip+recon-all reruns for skull-strip-suspected subjects

**Files:** None (operational SLURM)

- [ ] **Step 12.1: Compile fix-list from diagnosis reports**

Manually review `docs/SURFACE-DIAGNOSIS-*.md`. Extract the subjects whose `cause` column says `skull_strip`. Note for each: the cohort it belongs to and the path to its preproc T1w. (Diagnosis already gives the FS subject; T1w lives at `<bids>/derivatives/fmriprep_25.2.4/<sub>/<ses>/anat/<sub>_<ses>_*_desc-preproc_T1w.nii.gz` without an MNI suffix.)

- [ ] **Step 12.2: Submit one sbatch per fix-list subject**

For each subject in the fix list (example for sub-s03 in discovery):

```bash
T1W=$(ls /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03/ses-*/anat/sub-s03_ses-*_*desc-preproc_T1w.nii.gz | grep -v MNI | head -1)
mkdir -p /scratch/users/logben/discovery_bids/derivatives/freesurfer_fix

sbatch --export=ALL,SUBJ=sub-s03,T1W_INPUT="$T1W",FIX_SD=/scratch/users/logben/discovery_bids/derivatives/freesurfer_fix \
    -o /scratch/users/logben/discovery_bids/derivatives/freesurfer_fix/synthstrip-sub-s03-%j.out \
    -e /scratch/users/logben/discovery_bids/derivatives/freesurfer_fix/synthstrip-sub-s03-%j.err \
    scripts/synthstrip_recon_all.sbatch
```

Repeat for each subject. (`bash` loop OK; one sbatch per subject — recon-all takes 6-12h per subject.)

- [ ] **Step 12.3: Wait for completion**

Poll `squeue -u logben -h -o "%j %T" | grep synthstrip_recon` until empty. Total wallclock: ~12-24h depending on how many subjects + node availability.

- [ ] **Step 12.4: Spot-check one finished recon**

```bash
# Pick the first fix subject; confirm recon finished cleanly:
SUBJ=sub-s03  # adjust based on actual fix list
FIX_SD=/scratch/users/logben/discovery_bids/derivatives/freesurfer_fix
cat "$FIX_SD/${SUBJ}_fix/post_fix_holes.txt"
tail -5 "$FIX_SD/${SUBJ}_fix/scripts/recon-all-status.log"
```

Expected: `post_fix_holes.txt` shows two lines (lh, rh) with hole counts; status log ends with "finished without error".

---

## Task 13: Re-run fmriprep with the fixed FreeSurfer recon

**Files:** None (operational SLURM)

- [ ] **Step 13.1: For each fix-list subject, submit per-subject fmriprep with --fs-subjects-dir**

Submit per-subject fmriprep where the freesurfer dir is the new `freesurfer_fix`. The neuro_workflow `fmriprep` pipeline doesn't support `--fs-subjects-dir` as a top-level CLI, but `--fmriprep-args` passes arbitrary args. Use a temporary single-subject text file per submission.

For one subject (example for sub-s03 in discovery):

```bash
echo "s03" > /home/users/logben/neuro_workflow/subjects_fix_s03.txt
python3 -c "
import json
p='/home/users/logben/.neuro_workflow/datasets.json'
with open(p) as f: d=json.load(f)
d['discovery_fix_s03']={
    'bids_dir':'/scratch/users/logben/discovery_bids',
    'subjects_file':'subjects_fix_s03.txt',
    'partition':'russpold',
    'mail_user':'logben@stanford.edu',
    'image_dir':'/home/groups/russpold/singularity_images',
    'templateflow_dir':'/home/groups/russpold/templateflow'
}
with open(p,'w') as f: json.dump(d,f,indent=2)
"

# Submit fmriprep with --fs-subjects-dir pointed at the fixed recon
# The recon dir name is sub-s03_fix; fmriprep expects sub-<id>; build a symlink first.
ln -snf /scratch/users/logben/discovery_bids/derivatives/freesurfer_fix/sub-s03_fix \
        /scratch/users/logben/discovery_bids/derivatives/freesurfer_fix/sub-s03_ses-05

uv run neuro-run submit fmriprep discovery_fix_s03 --version 25.2.4 \
    --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage:den-41k fsnative T1w func" \
    --fmriprep-args "--fs-subjects-dir /scratch/users/logben/discovery_bids/derivatives/freesurfer_fix --use-syn-sdc --me-output-echos --bold2anat-init t2w" \
    --output-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_post_fix \
    --array-throttle 1 --time 12:00:00
```

Repeat for each fix-list subject. (Each subject = one ephemeral dataset registration + one fmriprep submission.)

- [ ] **Step 13.2: Wait for completion**

Per-subject fmriprep with cached anat (since we're feeding pre-recon freesurfer) takes ~3-6h.

- [ ] **Step 13.3: Spot-check output**

```bash
# For each fix subject, verify fsaverage6 surfaces produced:
find /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_post_fix/sub-s03 \
    -name "*space-fsaverage6_bold.func.gii" | head -3
```

Expected: GIFTI files present.

---

## Task 14: Re-QA on fmriprep_25.2.4_post_fix outputs

**Files:** None (operational SLURM)

- [ ] **Step 14.1: Run qa_report against the post-fix fmriprep dir**

```bash
mkdir -p /scratch/users/logben/discovery_bids/derivatives/qa_reports_post_fix
sbatch --wrap='module load uv; cd /home/users/logben/neuro_workflow && uv run python scripts/qa_report.py \
    --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_post_fix \
    --output-dir /scratch/users/logben/discovery_bids/derivatives/qa_reports_post_fix \
    --no-reliability-movies' \
    -J qa_report_post_fix_disc -p russpold -t 02:00:00 --mem=16G \
    -o /scratch/users/logben/discovery_bids/derivatives/qa_reports_post_fix/qa_report-%j.out \
    -e /scratch/users/logben/discovery_bids/derivatives/qa_reports_post_fix/qa_report-%j.err
```

Same for validation if it has fix subjects.

- [ ] **Step 14.2: Run render_surface_fix_status**

```bash
uv run python scripts/render_surface_fix_status.py \
    --pre-cohort-tsv /scratch/users/logben/discovery_bids/derivatives/qa_reports/cohort.tsv \
    --post-cohort-tsv /scratch/users/logben/discovery_bids/derivatives/qa_reports_post_fix/cohort.tsv \
    --threshold 100 \
    --output-md docs/SURFACE-FIX-STATUS-discovery.md
# Same for validation if applicable.
```

- [ ] **Step 14.3: Commit status reports**

```bash
git add docs/SURFACE-FIX-STATUS-discovery.md docs/SURFACE-FIX-STATUS-validation.md 2>/dev/null
git commit -m "docs(qa): SURFACE-FIX-STATUS reports (pre/post-fix hole counts + KEEP/EXCLUDE)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 15: Propagate fixed recons to lev1 (surface) + prep-mshbm

**Files:** None (operational SLURM)

- [ ] **Step 15.1: For each KEEP subject (post-fix holes ≤ 100), re-run lev1 surface**

```bash
# Example for sub-s03 in discovery (if fixed):
uv run neuro-run submit lev1 discovery_fix_s03 \
    --space surface \
    --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_post_fix \
    --results-dir /scratch/users/logben/lev1_discovery_post_fix \
    --time 06:00:00
```

(Wait for completion; expected 1-2h per subject.)

- [ ] **Step 15.2: For each KEEP subject, re-run prep-mshbm**

```bash
uv run neuro-run submit prep-mshbm discovery_fix_s03 --rest-only --include-task-bold --surface-fwhm 2 \
    --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4_post_fix \
    --output-dir /scratch/users/logben/mshbm_inputs_discovery_v7_upsample_post_fix \
    --time 12:00:00 --mem-gb 64
```

(MNI/T1w-space lev1 reruns are explicitly deferred to a future sub-project.)

---

## Task 16: Encode unfixable subjects in qc_decisions.tsv

**Files:**
- Modify: `config/manifests/qc_decisions.tsv`

- [ ] **Step 16.1: Append rows for EXCLUDE subjects**

For each subject marked EXCLUDE in `SURFACE-FIX-STATUS-*.md` (i.e., subjects whose post-fix holes still exceed 100, OR subjects whose diagnosis was `unknown`/`motion` and were never fix-attempted):

```bash
# Open the manifest
edit config/manifests/qc_decisions.tsv
```

Append rows (tab-delimited; example shown — adjust per actual exclusion list):

```
sub-sXX	-	-	-	exclude	surface_quality: 220 pre-fix → 198 post-fix Euler defects (fix failed)
sub-sYY	-	-	-	exclude	surface_quality: 150 pre-fix Euler defects (diagnosis=motion; no fix attempted)
```

- [ ] **Step 16.2: Commit the updated manifest**

```bash
git add config/manifests/qc_decisions.tsv
git commit -m "exclusions: add surface_quality decisions from sub-project A

Subjects with post-fix Euler defects > 100, or non-skull-strip-related
diagnoses where no fix was attempted. See docs/SURFACE-FIX-STATUS-*.md
and docs/SURFACE-DIAGNOSIS-*.md for evidence.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 17: Recompile exclusions + regenerate EXCLUSIONS.md

**Files:**
- Modify: `docs/EXCLUSIONS.md`
- Modify: `~/.neuro_workflow/exclusions/{discovery,validation}/compiled_exclusions.json` (lockfile)

- [ ] **Step 17.1: Run compile-exclusions for both cohorts**

```bash
uv run neuro-run exclusions compile discovery
uv run neuro-run exclusions compile validation
```

This rebuilds `~/.neuro_workflow/exclusions/{discovery,validation}/compiled_exclusions.json`, picking up the new `qa_decisions` rows from `qc_decisions.tsv` and the existing `motion` + `behavioral` sources.

- [ ] **Step 17.2: Regenerate EXCLUSIONS.md**

```bash
uv run python scripts/render_exclusions_md.py \
    --compiled discovery=~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json \
              validation=~/.neuro_workflow/exclusions/validation/compiled_exclusions.json \
    --output-md docs/EXCLUSIONS.md
```

- [ ] **Step 17.3: Spot-check the output**

```bash
head -40 docs/EXCLUSIONS.md
```

Expected: auto-generated header, then `## discovery` section with motion / behavioral / qa_decisions subsections, then `## validation` section, then the `## Manual notes (preserved across regenerations)` marker.

- [ ] **Step 17.4: Commit the updated docs + lockfiles**

```bash
git add docs/EXCLUSIONS.md ~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json ~/.neuro_workflow/exclusions/validation/compiled_exclusions.json 2>/dev/null
# (Lockfiles may be elsewhere; adjust path if compile-exclusions writes to a different location.)

git commit -m "docs(exclusions): regenerate EXCLUSIONS.md mirroring all auto-excludes

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage check** — every section of the spec has a task:

| Spec component | Task(s) |
|---|---|
| Component 0: Diagnose existing recon | Tasks 4–6 (script), Task 11 (execution) |
| Component 1: Validation qa_report run | Task 10 |
| Component 2: Triage helper | Tasks 1–3 (script), Task 11 (execution) |
| Component 3: SynthStrip+recon rerun | Task 7 (sbatch), Task 12 (execution) |
| Component 4: fmriprep re-run | Task 13 |
| Component 5: Re-QA after fix | Task 14 |
| Component 6: lev1+prep-mshbm propagation | Task 15 |
| Component 7: qc_decisions.tsv updates | Task 16 |
| Component 8: compile-exclusions | Task 17 |
| Component 9: EXCLUSIONS.md regen | Tasks 9 (script), 17 (execution) |
| Component 10: Fix-status report | Tasks 8 (script), 14 (execution) |

All present.

**Placeholder scan**: No "TBD"/"add error handling"/"similar to" patterns. Operational tasks (10–17) describe `bash`/`sbatch` commands rather than code — that's appropriate because they invoke existing CLIs / scripts produced by earlier tasks.

**Type consistency**: `find_high_hole_subjects` returns `pd.DataFrame`, used downstream. `diagnose_subject` returns `DiagnosisResult` dataclass. `render_md` / `render_status` return strings. Naming consistent throughout.

---

## Execution

**Plan complete and saved to `docs/superpowers/plans/2026-05-15-fmriprep-qa-and-surface-quality-exclusions.md`.** Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
