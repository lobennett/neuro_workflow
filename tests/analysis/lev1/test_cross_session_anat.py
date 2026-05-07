"""Cross-session anat resolution for subjects whose chosen T1w lives in a
different session than their BOLDs.

Several discovery (s10, s19, s29, s43) and validation subjects had their
default-session anat scans excluded via ``.bidsignore`` because the T1w was
unusable. fmriprep then chose a T1w from a *different* session for each
subject, e.g.:

* sub-s10 -> ses-09
* sub-s19 -> ses-05
* sub-s29 -> ses-04
* sub-s43 -> ses-05

In real fmriprep 25.x output for this project the chosen anat is emitted
per-session at ``sub-X/ses-Y/anat/`` (NOT subject-level ``sub-X/anat/``).
The session that contains the anat directory is whichever session fmriprep
selected; other sessions have only ``func/`` and ``fmap/``.

These tests cover two concerns that interact at the lev1 boundary:

1. ``mshbm.run.find_anat_dir`` correctly walks per-session anat dirs and
   returns the one that holds the chosen T1w, regardless of which session
   the BOLDs live in. (This is the canonical resolver for any code that
   needs the subject's anat outputs.)
2. ``FileFinder.get_files`` for a BOLD in a session that has *no* anat
   directory still returns a complete run record. lev1's FileFinder keys
   on ``space-T1w_desc-preproc_bold.nii.gz`` (a BOLD resampled into T1w
   space, NOT the anatomical T1w), so anat-side files are not required
   for BOLD discovery and a missing per-session anat must not silently
   filter the run out.

If a future change adds an anat-aware path to lev1, that path MUST go
through ``find_anat_dir`` (or an equivalent cross-session resolver), never
``fmriprep_dir / sub / ses_of_bold / anat``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from neuro_workflow.analysis.io.file_discovery import FileFinder
from neuro_workflow.analysis.mshbm.run import (
    find_anat_dir,
    find_mni_to_t1w_transform,
    find_t1w_reference,
)


# (subject, session that holds anat, session that holds BOLDs without anat)
# Anat sessions are taken from the real fmriprep_25.2.4 derivatives layout.
CROSS_SESSION_CASES = [
    ('sub-s10', 'ses-09', 'ses-01'),
    ('sub-s19', 'ses-05', 'ses-01'),
    ('sub-s29', 'ses-04', 'ses-01'),
    ('sub-s43', 'ses-05', 'ses-01'),
]


def _make_anat_session(fmriprep: Path, subject: str, session: str) -> Path:
    """Create a per-session anat dir with the chosen T1w + transforms.

    Mirrors the real fmriprep 25.x layout for this project:
    ``sub-X/ses-Y/anat/sub-X_ses-Y_acq-SagMPRAGE_run-1_<suffix>``.
    """
    anat_dir = fmriprep / subject / session / 'anat'
    anat_dir.mkdir(parents=True, exist_ok=True)
    base = f'{subject}_{session}_acq-SagMPRAGE_run-1'
    (anat_dir / f'{base}_desc-preproc_T1w.nii.gz').write_text('mock')
    (anat_dir / f'{base}_desc-brain_mask.nii.gz').write_text('mock')
    (anat_dir / f'{base}_from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5').write_text(
        'mock'
    )
    (anat_dir / f'{base}_from-T1w_to-MNI152NLin2009cAsym_mode-image_xfm.h5').write_text(
        'mock'
    )
    return anat_dir


def _make_func_session(
    bids: Path,
    fmriprep: Path,
    subject: str,
    session: str,
    task: str,
    run: str,
) -> None:
    """Create a func-only session (no anat dir) with all FileFinder-required files."""
    base = f'{subject}_{session}_task-{task}_{run}'

    bids_func = bids / subject / session / 'func'
    bids_func.mkdir(parents=True, exist_ok=True)
    (bids_func / f'{base}_events.tsv').write_text(
        'onset\tduration\ttrial_type\n0\t1\tcue\n'
    )

    fp_func = fmriprep / subject / session / 'func'
    fp_func.mkdir(parents=True, exist_ok=True)
    for suffix in (
        'desc-confounds_timeseries.tsv',
        'space-T1w_desc-preproc_bold.nii.gz',
        'space-T1w_desc-brain_mask.nii.gz',
        'space-MNI152NLin2009cAsym_res-2_desc-preproc_bold.nii.gz',
        'space-MNI152NLin2009cAsym_res-2_desc-brain_mask.nii.gz',
    ):
        (fp_func / f'{base}_{suffix}').write_text('mock')


def test_find_anat_dir_resolves_cross_session_for_s19(tmp_path: Path) -> None:
    """sub-s19's chosen anat lives in ses-05 even though BOLDs run in ses-01.

    Mirrors the on-disk derivatives:
        derivatives/fmriprep_25.2.4/sub-s19/ses-05/anat/...preproc_T1w.nii.gz
        derivatives/fmriprep_25.2.4/sub-s19/ses-01/func/...
    No anat dir exists under ses-01.
    """
    fmriprep = tmp_path / 'fmriprep_25.2.4'
    bids = tmp_path / 'bids'
    subject = 'sub-s19'

    # Anat in ses-05 only.
    anat_dir = _make_anat_session(fmriprep, subject, 'ses-05')
    # BOLDs in ses-01 with no anat dir.
    _make_func_session(bids, fmriprep, subject, 'ses-01', 'rest', 'run-1')

    resolved = find_anat_dir(fmriprep, subject)
    assert resolved == anat_dir
    # And we can pull both the T1w reference and the MNI->T1w transform
    # out of the session that actually has them.
    t1w_ref = find_t1w_reference(resolved)
    assert t1w_ref.name.endswith('_desc-preproc_T1w.nii.gz')
    assert 'ses-05' in t1w_ref.parts

    xfm = find_mni_to_t1w_transform(resolved)
    assert xfm.name.endswith('_from-MNI152NLin2009cAsym_to-T1w_mode-image_xfm.h5')
    assert 'ses-05' in xfm.parts


@pytest.mark.parametrize(
    'subject,anat_session,bold_session', CROSS_SESSION_CASES
)
def test_find_anat_dir_per_subject_real_session(
    tmp_path: Path, subject: str, anat_session: str, bold_session: str
) -> None:
    """Each documented discovery subject's chosen anat is resolved correctly.

    Builds the real-world layout (anat only in fmriprep's chosen session,
    BOLDs in a different session with no anat dir) and confirms the resolver
    returns the correct anat session.
    """
    fmriprep = tmp_path / subject / 'fmriprep_25.2.4'
    bids = tmp_path / subject / 'bids'

    expected_anat = _make_anat_session(fmriprep, subject, anat_session)
    _make_func_session(bids, fmriprep, subject, bold_session, 'rest', 'run-1')

    resolved = find_anat_dir(fmriprep, subject)
    assert resolved == expected_anat, (
        f'{subject}: expected anat at {expected_anat}, got {resolved}'
    )
    assert anat_session in resolved.parts
    assert bold_session not in resolved.parts


def test_find_anat_dir_skips_anat_only_sessions_without_t1w(tmp_path: Path) -> None:
    """An earlier session whose anat dir has only T2w (no T1w) is skipped.

    Mirrors the docstring of ``find_anat_dir``: a subject may have multiple
    anat dirs across sessions; only the one with ``*desc-preproc_T1w.nii.gz``
    is returned.
    """
    fmriprep = tmp_path / 'fmriprep_25.2.4'
    subject = 'sub-s19'

    # ses-01 has anat dir but only a T2w.
    decoy = fmriprep / subject / 'ses-01' / 'anat'
    decoy.mkdir(parents=True)
    (decoy / f'{subject}_ses-01_desc-preproc_T2w.nii.gz').write_text('mock')

    # ses-05 has the real T1w.
    real = _make_anat_session(fmriprep, subject, 'ses-05')

    resolved = find_anat_dir(fmriprep, subject)
    assert resolved == real
    assert resolved != decoy


def test_filefinder_does_not_filter_bold_for_missing_anat(tmp_path: Path) -> None:
    """Lev1 BOLD discovery in a session without anat must still surface the run.

    FileFinder's ``t1w_data`` is the BOLD resampled into T1w space, NOT the
    anatomical T1w. A subject whose chosen anat is in a different session
    must still get every per-run BOLD file even though the BOLD's session
    has no ``anat/`` directory at all.
    """
    fmriprep = tmp_path / 'fmriprep_25.2.4'
    bids = tmp_path / 'bids'
    subject = 'sub-s19'

    # Anat lives in ses-05; BOLD lives in ses-01 with no anat dir alongside.
    _make_anat_session(fmriprep, subject, 'ses-05')
    _make_func_session(bids, fmriprep, subject, 'ses-01', 'rest', 'run-1')
    assert not (fmriprep / subject / 'ses-01' / 'anat').exists()

    finder = FileFinder(bids_dir=bids, fmriprep_dir=fmriprep)
    files = finder.get_files('s19', 'rest')

    assert 'ses-01' in files, (
        f'BOLD session ses-01 missing from result; got {sorted(files)}'
    )
    run_files = files['ses-01']['run-1']
    for ftype in (
        'events',
        'confounds',
        't1w_data',
        't1w_brain_mask',
        'mni_data',
        'mni_brain_mask',
    ):
        assert ftype in run_files, (
            f'{ftype} missing from ses-01/run-1 even though only anat is in ses-05'
        )
        # BOLD-side paths must reference the BOLD session, not the anat session.
        assert 'ses-01' in str(run_files[ftype])
        assert 'ses-05' not in str(run_files[ftype])


def test_filefinder_does_not_invent_anat_session_runs(tmp_path: Path) -> None:
    """The anat-only session must NOT appear in FileFinder's BOLD output.

    fmriprep emits an anat dir under ses-05 for sub-s19 but no BOLD for
    that session. FileFinder is BOLD-centric and must report only sessions
    with task data.
    """
    fmriprep = tmp_path / 'fmriprep_25.2.4'
    bids = tmp_path / 'bids'
    subject = 'sub-s19'

    _make_anat_session(fmriprep, subject, 'ses-05')
    _make_func_session(bids, fmriprep, subject, 'ses-01', 'rest', 'run-1')

    finder = FileFinder(bids_dir=bids, fmriprep_dir=fmriprep)
    files = finder.get_files('s19', 'rest')

    assert 'ses-05' not in files, (
        'anat-only session must not appear as a BOLD session — got '
        f'{sorted(files)}'
    )


def test_find_anat_dir_raises_when_no_t1w_anywhere(tmp_path: Path) -> None:
    """Defensive: every session lacks a T1w => clear FileNotFoundError."""
    fmriprep = tmp_path / 'fmriprep_25.2.4'
    subject = 'sub-s19'
    # Only a func session, no anat anywhere.
    (fmriprep / subject / 'ses-01' / 'func').mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match='No anat directory'):
        find_anat_dir(fmriprep, subject)
