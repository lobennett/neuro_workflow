"""Shared on-disk conventions for MSHBM inputs (naming + NIfTI marshalling).

Single source of truth (RF-6) for the MSHBM filename grammar, the lh/rh hemi
guard, and the canonical ``(V, 1, 1, T)`` NIfTI write that every source adapter
(``from_iproc``, ``from_fmriprep``, ``from_xcpd``) and their CLI drivers share.
Previously each of these was duplicated (and the filename grammar had drifted
between the iProc/fMRIPrep modules and the xcpd script).
"""
from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

HEMI_MAP = {"lh": "lh", "rh": "rh"}


def check_hemi(hemi: str) -> None:
    """Raise ``ValueError`` unless ``hemi`` is 'lh' or 'rh'."""
    if hemi not in HEMI_MAP:
        raise ValueError(f"Unexpected hemi {hemi!r}; expected 'lh' or 'rh'")


def make_mshbm_name(hemi: str, session: str, run: str, task: str = "rest") -> str:
    """Build the MSHBM-compatible filename for one hemi of one run.

    The CBIG ``MSHBM_wrapper`` globs ``{lh,rh}*fsaverage6_sm*.nii.gz`` and (in
    group-by-session mode) parses a ``_ses-NN_`` token, so the name keeps both.
    The ``nat_resid_bpss`` infix matches the lab's ``prepare_mshbm_inputs``
    convention so iProc-, fMRIPrep- and XCP-D-derived inputs are interchangeable.

    ``task`` defaults to ``"rest"`` for rest-only callers; pass the lowercased
    task label for task runs.

        make_mshbm_name('lh', '01', '004', 'rest')
        -> 'lh_ses-01_task-rest_run-004_nat_resid_bpss_fsaverage6_sm0.nii.gz'
    """
    check_hemi(hemi)
    return (
        f"{hemi}_ses-{session}_task-{task}_run-{run}"
        f"_nat_resid_bpss_fsaverage6_sm0.nii.gz"
    )


def write_mshbm_nifti(arr_vt: np.ndarray, out_path: Path) -> Path:
    """Write a ``(V, T)`` surface array as the canonical ``(V, 1, 1, T)`` MSHBM NIfTI.

    NaN/Inf are zeroed (the single medial-wall sentinel CBIG ignores via its own
    cortex mask), an identity affine is used, and parent dirs are created.
    Returns ``out_path``.
    """
    arr = np.nan_to_num(np.asarray(arr_vt), nan=0.0, posinf=0.0, neginf=0.0)
    n_v, n_t = arr.shape
    out_img = nib.Nifti1Image(arr.reshape(n_v, 1, 1, n_t), affine=np.eye(4))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(out_img, str(out_path))
    return out_path
