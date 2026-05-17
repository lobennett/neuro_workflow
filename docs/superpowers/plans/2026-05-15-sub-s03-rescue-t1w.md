# sub-s03 rescue T1w integration — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a one-off Flywheel↔BIDS audit script, use it to confirm sub-s03's Flywheel session 25210 contains the rescue T1w, un-exclude that session in `pipeline_config.json`, re-run bidsify + fmriprep on sub-s03, verify the new surface quality, and propagate to lev1-surface + prep-mshbm. Resolves both the bad-surface issue (162 Euler defects) and the 14-vs-12 session-count discrepancy.

**Architecture:** Two new artifacts: `scripts/audit_subject_flywheel_vs_bids.py` (reuses `bidsify/flywheel_query.py` primitives for FW queries; cross-references against `<bids>/<subject>/ses-*/`), and a config edit to `pipeline_config.json`. Everything else uses existing `neuro-run` submit machinery (`bidsify`, `fmriprep`, `lev1`, `prep-mshbm`) with `--subjects s03` filtering.

**Tech Stack:** Python 3.13, `flywheel-sdk` (already in pipeline deps), pandas, pytest. Existing neuro_workflow CLIs for SLURM submissions.

**Spec:** `docs/superpowers/specs/2026-05-15-sub-s03-rescue-t1w-design.md`

---

## File map

| File | Change |
|---|---|
| `scripts/audit_subject_flywheel_vs_bids.py` | Create — audit one subject's FW sessions vs BIDS contents |
| `tests/scripts/test_audit_subject_flywheel_vs_bids.py` | Create — 4 tests (smoke + 3 behavioral) |
| `config/pipeline_config.json` | Modify — flip s03/25210 from `exclude:true` to a documented include |
| `/scratch/users/logben/discovery_bids/.bidsignore` | Modify — append stale T1w paths |
| `docs/AUDIT-sub-s03.md` | Create — output of audit script |
| `docs/SURFACE-FIX-STATUS.md` | Modify — append sub-s03 row after re-QA |
| `docs/EXCLUSIONS.md` | Modify — add manual note about the .bidsignore additions |

No changes to bidsify, fmriprep, lev1, or prep-mshbm pipeline code — all support `--subjects` filtering already.

---

## Task 1: Scaffold the audit script + import test

**Files:**
- Create: `tests/scripts/test_audit_subject_flywheel_vs_bids.py`
- Create: `scripts/audit_subject_flywheel_vs_bids.py`

- [ ] **Step 1.1: Write the failing test**

Write `/home/users/logben/neuro_workflow/tests/scripts/test_audit_subject_flywheel_vs_bids.py`:

```python
"""Tests for scripts/audit_subject_flywheel_vs_bids.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = Path(__file__).resolve().parents[2] / 'scripts' / 'audit_subject_flywheel_vs_bids.py'
    spec = importlib.util.spec_from_file_location('audit', script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_audit_module_imports():
    mod = _load_module()
    assert hasattr(mod, 'audit_subject')
    assert hasattr(mod, 'render_audit_md')
    assert hasattr(mod, 'main')
```

- [ ] **Step 1.2: Run — expect FileNotFoundError**

```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/scripts/test_audit_subject_flywheel_vs_bids.py -v
```

Expected: FAIL with FileNotFoundError on the script path.

- [ ] **Step 1.3: Create stub script**

Write `/home/users/logben/neuro_workflow/scripts/audit_subject_flywheel_vs_bids.py`:

```python
"""Audit a single subject's Flywheel sessions vs current BIDS contents.

Outputs a markdown report mapping each Flywheel session to its BIDS session
number (or EXCLUDED / MISSING). Used to surface misclassified sessions before
fixing them in pipeline_config.json + re-running bidsify.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SessionAuditRow:
    fw_session_label: str
    fw_timestamp: str
    bids_session: str  # "ses-NN", "EXCLUDED", "MISSING", "REASSIGNED"
    n_t1w: int
    n_t2w: int
    n_bold: int
    n_fmap: int
    notes: str


def audit_subject(
    canonical_label: str,
    bids_dir: Path,
    fw_sessions: list[dict[str, Any]],
    config_overrides: dict[str, dict],
) -> list[SessionAuditRow]:
    """Cross-reference FW sessions for a subject against BIDS contents."""
    raise NotImplementedError


def render_audit_md(canonical_label: str, rows: list[SessionAuditRow]) -> str:
    """Render audit rows as a markdown table."""
    raise NotImplementedError


def main() -> int:
    raise NotImplementedError


if __name__ == '__main__':
    sys.exit(main())
```

