"""Collection exclusion generator.

Folds the committed, human-curated data-collection exclusions
(``data/exclusions/{dataset}_collection.bidsignore``) into the compiled
exclusion set, so the incomplete-acquisition / <50%-TR / irreconcilable-BOLD /
onset-break scans gate lev1 (the compiled layer) and not only fMRIPrep (the
``.bidsignore`` layer). Previously the collection layer lived ONLY in the
rendered ``.bidsignore``; a scan whose fMRIPrep derivatives predate its
collection exclusion would slip through the lev1 gate.

Only functional-BOLD glob lines are ingested. Each is expanded against the BIDS
directory into concrete per-scan entries (``run-*`` -> every real run;
multi-echo files deduped to one entry per scan). Anatomical / wildcard-subject
lines (``anat/``, ``*_T1w.*``, ``sub-*/...``) are skipped: they affect fMRIPrep
anatomical selection, not the lev1 BOLD-scan gate.
"""

from __future__ import annotations

import re
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.exclusions_render import collection_path
from neuro_workflow.exclusions.base import load_dataset_subjects, register_generator

# A functional-BOLD collection glob line, e.g.
#   sub-s03/ses-01/func/sub-s03_ses-01_task-nBack_run-*_echo-*_bold.*
_FUNC_GLOB_RE = re.compile(
    r"^sub-(?P<subject>[A-Za-z0-9]+)/ses-(?P<session>[A-Za-z0-9]+)/func/"
    r"sub-(?P=subject)_ses-(?P=session)_task-(?P<task>[A-Za-z0-9]+)"
    r"_run-(?P<run>[A-Za-z0-9*]+)_echo-[^/]*_bold\.[^/]*$"
)

# A real multi-echo BOLD filename on disk (tolerant of intervening entities,
# see exclusions.qa_decisions for the same multi-echo handling).
_BOLD_FILE_RE = re.compile(
    r"^(?P<subject>sub-[A-Za-z0-9]+)_(?P<session>ses-[A-Za-z0-9]+)"
    r"_task-(?P<task>[A-Za-z0-9]+)_run-(?P<run>[A-Za-z0-9]+)"
    r"(?:_[A-Za-z0-9]+-[A-Za-z0-9]+)*_bold\.nii\.gz$"
)


def _expand_glob_to_entries(
    subject: str,
    session: str,
    task: str,
    run_token: str,
    reason: str,
    bids_dir: Path,
) -> list[dict]:
    """Expand one func collection glob to one entry per (sub, ses, task, run).

    run_token is a concrete run ("1") or "*" (all runs). Multi-echo BOLD files
    collapse to a single entry per scan.
    """
    sub = f"sub-{subject}"
    ses = f"ses-{session}"
    pattern = f"{sub}_{ses}_task-{task}_run-{run_token}_echo-*_bold.nii.gz"
    seen: set[tuple[str, str, str, str]] = set()
    out: list[dict] = []
    for bold in (bids_dir / sub / ses / "func").glob(pattern):
        m = _BOLD_FILE_RE.match(bold.name)
        if not m:
            continue
        key = (
            m.group("subject"),
            m.group("session"),
            f"task-{m.group('task')}",
            f"run-{m.group('run')}",
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "subject": key[0],
                "session": key[1],
                "task": key[2],
                "run": key[3],
                "source": "collection",
                "action": "exclude",
                "reason": reason,
            }
        )
    return out


class CollectionGenerator:
    name = "collection"
    description = (
        "Ingest the committed human-curated {dataset}_collection.bidsignore "
        "func-BOLD exclusions into the compiled set (expanded per scan via BIDS "
        "glob). Anatomical / wildcard-subject lines are skipped."
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        # No extra CLI args: the committed collection file is the input.
        pass

    def generate(
        self,
        dataset_name: str,
        dataset_config: dict,
        args: Namespace,
    ) -> list[dict]:
        path = collection_path(dataset_name)
        if not path.is_file():
            print(f"collection: no committed collection file at {path}; 0 entries")
            return []

        sample = load_dataset_subjects(dataset_name)
        bids_dir = Path(dataset_config["bids_dir"])

        entries: list[dict] = []
        n_func = n_skipped = n_expanded = 0
        last_comment: str | None = None

        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                last_comment = line.lstrip("#").strip()
                continue
            m = _FUNC_GLOB_RE.match(line)
            if not m:
                # anat / wildcard-subject / other: not a lev1 BOLD-scan gate.
                n_skipped += 1
                continue
            n_func += 1
            if f"sub-{m.group('subject')}" not in sample:
                continue
            reason = (
                f"collection: {last_comment}"
                if last_comment
                else "collection: data-collection exclusion"
            )
            expanded = _expand_glob_to_entries(
                m.group("subject"),
                m.group("session"),
                m.group("task"),
                m.group("run"),
                reason,
                bids_dir,
            )
            entries.extend(expanded)
            n_expanded += len(expanded)

        # Dedupe across collection lines (overlapping run-* / run-1 lines).
        uniq: dict[tuple, dict] = {}
        for e in entries:
            uniq[(e["subject"], e["session"], e["task"], e["run"])] = e
        entries = sorted(
            uniq.values(),
            key=lambda e: (e["subject"], e["session"], e["task"], e["run"]),
        )

        print(
            f"collection: {len(entries)} excluded "
            f"({n_expanded} expanded from {n_func} func lines), "
            f"{n_skipped} non-func lines skipped"
        )
        return entries


register_generator(CollectionGenerator())
