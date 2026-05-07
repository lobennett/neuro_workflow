"""Cohort-level outlier QC for lev1 contrast maps.

Mirrors Jeanette Mumford's fmri-outlier-detector/run_network.py against
our lev1 output paths. Single file, plain functions + frozen dataclasses,
≤300 lines (per the spec's code-style guardrails).

Public API:
    detect_lev1_outliers(*, lev1_dirs, output_dir, ...) -> None

Computes per-voxel cohort mean/SD for each (task, contrast) group,
flags voxels >n_std SD from the mean, aggregates per-(subject, contrast)
outlier %, reads the per-contrast VIF CSVs lev1 already emits, writes:
    - lev1_outliers.csv     (one row per scan-contrast)
    - lev1_outliers.pdf     (Jeanette-style: panels + histograms)
    - lev1_flagged.tsv      (subset where any flag fires)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# BIDS-style entity parser for our lev1 output filenames.
# The contrast field may contain underscores (e.g. "stop_success-go"),
# so we match it non-greedily up to the next BIDS entity (_rtmodel- or _stat-).
_FILENAME_RE = re.compile(
    r"^(?P<subject>sub-[A-Za-z0-9]+)"
    r"_(?P<session>ses-[A-Za-z0-9]+)"
    r"_task-(?P<task>[A-Za-z0-9]+)"
    r"_run-(?P<run>\d+)"
    r"_contrast-(?P<contrast>.+?)"
    r"(?:_rtmodel-[A-Za-z0-9_]+?)?"
    r"_stat-effect-size\.nii\.gz$"
)


@dataclass(frozen=True)
class ScanContrast:
    """One (subject, session, run, task, contrast) tuple."""
    subject: str
    session: str
    task: str
    run: str
    contrast: str
    path: Path


def parse_contrast_path(path: Path) -> ScanContrast:
    """Parse one stat-effect-size NIfTI path into a ScanContrast.

    Raises ValueError if the filename doesn't match the expected pattern.
    """
    m = _FILENAME_RE.match(path.name)
    if not m:
        raise ValueError(f"unrecognized contrast filename: {path.name}")
    return ScanContrast(
        subject=m.group("subject"),
        session=m.group("session"),
        task=m.group("task"),
        run=m.group("run"),
        contrast=m.group("contrast"),
        path=path,
    )


def discover_contrast_files(
    lev1_dirs: list[Path],
    *,
    glob_pattern: str = "sub-s*/task-*/indiv_contrasts/*stat-effect-size.nii.gz",
) -> list[Path]:
    """Find all contrast effect-size NIfTIs across the given lev1 output dirs."""
    out: list[Path] = []
    for d in lev1_dirs:
        out.extend(d.glob(glob_pattern))
    return sorted(out)
