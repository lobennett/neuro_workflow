"""Select the correct NIfTI/JSON files from duplicate Flywheel gear outputs."""

import logging
import re

logger = logging.getLogger(__name__)


def _is_nifti(f):
    return f.name.endswith(".nii.gz")


def _is_json(f):
    return f.name.endswith(".json") and f.type == "source code"


def _is_bval(f):
    return f.name.endswith(".bval")


def _is_bvec(f):
    return f.name.endswith(".bvec")


def _skip_file(f):
    return f.type in ("dicom", "qa", "montage", "pfile")


def _echo_number(filename):
    """Extract echo number from filename like '*_e2.nii.gz' or '*_e2.json'."""
    m = re.search(r"_e(\d+)(?:\.|_)", filename)
    return int(m.group(1)) if m else None


def _resolve_duplicate_file(candidates):
    """When a gear produces multiple copies of the same file, pick the latest."""
    return max(candidates, key=lambda f: f.created or "")


def select_files(files, modality):
    """Select the correct files for a given modality from a Flywheel acquisition.

    Args:
        files: List of Flywheel file objects from an acquisition
        modality: One of "func", "fmap", "anat", "dwi"

    Returns:
        For func: list of dicts with keys {echo, nifti, json}
        For fmap: dict with keys {fieldmap_nifti, fieldmap_json, magnitude_nifti}
        For anat: dict with keys {nifti, json}
        For dwi: dict with keys {nifti, json, bval, bvec}
    """
    files = [f for f in files if not _skip_file(f)]

    if modality == "func":
        return _select_multiecho(files)
    elif modality == "fmap":
        return _select_fieldmap(files)
    elif modality == "anat":
        return _select_single(files)
    elif modality == "dwi":
        return _select_dwi(files)
    else:
        raise ValueError(f"Unknown modality: {modality}")


def _select_multiecho(files):
    """Select multi-echo BOLD files (_e1, _e2, _e3)."""
    niftis = [f for f in files if _is_nifti(f)]
    jsons = [f for f in files if _is_json(f)]

    echo_niftis = {}
    for f in niftis:
        echo = _echo_number(f.name)
        if echo is None:
            continue
        echo_niftis.setdefault(echo, []).append(f)

    echo_jsons = {}
    for f in jsons:
        echo = _echo_number(f.name)
        if echo is None:
            continue
        echo_jsons.setdefault(echo, []).append(f)

    results = []
    for echo in sorted(echo_niftis.keys()):
        nifti_candidates = echo_niftis[echo]
        json_candidates = echo_jsons.get(echo, [])

        nifti = _resolve_duplicate_file(nifti_candidates)
        json_file = _resolve_duplicate_file(json_candidates) if json_candidates else None

        if len(nifti_candidates) > 1:
            sizes = {f.size for f in nifti_candidates}
            if len(sizes) > 1:
                logger.warning(
                    "Echo %d has duplicates with different sizes: %s",
                    echo, [(f.name, f.size) for f in nifti_candidates],
                )

        results.append({"echo": echo, "nifti": nifti, "json": json_file})

    return results


def _select_fieldmap(files):
    """Select fieldmap + magnitude pair."""
    niftis = [f for f in files if _is_nifti(f)]
    jsons = [f for f in files if _is_json(f)]

    fieldmap_nifti = None
    magnitude_nifti = None
    fieldmap_json = None

    for f in niftis:
        if "_fieldmap" in f.name:
            fieldmap_nifti = f
        else:
            magnitude_nifti = f

    for f in jsons:
        if "_fieldmap" in f.name:
            fieldmap_json = f

    return {
        "fieldmap_nifti": fieldmap_nifti,
        "fieldmap_json": fieldmap_json,
        "magnitude_nifti": magnitude_nifti,
    }


def _select_single(files):
    """Select single NIfTI + JSON for anat."""
    niftis = [f for f in files if _is_nifti(f)]
    jsons = [f for f in files if _is_json(f)]

    nifti = _resolve_duplicate_file(niftis) if niftis else None
    json_file = _resolve_duplicate_file(jsons) if jsons else None

    return {"nifti": nifti, "json": json_file}


def _select_dwi(files):
    """Select NIfTI + JSON + bval + bvec for diffusion."""
    niftis = [f for f in files if _is_nifti(f)]
    jsons = [f for f in files if _is_json(f)]
    bvals = [f for f in files if _is_bval(f)]
    bvecs = [f for f in files if _is_bvec(f)]

    return {
        "nifti": _resolve_duplicate_file(niftis) if niftis else None,
        "json": _resolve_duplicate_file(jsons) if jsons else None,
        "bval": _resolve_duplicate_file(bvals) if bvals else None,
        "bvec": _resolve_duplicate_file(bvecs) if bvecs else None,
    }