- [ ] **Step 1.4: Run test — expect pass**

```bash
uv run pytest tests/scripts/test_audit_subject_flywheel_vs_bids.py -v
```

Expected: 1 passed.

- [ ] **Step 1.5: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add scripts/audit_subject_flywheel_vs_bids.py tests/scripts/test_audit_subject_flywheel_vs_bids.py
git commit -m "feat(audit): scaffold audit_subject_flywheel_vs_bids script

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: TDD `audit_subject` core logic

**Files:**
- Modify: `tests/scripts/test_audit_subject_flywheel_vs_bids.py`
- Modify: `scripts/audit_subject_flywheel_vs_bids.py`

- [ ] **Step 2.1: Append failing tests**

```python
def test_audit_marks_excluded_per_config(tmp_path):
    """A FW session with exclude:true in overrides shows as EXCLUDED."""
    mod = _load_module()
    bids = tmp_path / 'bids'
    (bids / 'sub-s03' / 'ses-01' / 'anat').mkdir(parents=True)
    fw_sessions = [
        {'fw_session_label': '20210101', 'timestamp': '2021-01-01T10:00:00',
         'acquisitions': [{'label': 'T1w_MPRAGE'}, {'label': 'BOLD_rest'}]},
        {'fw_session_label': '25210', 'timestamp': '2022-05-24T17:10:00',
         'acquisitions': [{'label': 'T1w_SagMPRAGE'}]},
    ]
    overrides = {'25210': {'exclude': True, 'reason': 'test'}}

    rows = mod.audit_subject('s03', bids, fw_sessions, overrides)
    assert len(rows) == 2
    by_label = {r.fw_session_label: r for r in rows}
    assert by_label['25210'].bids_session == 'EXCLUDED'
    assert by_label['25210'].n_t1w == 1


def test_audit_marks_reassigned_per_config(tmp_path):
    """A FW session with reassign_to in overrides shows as REASSIGNED."""
    mod = _load_module()
    bids = tmp_path / 'bids'
    bids.mkdir()
    fw_sessions = [
        {'fw_session_label': '22752', 'timestamp': '2021-02-12T09:00:00',
         'acquisitions': [{'label': 'T1w_MPRAGE'}]},
    ]
    overrides = {'22752': {'reassign_to': 's10', 'reason': 'mislabeled'}}

    rows = mod.audit_subject('s03', bids, fw_sessions, overrides)
    assert rows[0].bids_session == 'REASSIGNED'
    assert 'reassigned to s10' in rows[0].notes.lower()


def test_audit_maps_fw_session_to_bids_chronologically(tmp_path):
    """FW sessions sorted by timestamp map to ses-01, ses-02, ... in BIDS."""
    mod = _load_module()
    bids = tmp_path / 'bids'
    for s in ['ses-01', 'ses-02']:
        (bids / 'sub-s03' / s / 'anat').mkdir(parents=True)
        (bids / 'sub-s03' / s / 'anat' / f'sub-s03_{s}_T1w.nii.gz').touch()
    fw_sessions = [
        {'fw_session_label': 'A', 'timestamp': '2021-01-01T10:00:00',
         'acquisitions': [{'label': 'T1w'}]},
        {'fw_session_label': 'B', 'timestamp': '2021-02-01T10:00:00',
         'acquisitions': [{'label': 'T1w'}]},
    ]
    rows = mod.audit_subject('s03', bids, fw_sessions, {})
    by_label = {r.fw_session_label: r for r in rows}
    assert by_label['A'].bids_session == 'ses-01'
    assert by_label['B'].bids_session == 'ses-02'
```

- [ ] **Step 2.2: Run — expect 3 fails (NotImplementedError)**

