"""Helpers for converting iProc fsaverage6 rest surfaces into MSHBM inputs.

iProc's ``filter_and_project`` stage already projects each rest run to
fsaverage6 and writes a FreeSurfer surface-overlay NIfTI, e.g.::

    FS6/<ses>/REST_<run>/lh.<ses>_bld<run>_tedana_bpss_fsaverage6_sm0p0.nii.gz

These are already bandpass-filtered + multi-echo-denoised rest time series in
the exact target space MSHBM consumes — only the on-disk *layout* differs from
what the CBIG MATLAB code expects:

* FreeSurfer folds the 40962-vertex fsaverage6 vector into a ``(13654, 1, 3, T)``
  volume (column-major: ``40962 == 13654 * 3``).
* CBIG ``MRIread`` + ``reshape(vol, [], T)`` flattens the first three dims back
  to ``(40962, T)``. The canonical on-disk form the lab's other adapters
  (``from_xcpd``) write is ``(40962, 1, 1, T)``.

This module canonicalises the fold in pure Python (column-major reshape), which
is byte-identical to round-tripping through an identity ``mri_surf2surf`` but
needs no FreeSurfer. NaNs are zeroed to match the single medial-wall sentinel
convention used by ``from_xcpd`` (CBIG applies its own fsaverage6 cortex mask,
so medial-wall values are ignored downstream regardless).

Pure-Python utilities only — orchestration lives in
``scripts/mshbm_inputs_from_iproc.py`` to keep this module easy to test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import nibabel as nib
import numpy as np

FSAVERAGE6_NVERTICES = 40962

HEMI_MAP = {"lh": "lh", "rh": "rh"}

# iProc rest surface: lh.01_bld004_tedana_bpss_fsaverage6_sm0p0.nii.gz
_IPROC_SURF_RE = re.compile(
    r"^(?P<hemi>lh|rh)\.(?P<ses>\d+)_bld(?P<run>\d+)_"
    r"tedana_bpss_fsaverage6_sm0p0\.nii\.gz$"
)


@dataclass(frozen=True)
class IprocScan:
    """One run (task or rest) for one subject, both hemispheres.

    ``session`` / ``run`` are the zero-padded iProc tokens (e.g. ``"01"``,
    ``"004"``). ``task`` is the iProc cell label (e.g. ``"REST"``, ``"FLANKER"``)
    derived from the cell directory name. ``lh_path`` / ``rh_path`` point at the
    iProc fsaverage6 NIfTIs.
    """

    session: str
    run: str
    task: str
    lh_path: Path
    rh_path: Path


@dataclass(frozen=True)
class IprocRestScan:
    """One rest run for one subject, both hemispheres.

    ``session`` / ``run`` are the zero-padded iProc tokens (e.g. ``"01"``,
    ``"004"``). ``lh_path`` / ``rh_path`` point at the iProc fsaverage6 NIfTIs.
    """

    session: str
    run: str
    lh_path: Path
    rh_path: Path


def make_mshbm_name(hemi: str, session: str, run: str, task: str = "rest") -> str:
    """Build the MSHBM-compatible filename for one hemi of one run.

    The CBIG ``MSHBM_wrapper`` globs ``{lh,rh}*fsaverage6_sm*.nii.gz`` and (in
    group-by-session mode) parses a ``_ses-NN_`` token, so the output name keeps
    both. The ``nat_resid_bpss`` infix matches the lab's established
    ``prepare_mshbm_inputs`` convention so iProc- and fMRIPrep-derived inputs are
    interchangeable in the wrapper.

    ``task`` defaults to ``"rest"`` for back-compatibility with rest-only callers;
    pass the lowercased iProc cell label (e.g. ``"flanker"``) for task runs.

    Input  tokens: hemi='lh', session='01', run='004', task='rest'
    Output:        lh_ses-01_task-rest_run-004_nat_resid_bpss_fsaverage6_sm0.nii.gz
    """
    if hemi not in HEMI_MAP:
        raise ValueError(f"Unexpected hemi {hemi!r}; expected 'lh' or 'rh'")
    return (
        f"{hemi}_ses-{session}_task-{task}_run-{run}"
        f"_nat_resid_bpss_fsaverage6_sm0.nii.gz"
    )


def discover_iproc_scans(iproc_subject_root: Path) -> list[IprocScan]:
    """Find all task+rest runs under an iProc subject's ``FS6`` tree.

    Args:
        iproc_subject_root: iProc subject dir, i.e. ``.../mri_data/<subj>``
            (the dir that contains ``FS6/<ses>/<TASK>_<run>/``).

    Returns one :class:`IprocScan` per (session, run) that has *both*
    hemispheres present, sorted by (session, run). The ``task`` label is derived
    from the cell directory name (``FLANKER_009`` -> ``FLANKER``). A run missing
    its rh mate is skipped (the caller logs it).
    """
    fs6_root = Path(iproc_subject_root) / "FS6"
    pairs: dict[tuple[str, str], dict[str, object]] = {}
    for surf in fs6_root.glob("*/*/lh.*_tedana_bpss_fsaverage6_sm0p0.nii.gz"):
        m = _IPROC_SURF_RE.match(surf.name)
        if not m:
            continue
        key = (m.group("ses"), m.group("run"))
        entry = pairs.setdefault(key, {})
        entry["lh"] = surf
        entry["task"] = surf.parent.name.rsplit("_", 1)[0]
    for surf in fs6_root.glob("*/*/rh.*_tedana_bpss_fsaverage6_sm0p0.nii.gz"):
        m = _IPROC_SURF_RE.match(surf.name)
        if not m:
            continue
        key = (m.group("ses"), m.group("run"))
        entry = pairs.setdefault(key, {})
        entry["rh"] = surf
        entry["task"] = surf.parent.name.rsplit("_", 1)[0]

    scans: list[IprocScan] = []
    for (ses, run), entry in sorted(pairs.items()):
        if "lh" in entry and "rh" in entry:
            scans.append(
                IprocScan(session=ses, run=run, task=entry["task"],
                          lh_path=entry["lh"], rh_path=entry["rh"])
            )
    return scans


def discover_iproc_rest(iproc_subject_root: Path) -> list[IprocRestScan]:
    """Find all rest runs under an iProc subject's ``FS6`` tree.

    Thin filter over :func:`discover_iproc_scans` keeping only ``REST`` cells.

    Args:
        iproc_subject_root: iProc subject dir, i.e. ``.../mri_data/<subj>``
            (the dir that contains ``FS6/<ses>/REST_<run>/``).

    Returns one :class:`IprocRestScan` per (session, run) that has *both*
    hemispheres present, sorted by (session, run). A run missing its rh mate is
    skipped (the caller logs it).
    """
    return [
        IprocRestScan(session=s.session, run=s.run,
                      lh_path=s.lh_path, rh_path=s.rh_path)
        for s in discover_iproc_scans(iproc_subject_root)
        if s.task == "REST"
    ]


def iproc_surf_to_mshbm_nifti(in_path: Path, out_path: Path) -> Path:
    """Canonicalise an iProc fsaverage6 overlay NIfTI to ``(V, 1, 1, T)``.

    iProc writes ``(13654, 1, 3, T)``; this column-major-reshapes the first
    three axes back to the 40962-vertex vector (the exact order FreeSurfer used
    to fold it) and writes ``(40962, 1, 1, T)`` — the canonical form CBIG MSHBM
    consumes. NaN/Inf are zeroed (single medial-wall sentinel).
    """
    img = nib.load(str(in_path))
    arr = np.asarray(img.dataobj, dtype=np.float32)
    nvox = int(np.prod(arr.shape[:3]))
    if nvox != FSAVERAGE6_NVERTICES:
        raise ValueError(
            f"{in_path.name}: first 3 dims multiply to {nvox}, "
            f"expected {FSAVERAGE6_NVERTICES} (fsaverage6)"
        )
    n_t = arr.shape[3] if arr.ndim == 4 else 1
    # Column-major (Fortran) flatten of the folded spatial dims == FreeSurfer's
    # vertex linear index; this inverts the (13654,1,3) fold exactly.
    flat = arr.reshape(nvox, n_t, order="F")
    flat = np.nan_to_num(flat, nan=0.0, posinf=0.0, neginf=0.0)
    out_4d = flat.reshape(nvox, 1, 1, n_t)
    out_img = nib.Nifti1Image(out_4d, affine=np.eye(4))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(out_img, str(out_path))
    return out_path
