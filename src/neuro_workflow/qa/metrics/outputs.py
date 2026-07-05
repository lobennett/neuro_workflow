"""Check presence of expected fmriprep output files for a given scan."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ScanID:
    subject: str
    session: str
    task: str
    run: str


@dataclass
class OutputCheckResult:
    complete: bool
    missing: list[str] = field(default_factory=list)


_EXPECTED_SUFFIXES: list[str] = [
    "{base}_desc-preproc_bold.nii.gz",
    "{base}_space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz",
    "{base}_space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz",
    "{base}_space-T1w_desc-preproc_bold.nii.gz",
    "{base}_hemi-L_space-fsaverage6_bold.func.gii",
    "{base}_hemi-R_space-fsaverage6_bold.func.gii",
    "{base}_hemi-L_space-fsnative_bold.func.gii",
    "{base}_hemi-R_space-fsnative_bold.func.gii",
    "{base}_space-fsLR_den-91k_bold.dtseries.nii",
    "{base}_desc-confounds_timeseries.tsv",
]


def check_expected_outputs(fmriprep_dir: Path, scan: ScanID) -> OutputCheckResult:
    """Verify all expected output files exist for the given scan.

    Searches:
        <fmriprep_dir>/<subject>/<session>/func/<base>_<suffix>

    Returns:
        OutputCheckResult with complete=True when all files exist, otherwise
        complete=False and a list of missing filenames (relative to func dir).
    """
    base = f"{scan.subject}_{scan.session}_task-{scan.task}_run-{scan.run}"
    func_dir = fmriprep_dir / scan.subject / scan.session / "func"
    missing = [
        suffix.format(base=base)
        for suffix in _EXPECTED_SUFFIXES
        if not (func_dir / suffix.format(base=base)).is_file()
    ]
    return OutputCheckResult(complete=not missing, missing=missing)