```bash
uv run pytest tests/scripts/test_audit_subject_flywheel_vs_bids.py -v
```

- [ ] **Step 2.3: Implement `audit_subject`**

Replace the `audit_subject` body in `scripts/audit_subject_flywheel_vs_bids.py`:

```python
def _classify_acquisition(label: str) -> str:
    """Classify a Flywheel acquisition label into a BIDS scan-type bucket."""
    L = label.lower()
    if 't2w' in L or 't2' in L.replace('t2*', ''):
        return 't2w'
    if 't1w' in L or 'mprage' in L:
        return 't1w'
    if 'bold' in L or 'task' in L or 'rest' in L:
        return 'bold'
    if 'fmap' in L or 'fieldmap' in L or 'epi' in L:
        return 'fmap'
    return 'other'


def _count_acquisitions(acquisitions: list[dict[str, Any]]) -> dict[str, int]:
    counts = {'t1w': 0, 't2w': 0, 'bold': 0, 'fmap': 0}
    for acq in acquisitions:
        bucket = _classify_acquisition(acq.get('label', ''))
        if bucket in counts:
            counts[bucket] += 1
    return counts


def audit_subject(
    canonical_label: str,
    bids_dir: Path,
    fw_sessions: list[dict[str, Any]],
    config_overrides: dict[str, dict],
) -> list[SessionAuditRow]:
    """Cross-reference FW sessions for a subject against BIDS contents."""
    # Sort FW sessions chronologically (skipping excluded/reassigned for the
    # ses-NN numbering, since bidsify also skips them).
    sorted_sessions = sorted(fw_sessions, key=lambda s: s.get('timestamp', ''))

    bids_subj_dir = bids_dir / f'sub-{canonical_label}'
    bids_session_counter = 0

    rows: list[SessionAuditRow] = []
    for sess in sorted_sessions:
        label = sess['fw_session_label']
        override = config_overrides.get(label, {})
        counts = _count_acquisitions(sess.get('acquisitions', []))

        if override.get('exclude'):
            bids_label = 'EXCLUDED'
            notes = override.get('reason', '')
        elif override.get('reassign_to'):
            bids_label = 'REASSIGNED'
            notes = f"reassigned to {override['reassign_to']}: {override.get('reason', '')}"
        else:
            bids_session_counter += 1
            candidate = f'ses-{bids_session_counter:02d}'
            if (bids_subj_dir / candidate).is_dir():
                bids_label = candidate
                notes = ''
            else:
                bids_label = 'MISSING'
                notes = f'FW session present but no {candidate} dir in BIDS'

        rows.append(SessionAuditRow(
            fw_session_label=label,
            fw_timestamp=sess.get('timestamp', ''),
            bids_session=bids_label,
            n_t1w=counts['t1w'],
            n_t2w=counts['t2w'],
            n_bold=counts['bold'],
            n_fmap=counts['fmap'],
            notes=notes,
        ))
    return rows
```

- [ ] **Step 2.4: Run — expect 4 passed (smoke + 3 behavioral)**

```bash
uv run pytest tests/scripts/test_audit_subject_flywheel_vs_bids.py -v
```

- [ ] **Step 2.5: Commit**

```bash
git add scripts/audit_subject_flywheel_vs_bids.py tests/scripts/test_audit_subject_flywheel_vs_bids.py
git commit -m "feat(audit): audit_subject classifies FW sessions vs BIDS state

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: TDD `render_audit_md` + `main()` CLI

**Files:**
- Modify: `tests/scripts/test_audit_subject_flywheel_vs_bids.py`
- Modify: `scripts/audit_subject_flywheel_vs_bids.py`

- [ ] **Step 3.1: Append failing test**

```python
def test_render_audit_md_produces_table():
    mod = _load_module()
    rows = [
        mod.SessionAuditRow(
            fw_session_label='25210', fw_timestamp='2022-05-24T17:10:00',
            bids_session='EXCLUDED', n_t1w=1, n_t2w=0, n_bold=0, n_fmap=0,
            notes='Rescue T1w session',
        ),
    ]
    md = mod.render_audit_md('s03', rows)
    assert '# Audit — sub-s03' in md
    assert '| 25210 |' in md
    assert 'EXCLUDED' in md
    assert 'Rescue T1w session' in md
