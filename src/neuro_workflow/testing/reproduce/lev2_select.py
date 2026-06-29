"""Model the lev2-eligible {(subject,task,contrast)} set + the on-disk reference."""
from __future__ import annotations
import re
from pathlib import Path
from typing import Iterable

_FE_RE = re.compile(
    r"(?P<sub>sub-[^_/]+)_(?:hemi-[^_]+_)?(?:space-[^_]+_)?task-(?P<task>[^_]+)"
    r"_contrast-(?P<contrast>.+?)_rtmodel-[^_]+(?:_desc-belowMinRuns)?_stat-fixed-effects")


def lev2_reference_set(level1_dirs: Iterable[Path]) -> set:
    """Glob real fixed-effects maps lev2 consumes; drop _desc-belowMinRuns."""
    out = set()
    for d in level1_dirs:
        for f in Path(d).glob("sub-*/*/fixed_effects/*_stat-fixed-effects.nii.gz"):
            if "_desc-belowMinRuns" in f.name:
                continue
            m = _FE_RE.search(f.name)
            if m:
                out.add((m.group("sub"), m.group("task"), m.group("contrast")))
    return out


def lev2_eligible_set(bids_dir: Path, fmriprep_dir: Path, subjects, tasks,
                      excluded_keys: set, *, contrast_excluded: set | None = None,
                      min_runs: int = 2) -> set:
    """Deterministic model of the lev2-eligible {(subject, task, contrast)} set.

    A (subject, task, contrast) is eligible iff the number of BIDS runs that
    CONTRIBUTE to that contrast is >= ``min_runs``. A run does not contribute when
    either (a) the whole scan is excluded — ``(subject, session, task, run)`` in
    ``excluded_keys`` (scan-level exclude/trim) — or (b) that specific contrast is
    dropped for the run — ``(subject, session, task, run, contrast)`` in
    ``contrast_excluded`` (the per-contrast ``exclude-contrast`` action). This
    mirrors ``fixed_effects.find_contrast_files(contrast_exclusions=…)`` +
    ``--min-runs`` (below-floor maps are tagged ``_desc-belowMinRuns`` and filtered
    out of lev2), so the model matches the on-disk fixed-effects reference.

    ``excluded_keys`` are 4-tuples (subject, session, task, run); ``contrast_excluded``
    are 5-tuples (subject, session, task, run, contrast)."""
    from neuro_workflow.analysis.io.file_discovery import FileFinder
    from neuro_workflow.analysis.task_config.loader import get_task_contrasts

    contrast_excluded = contrast_excluded or set()
    finder = FileFinder(str(bids_dir), str(fmriprep_dir))
    out = set()
    for sub in subjects:
        for task in tasks:
            if task == "rest":
                continue
            files = finder.get_files(
                sub, task, required_files=FileFinder.get_required_files_for_space("MNI"))
            # Runs surviving scan-level exclusion (shared across all contrasts).
            scan_runs = [
                (ses, run)
                for ses, runs in files.items()
                for run in runs
                if (sub, ses, task, run) not in excluded_keys
            ]
            for contrast in get_task_contrasts(task):
                n = sum(
                    1 for (ses, run) in scan_runs
                    if (sub, ses, task, run, contrast) not in contrast_excluded
                )
                if n >= min_runs:
                    out.add((sub, task, contrast))
    return out
