"""Junk-trial exclusion generator — a pre-lev1, first-class version of lev1's
runtime ``percent_junk > 0.30`` QA fail.

Historically the "too many junk trials" decision was made only at lev1 runtime
(``run_quality_control`` sets ``any_fail=True`` when ``percent_junk`` exceeds the
cutoff) and was never recorded in the compiled exclusion set. This generator
lifts that decision to a compiled, auditable exclusion so the junk cut is
reproducible and visible in the lockfile / .bidsignore.

Parity contract
---------------
The junk fraction is computed with the *exact* preprocessing lev1 applies before
its junk check (see ``analysis/lev1/runner.py``):

    events_df = pd.read_csv(events_tsv, sep="\t")
    processed = preprocess_events(events_df, task, n_scans=n_scans, tr=tr)
    _, percent_junk = add_junk_trials(processed, task)

``n_scans`` is the number of BOLD timepoints lev1 saw — read here from the BIDS
BOLD's 4th dimension (the runtime surface/volume run has the same length, since
fMRIPrep is run with ``--dummy-scans 0`` on the pre-trimmed BOLD). It matters:
salvaged (short-BOLD) scans have trailing events dropped by ``preprocess_events``,
which changes the junk fraction; skipping it produces false positives.

The cutoff is read from :func:`neuro_workflow.core.thresholds.junk_fraction_max`
(the single source of truth, == 0.30), never hardcoded. A scan is flagged when
``percent_junk > junk_fraction_max()`` — the same strict ``>`` comparison lev1
uses.

Scoping mirrors the other generators: output is filtered to the dataset's
canonical roster via :func:`load_dataset_subjects` (fail-loud on unknown dataset).
"""

from __future__ import annotations

import logging
import re
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.exclusions.base import load_dataset_subjects, register_generator

logger = logging.getLogger(__name__)

# sub-<x>_ses-<y>_task-<t>_run-<r>_events.tsv  (entities are `_`-delimited).
_EVENTS_RE = re.compile(
    r"^sub-(?P<sub>[^_]+)_ses-(?P<ses>[^_]+)_task-(?P<task>[^_]+)_run-(?P<run>[^_]+)_events\.tsv$"
)


def _read_n_scans(func_dir: Path, stem: str) -> int | None:
    """Return the BOLD timepoint count for this run, or None if unavailable.

    ``stem`` is the BIDS run stem (the events filename without the trailing
    ``_events.tsv``), e.g. ``sub-s956_ses-04_task-cuedTS_run-1``.

    Prefers the multi-echo layout (``echo-*_bold.nii.gz``); falls back to a
    single ``_bold.nii.gz``. Picks the first file with a 4D shape. Returns None
    when no 4D BOLD exists (e.g. a stray 3D file) — the caller then computes the
    junk fraction over the full, un-truncated events (best effort pre-lev1).
    """
    import nibabel as nib

    candidates = sorted(func_dir.glob(f"{stem}_echo-*_bold.nii.gz")) or sorted(
        func_dir.glob(f"{stem}_bold.nii.gz")
    )
    for bold in candidates:
        try:
            shape = nib.load(str(bold)).shape
        except Exception as exc:  # noqa: BLE001 — a corrupt file must not abort the sweep
            logger.warning("junk_qc: could not read BOLD header %s: %s", bold, exc)
            continue
        if len(shape) >= 4:
            return int(shape[3])
    return None


class JunkQCGenerator:
    name = "junk_qc"
    description = (
        "Flag task scans whose junk-trial fraction exceeds the lev1 QA cutoff "
        "(thresholds.junk_fraction_max, default 0.30) — first-class version of "
        "lev1's runtime percent_junk QA fail"
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--bids-dir",
            required=False,
            default=None,
            help="Override the dataset's BIDS directory (default: dataset_config['bids_dir']).",
        )

    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]:
        try:
            import pandas as pd  # noqa: F401

            from neuro_workflow.analysis.lev1.processing.events import (
                add_junk_trials,
                preprocess_events,
            )
            from neuro_workflow.analysis.task_config.loader import get_task_parameters
        except ImportError as exc:
            print(
                "Error: junk_qc requires the analysis extras (pandas, nibabel, pyyaml). "
                f"Install with: uv pip install -e '.[events]' ({exc})"
            )
            return []

        import pandas as pd

        from neuro_workflow.core.thresholds import junk_fraction_max

        bids_override = getattr(args, "bids_dir", None)
        bids_dir = Path(bids_override) if bids_override else Path(dataset_config["bids_dir"])
        threshold = junk_fraction_max()

        # Fail-loud roster resolution; scope output to this dataset's subjects.
        roster = load_dataset_subjects(dataset_name)

        entries: list[dict] = []
        n_scanned = 0
        n_skipped_task = 0

        for events_tsv in sorted(bids_dir.glob("sub-*/ses-*/func/*_task-*_events.tsv")):
            # Never descend into derivatives/ or sourcedata/ trees.
            parts = set(events_tsv.parts)
            if "derivatives" in parts or "sourcedata" in parts:
                continue

            m = _EVENTS_RE.match(events_tsv.name)
            if not m:
                continue
            sub, ses, task, run = m["sub"], m["ses"], m["task"], m["run"]

            subject = f"sub-{sub}"
            if subject not in roster:
                continue
            if task == "rest":
                continue

            # tr exactly as lev1's runner resolves it: task_params["tr"].
            try:
                tr = get_task_parameters(task)["tr"]
            except Exception as exc:  # noqa: BLE001
                logger.warning("junk_qc: skipping %s (task params failed: %s)", events_tsv, exc)
                n_skipped_task += 1
                continue

            # Stem = events filename minus the trailing "_events.tsv"; the BOLD
            # files share this exact prefix (echo-*/plain). Deriving it from the
            # filename avoids re-formatting the BIDS entities (and double-prefix bugs).
            stem = events_tsv.name[: -len("_events.tsv")]
            n_scans = _read_n_scans(events_tsv.parent, stem)

            events_df = pd.read_csv(events_tsv, sep="\t")
            try:
                processed = preprocess_events(events_df, task, n_scans=n_scans, tr=tr)
                _, percent_junk = add_junk_trials(processed, task)
            except ValueError as exc:
                # Unknown task (define_nuisance_trials) or empty events — not a junk
                # signal; skip like lev1 would never have produced a junk fail.
                logger.warning("junk_qc: skipping %s (%s)", events_tsv, exc)
                n_skipped_task += 1
                continue

            n_scanned += 1
            if percent_junk > threshold:
                entries.append(
                    {
                        "subject": subject,
                        "session": f"ses-{ses}",
                        "task": task,  # bare task name (no `task-` prefix)
                        "run": f"run-{run}",
                        "action": "exclude",
                        "reason": (
                            f"junk_qc: junk {percent_junk:.1%} > {threshold:.0%} of relevant trials"
                        ),
                        "source": "junk_qc",
                        "metrics": {"percent_junk": float(percent_junk)},
                    }
                )

        entries.sort(key=lambda e: (e["subject"], e["session"], e["task"], e["run"]))
        print(
            f"junk_qc: {len(entries)} exclusion(s) over {n_scanned} task scan(s) "
            f"(threshold {threshold:.0%}; roster-scoped to {len(roster)} subjects of "
            f"dataset '{dataset_name}'; {n_skipped_task} scan(s) skipped)"
        )
        return entries


register_generator(JunkQCGenerator())