```

- [ ] **Step 3.2: Run — expect fail**

- [ ] **Step 3.3: Implement `render_audit_md` + `main`**

Replace the `render_audit_md` and `main` bodies:

```python
def render_audit_md(canonical_label: str, rows: list[SessionAuditRow]) -> str:
    lines = [
        f'# Audit — sub-{canonical_label}',
        '',
        '| FW Session | Timestamp | BIDS Session | T1w | T2w | BOLD | Fmap | Notes |',
        '|---|---|---|---|---|---|---|---|',
    ]
    for r in rows:
        lines.append(
            f'| {r.fw_session_label} | {r.fw_timestamp} | {r.bids_session} | '
            f'{r.n_t1w} | {r.n_t2w} | {r.n_bold} | {r.n_fmap} | {r.notes} |'
        )
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject', required=True,
                        help='Canonical subject label (e.g., s03)')
    parser.add_argument('--bids-dir', type=Path, required=True,
                        help='BIDS root (e.g., /scratch/users/logben/discovery_bids)')
    parser.add_argument('--config', type=Path,
                        default=Path('config/pipeline_config.json'),
                        help='Path to pipeline_config.json')
    parser.add_argument('--output-md', type=Path, default=None,
                        help='Write report to this path (else print to stdout)')
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    fw_cfg = config['flywheel']
    aliases = fw_cfg.get('subject_aliases', {})
    overrides_all = fw_cfg.get('session_overrides', {})
    subject_overrides = overrides_all.get(args.subject, {})

    # Use the existing bidsify FW query infrastructure
    import flywheel
    from neuro_workflow.bidsify.flywheel_query import (
        collect_subject_sessions, query_project_subjects,
    )
    fw = flywheel.Client()
    all_subjects, _project = query_project_subjects(fw, fw_cfg['project'])
    session_infos = collect_subject_sessions(
        canonical_label=args.subject,
        all_subjects=all_subjects,
        aliases=aliases,
        session_overrides=overrides_all,
    )

    # Adapt session_infos to the audit_subject input shape
    fw_sessions = []
    for info in session_infos:
        acqs = []
        for a in info['fw_session'].acquisitions():
            acqs.append({'label': a.label})
        fw_sessions.append({
            'fw_session_label': info['fw_session'].label,
            'timestamp': info['timestamp'].isoformat() if info['timestamp'] else '',
            'acquisitions': acqs,
        })

    rows = audit_subject(args.subject, args.bids_dir, fw_sessions, subject_overrides)
    md = render_audit_md(args.subject, rows)
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(md)
        print(f'Wrote {args.output_md}')
    else:
        print(md)
    return 0
```

- [ ] **Step 3.4: Run — expect 5 passed**

```bash
uv run pytest tests/scripts/test_audit_subject_flywheel_vs_bids.py -v
```

- [ ] **Step 3.5: Commit**

```bash
git add scripts/audit_subject_flywheel_vs_bids.py tests/scripts/test_audit_subject_flywheel_vs_bids.py
git commit -m "feat(audit): render_audit_md + CLI for audit_subject_flywheel_vs_bids

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Operational — run audit on sub-s03

**Files:**
- Create: `docs/AUDIT-sub-s03.md` (output of script)

- [ ] **Step 4.1: Authenticate with Flywheel + run audit**

The bidsify module's existing pattern uses `flywheel.Client()` which reads credentials from `~/.config/flywheel/user.json` (per memory). Confirm credentials are valid (the user has run bidsify before, so they should be).

```bash
cd /home/users/logben/neuro_workflow
module load uv
mkdir -p docs

uv run python scripts/audit_subject_flywheel_vs_bids.py \
    --subject s03 \
    --bids-dir /scratch/users/logben/discovery_bids \
    --config config/pipeline_config.json \
    --output-md docs/AUDIT-sub-s03.md
```

Expected runtime: ~30s (one subject, ~14 FW sessions to enumerate).

- [ ] **Step 4.2: Eyeball the output**

