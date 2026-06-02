"""fsaverage6 surface smoothing marshalling for MSHBM inputs.

Pure array<->GIFTI helpers; the actual wb_command -metric-smoothing call lives
in the driver scripts (per the module/script split convention used across the
mshbm package).
"""
from __future__ import annotations

from pathlib import Path

import nibabel as nib
import numpy as np

FWHM_2MM_SIGMA = 2.0 / 2.3548200450309493  # FWHM(mm) -> Gaussian sigma(mm)


def array_to_func_gii(arr: np.ndarray, out_path: Path) -> Path:
    """Write (V, T) float32 as a .func.gii (one DataArray per column)."""
    arr = np.asarray(arr, dtype=np.float32)
    darrays = [
        nib.gifti.GiftiDataArray(
            arr[:, t].copy(), intent="NIFTI_INTENT_TIME_SERIES"
        )
        for t in range(arr.shape[1])
    ]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    nib.save(nib.gifti.GiftiImage(darrays=darrays), str(out_path))
    return out_path


def func_gii_to_array(path: Path) -> np.ndarray:
    """Load a .func.gii to (V, T) float32."""
    g = nib.load(str(path))
    return np.stack([d.data.astype(np.float32) for d in g.darrays], axis=-1)
