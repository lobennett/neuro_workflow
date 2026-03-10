"""Query Flywheel for subjects and sessions, merging aliases."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def collect_subject_sessions(
    canonical_label: str,
    all_subjects: list[Any],
    aliases: dict[str, str],
) -> list[dict[str, Any]]:
    """Collect all sessions for a canonical subject, merging aliased labels.

    Returns list of dicts sorted by timestamp:
        {fw_subject, fw_session, timestamp, acquisitions}
    """
    # Build set of FW labels that map to this canonical label
    matching_labels = {canonical_label}
    for variant, canon in aliases.items():
        if canon == canonical_label:
            matching_labels.add(variant)

    sessions: list[dict[str, Any]] = []
    for subj in all_subjects:
        if subj.label not in matching_labels:
            continue
        for sess in subj.sessions():
            sessions.append(
                {
                    "fw_subject": subj,
                    "fw_session": sess,
                    "timestamp": sess.timestamp,
                    "acquisitions": sess.acquisitions(),
                }
            )

    sessions.sort(key=lambda s: s["timestamp"])
    return sessions


def build_session_timeline(
    sessions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add sequential 'bids_session' labels (ses-01, ses-02, ...) to session dicts."""
    for idx, sess in enumerate(sessions, start=1):
        sess["bids_session"] = f"ses-{idx:02d}"
    return sessions


def query_project_subjects(
    fw_client: Any,
    project_label: str,
) -> tuple[list[Any], Any]:
    """Look up a Flywheel project and return (subjects, project).

    Raises ValueError if the project is not found.
    """
    project = fw_client.projects.find_first(f'label="{project_label}"')
    if project is None:
        raise ValueError(f"Project '{project_label}' not found")
    subjects = project.subjects()
    return subjects, project