```bash
cat docs/AUDIT-sub-s03.md
```

Expected:
- 14 rows (one per FW session).
- One row for FW session `25210` showing `EXCLUDED` with `n_t1w=1` (confirms it has the rescue T1w as user described).
- One row for FW session `22752` showing `REASSIGNED` (reassigned to s10).
- 12 rows showing `ses-01` ... `ses-12` (the current BIDS sessions).

If `25210` shows `n_t1w=0`, STOP — user's report may be incorrect about session ID. Re-verify before proceeding.

- [ ] **Step 4.3: Commit the audit report**

```bash
git add docs/AUDIT-sub-s03.md
git commit -m "docs(audit): audit report for sub-s03 — confirms ses-25210 has rescue T1w

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Edit `pipeline_config.json` to un-exclude session 25210

**Files:**
- Modify: `config/pipeline_config.json`

- [ ] **Step 5.1: Open the file and locate the entry**

```bash
grep -n '"25210"' /home/users/logben/neuro_workflow/config/pipeline_config.json
```

Expected: shows the line within `flywheel.session_overrides.s03.25210`.

- [ ] **Step 5.2: Change the entry**

Replace:

```json
        "25210": {
          "exclude": true,
          "reason": "Empty/test session -- no usable imaging data"
        }
```

With:

```json
        "25210": {
          "note": "Rescue T1w session acquired 2022-05-24 after the original SagMPRAGE produced bad recon (162 Euler defects); becomes ses-13 in BIDS"
        }
```

(Drop the `exclude` field. The `note` field is informational — bidsify only checks for `exclude` and `reassign_to`.)

- [ ] **Step 5.3: Validate the JSON parses**

```bash
uv run python -c "import json; json.load(open('config/pipeline_config.json'))" && echo "OK"
```

Expected: `OK`.

- [ ] **Step 5.4: Commit**

```bash
git add config/pipeline_config.json
git commit -m "fix(config): un-exclude sub-s03 session 25210 (rescue T1w)

The session was misclassified as 'Empty/test session -- no usable imaging
data' but actually contains a rescue T1w acquired 2022-05-24 because
the original SagMPRAGE produced 162 mean Euler defects.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Rerun bidsify on sub-s03

**Files:** None (operational SLURM; produces files under `/scratch/users/logben/discovery_bids/sub-s03/ses-13/`)

- [ ] **Step 6.1: Submit bidsify for sub-s03 only**

```bash
cd /home/users/logben/neuro_workflow
uv run neuro-run submit bidsify discovery --subjects s03 --overwrite \
    --time 02:00:00 --mem-gb 16
```

Expected: prints "Submitted batch job NNNNN".

- [ ] **Step 6.2: Wait for job + verify the rescue T1w landed**

Poll `squeue -u logben -h -o "%j %T %M" | grep bidsify` until done (~30 min to 2h).

```bash
ls /scratch/users/logben/discovery_bids/sub-s03/ses-13/anat/ 2>/dev/null
```

Expected: at least one `sub-s03_ses-13_*_T1w.nii.gz` file present, plus its `.json` sidecar.

If `ses-13/` doesn't exist, inspect the bidsify logs (under the dataset's log dir) and STOP before proceeding.

- [ ] **Step 6.3: Re-run trim_bold.py (in case ses-13 has any BOLD that needs trimming)**

```bash
uv run python scripts/trim_bold.py /scratch/users/logben/discovery_bids
```

Per CLAUDE.md, `trim_bold.py` is idempotent (sidecar check) and atomic. It only operates on untrimmed BOLDs; previously-trimmed scans are skipped.

---

## Task 7: Update `.bidsignore` to hide stale T1ws

**Files:**
- Modify: `/scratch/users/logben/discovery_bids/.bidsignore`

- [ ] **Step 7.1: Append entries**

```bash
cat >> /scratch/users/logben/discovery_bids/.bidsignore <<'EOF'

# Stale T1ws for sub-s03 — kept on disk but hidden from fmriprep.
# The rescue T1w in ses-13 (acquired 2022-05-24) is the canonical anat.
sub-s03/ses-01/anat/*MPRAGEPromo*
sub-s03/ses-05/anat/*SagMPRAGE*
EOF
```

