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
                      excluded_keys: set, *, min_runs: int = 2) -> set:
    """Deterministic model: (BIDS runs - excluded - rest/no-events) >= min_runs
    -> expand over task contrasts. excluded_keys are bare-task 4-tuples
    (subject, session, task, run)."""
    from neuro_workflow.analysis.io.file_discovery import FileFinder
    from neuro_workflow.analysis.task_config.loader import get_task_contrasts

    finder = FileFinder(str(bids_dir), str(fmriprep_dir))
    out = set()
    for sub in subjects:
        for task in tasks:
            if task == "rest":
                continue
            files = finder.get_files(
                sub, task, required_files=FileFinder.get_required_files_for_space("MNI"))
            n = 0
            for ses, runs in files.items():
                for run in runs:
                    if (sub, ses, task, run) in excluded_keys:
                        continue
                    n += 1
            if n < min_runs:
                continue
            for contrast in get_task_contrasts(task):
                out.add((sub, task, contrast))
    return out
