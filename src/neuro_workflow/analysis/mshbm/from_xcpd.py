"""Helpers for converting XCP-D denoised CIFTI outputs into MSHBM fsaverage6 NIfTIs.

Pure-Python utilities — wb_command orchestration lives in
``scripts/mshbm_from_xcpd.py`` to keep this module easy to test.
"""
from __future__ import annotations

from pathlib import Path