- [ ] **Step 7.2: Verify BIDS still validates**

```bash
apptainer run /home/groups/russpold/singularity_images/bids-validator_1.14.6.simg \
    /scratch/users/logben/discovery_bids 2>&1 | tail -20
```

Expected: 0 errors. Warnings about the .bidsignore'd files are OK.

- [ ] **Step 7.3: Document the additions in EXCLUSIONS.md**

Open `/home/users/logben/neuro_workflow/docs/EXCLUSIONS.md`; find the "Manual notes" section (or create one at the bottom) and append:

```markdown
## Manual notes (preserved across regenerations)

### sub-s03 stale T1ws (2026-05-15)

Hidden via `.bidsignore` after un-excluding Flywheel session 25210 (rescue T1w → ses-13):

- `sub-s03/ses-01/anat/*MPRAGEPromo*` — 4D-saved PROMO; frame 32 is the actual T1w but
  bidsify did not split it; kept for provenance.
- `sub-s03/ses-05/anat/*SagMPRAGE*` — produced 162 mean Euler defects in FreeSurfer
  recon (multiple "large defect" warnings); replaced by ses-13 rescue T1w.
```

- [ ] **Step 7.4: Commit**

```bash
git add docs/EXCLUSIONS.md
git commit -m "docs(exclusions): document sub-s03 stale T1w .bidsignore entries

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: Wipe stale fmriprep + work dir for sub-s03

**Files:** None (filesystem cleanup)

- [ ] **Step 8.1: Verify what will be deleted**

```bash
ls -d /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03 2>/dev/null
ls -d /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_* 2>/dev/null
ls -d /scratch/users/logben/work/fmriprep_discovery_25.2.4/fmriprep_25_2_wf/sub_s03_* 2>/dev/null
```

Expected: existing directories from the prior recon. None of them are referenced by the other 4 subjects' recons (each subject is independent).

- [ ] **Step 8.2: Delete them**

```bash
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_ses-05
# Note: there may be other sub-s03_ses-* FS dirs from prior debugging; check first:
ls -d /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_* 2>/dev/null
# Delete any that are present:
rm -rf /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_*
rm -rf /scratch/users/logben/work/fmriprep_discovery_25.2.4/fmriprep_25_2_wf/sub_s03_*
```

- [ ] **Step 8.3: Verify cleanup**

```bash
ls -d /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03 \
      /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_* \
      /scratch/users/logben/work/fmriprep_discovery_25.2.4/fmriprep_25_2_wf/sub_s03_* 2>&1 | head
```

Expected: "No such file or directory" for all paths.

---

## Task 9: Rerun fmriprep on sub-s03

**Files:** None (operational SLURM; produces files under `/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03/`)

- [ ] **Step 9.1: Ensure dataset registration filters to s03 only**

Reuse `discovery_phase1` if it exists (per memory it points at `subjects_phase1_s03.txt` with just `s03`):

```bash
grep -A 5 '"discovery_phase1"' ~/.neuro_workflow/datasets.json
cat /home/users/logben/neuro_workflow/subjects_phase1_s03.txt 2>/dev/null
```

Expected: `subjects_phase1_s03.txt` contains exactly `s03` on one line. If not, create it:

```bash
echo "s03" > /home/users/logben/neuro_workflow/subjects_phase1_s03.txt
```

If `discovery_phase1` doesn't exist, add it:

```bash
uv run python -c "
import json
p='/home/users/logben/.neuro_workflow/datasets.json'
with open(p) as f: d=json.load(f)
d.setdefault('discovery_phase1', {
    'bids_dir':'/scratch/users/logben/discovery_bids',
    'subjects_file':'subjects_phase1_s03.txt',
    'partition':'russpold',
    'mail_user':'logben@stanford.edu',
    'image_dir':'/home/groups/russpold/singularity_images',
    'templateflow_dir':'/home/groups/russpold/templateflow'
})
with open(p,'w') as f: json.dump(d, f, indent=2)
print('ok')
"
```

- [ ] **Step 9.2: Submit fmriprep**

```bash
cd /home/users/logben/neuro_workflow
uv run neuro-run submit fmriprep discovery_phase1 --version 25.2.4 \
    --output-spaces "MNI152NLin2009cAsym:res-1 MNI152NLin6Asym:res-2 fsaverage:den-41k fsnative T1w func" \
    --fmriprep-args "--use-syn-sdc --me-output-echos --bold2anat-init t2w" \
    --output-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
    --array-throttle 1 --time 12:00:00
```

Expected: prints "Submitted batch job NNNNN".

- [ ] **Step 9.3: Wait + verify**

Poll until done (~8-12h). Then:

```bash
ls /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s03_*/surf/ 2>/dev/null | head
find /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sub-s03 -name "*space-fsaverage6_bold.func.gii" 2>/dev/null | wc -l
```

Expected:
- New `sub-s03_ses-13/surf/` dir present (or similar — fmriprep's recon will use whichever session has the T1w; with .bidsignore filtering, ses-13 is the only T1w).
- ~57 fsaverage6 GIFTI files (12 rest + ~45 task × 2 hemispheres / well, actually one per (ses, task, run, hemi) — confirm count matches the other 4 subjects' counts for sub-s03's session structure).

If the recon failed or holes are still high, escalate per the spec's risk-handling section.

---

## Task 10: Re-QA on the new fmriprep output

**Files:**
- Modify: `docs/SURFACE-FIX-STATUS.md` (append sub-s03 row)

- [ ] **Step 10.1: Submit qa_report for sub-s03**

```bash
sbatch --wrap='module load uv && cd /home/users/logben/neuro_workflow && uv run python scripts/qa_report.py \
    --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
    --output-dir /scratch/users/logben/discovery_bids/derivatives/qa_reports \
    --subjects sub-s03 --no-reliability-movies' \
    -J qa_s03_rescue -p russpold -t 01:00:00 --mem=16G \
    -o /scratch/users/logben/discovery_bids/derivatives/qa_reports/qa_s03_rescue-%j.out \
    -e /scratch/users/logben/discovery_bids/derivatives/qa_reports/qa_s03_rescue-%j.err
