"""Symlink real (small) metric inputs into the stub tree for the generators."""
from __future__ import annotations
from pathlib import Path
from typing import Optional


def _link(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    dst.symlink_to(Path(src).resolve())
    return dst


def stage_metrics(bids_dir: Path, *, fmriprep_src: Path, version: str,
                  behavioral_src: Optional[Path] = None) -> dict:
    """Symlink the fMRIPrep derivative (+ optional behavioral sourcedata) into the
    stub tree. lev1_outliers.csv is passed to its generator by path, not staged here.
    Returns {kind: linked_path}."""
    out = {}
    out["fmriprep"] = _link(fmriprep_src, bids_dir / "derivatives" / f"fmriprep_{version}")
    if behavioral_src is not None:
        out["behavioral"] = _link(behavioral_src, bids_dir / "sourcedata" / "in_scanner_behavior")
    return out