```

Wait ~30-60 min.

- [ ] **Step 10.2: Check the new hole count**

```bash
grep -E "^subject|sub-s03" /scratch/users/logben/discovery_bids/derivatives/qa_reports/cohort.tsv
```

Expected: sub-s03's `fs_holes_mean` value is now in single digits or low teens (matching the other 4 discovery subjects which are 4.5–12).

If still > 100, proceed to step 10.3-FALLBACK below; otherwise step 10.3-SUCCESS.

- [ ] **Step 10.3-SUCCESS: Append KEEP row to SURFACE-FIX-STATUS.md**

If the file doesn't exist yet, create with the header used by `scripts/render_surface_fix_status.py`:

```bash
NEW_HOLES=$(awk -F'\t' '$1=="sub-s03"{print $5}' /scratch/users/logben/discovery_bids/derivatives/qa_reports/cohort.tsv)
cat >> docs/SURFACE-FIX-STATUS.md <<EOF

| sub-s03 | 162 | ${NEW_HOLES} | KEEP (rescue T1w from ses-13) |
EOF

git add docs/SURFACE-FIX-STATUS.md
git commit -m "docs(surface): record sub-s03 rescue T1w success (162 → ${NEW_HOLES} mean holes)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 10.3-FALLBACK: If holes still > 100, fall back to exclusion**

```bash
NEW_HOLES=$(awk -F'\t' '$1=="sub-s03"{print $5}' /scratch/users/logben/discovery_bids/derivatives/qa_reports/cohort.tsv)

cat >> config/manifests/qc_decisions.tsv <<EOF
sub-s03	-	-	-	exclude	surface_quality: 162 → ${NEW_HOLES} mean Euler defects (rescue T1w attempt failed)
EOF

uv run neuro-run exclusions compile discovery

cat >> docs/SURFACE-FIX-STATUS.md <<EOF

| sub-s03 | 162 | ${NEW_HOLES} | EXCLUDE (rescue T1w also failed) |
EOF

git add config/manifests/qc_decisions.tsv docs/SURFACE-FIX-STATUS.md
git commit -m "exclusions: add sub-s03 (rescue T1w attempt failed, still ${NEW_HOLES} holes)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

STOP here in the fallback case. Skip Tasks 11-12 (no point propagating to lev1/MSHBM if excluded).

---

## Task 11: Rerun lev1 surface for sub-s03

(Only if Task 10 hit the SUCCESS branch.)

**Files:** None (operational SLURM)

- [ ] **Step 11.1: Submit lev1 in surface space**

```bash
cd /home/users/logben/neuro_workflow
uv run neuro-run submit lev1 discovery_phase1 \
    --space surface \
    --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
    --time 06:00:00
```

(Adjust args based on the existing `lev1` pipeline CLI. The `discovery_phase1` dataset registration filters to s03 only.)

- [ ] **Step 11.2: Wait + verify outputs**

Poll until done (~1-2h). Then:

```bash
find /scratch/users/logben/lev1_discovery_post_fix/sub-s03 -name "*_stat-fixed-effects-z_score.nii.gz" 2>/dev/null | wc -l
```

Expected: matches the per-task contrast count from prior lev1 runs.

---

## Task 12: Rerun prep-mshbm for sub-s03

(Only if Task 10 hit the SUCCESS branch.)

**Files:** None (operational SLURM)

- [ ] **Step 12.1: Submit prep-mshbm**

```bash
uv run neuro-run submit prep-mshbm discovery_phase1 \
    --rest-only --include-task-bold --surface-fwhm 2 \
    --fmriprep-dir /scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4 \
    --output-dir /scratch/users/logben/mshbm_inputs_discovery_post_fix_s03 \
    --time 12:00:00 --mem-gb 64
```

- [ ] **Step 12.2: Wait + verify outputs**

Poll until done (~4-8h with 57-ish sessions). Then:

```bash
ls /scratch/users/logben/mshbm_inputs_discovery_post_fix_s03/sub-s03/ | wc -l
```

Expected: ~114 NIfTI files (57 sessions × 2 hemispheres) if `include_task_bold`, or ~24 if rest-only.

---

## Task 13: Final test suite + sanity

**Files:** None

- [ ] **Step 13.1: Run the full test suite**

```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/ 2>&1 | tail -8
```

Expected: all tests pass (the new audit tests + all pre-existing ones).

- [ ] **Step 13.2: Sanity check the deliverables**

```bash
ls docs/AUDIT-sub-s03.md docs/SURFACE-FIX-STATUS.md docs/EXCLUSIONS.md
git log --oneline qa-surface-exclusions-2026-05-15 ^main | head -20
```

Expected: all 3 doc files present; commit log shows the chain from the audit-scaffold commits through the operational fix.

---

## Self-Review

**Spec coverage** — every spec section maps to a task:

| Spec component | Task(s) |
|---|---|
| Phase 1 audit script + tests | Tasks 1, 2, 3 |
| Run audit on sub-s03 | Task 4 |
| Config edit (un-exclude 25210) | Task 5 |
| Bidsify rerun for sub-s03 | Task 6 |
| .bidsignore stale T1ws + EXCLUSIONS.md notes | Task 7 |
| Wipe stale fmriprep + work dir | Task 8 |
| fmriprep rerun for sub-s03 | Task 9 |
| Re-QA + SURFACE-FIX-STATUS append | Task 10 |
| Fallback exclusion path | Task 10.3-FALLBACK |
| lev1-surface propagation | Task 11 |
| prep-mshbm propagation | Task 12 |
| Final sanity | Task 13 |

All present.

**Placeholder scan**: No "TBD"/"add error handling"/"similar to" patterns. Every operational step has a real command. Fallback branching at Task 10 is explicit.

**Type consistency**: `SessionAuditRow` dataclass used consistently. `audit_subject` signature stable from Task 1 stub through Task 2 implementation. `render_audit_md` takes the canonical label + rows; same in test and CLI.

---

## Execution

**Plan complete and saved to `docs/superpowers/plans/2026-05-15-sub-s03-rescue-t1w.md`.** Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
