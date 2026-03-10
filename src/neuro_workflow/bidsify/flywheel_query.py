"""Query Flywheel for subjects and sessions, merging aliases."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def collect_subject_sessions(
    canonical_label: str,
    all_subjects: list[Any],
    aliases: dict[str, str],
    session_overrides: dict[str, dict] | None = None,
) -> list[dict[str, Any]]:
    """Collect all sessions for a canonical subject, merging aliased labels.

    Args:
        canonical_label: The canonical subject label (e.g. "s10").
        all_subjects: All FW subject objects in the project.
        aliases: Mapping of variant label -> canonical label.
        session_overrides: Optional nested dict keyed by FW subject label,
            then session label. Each value is a dict with either
            ``{"exclude": true}`` or ``{"reassign_to": "<subject>"}``
            plus an optional ``"reason"`` string.

    Returns list of dicts sorted by timestamp:
        {fw_subject, fw_session, timestamp, acquisitions}
    """
    overrides = session_overrides or {}

    # Build set of FW labels that map to this canonical label
    matching_labels = {canonical_label}
    for variant, canon in aliases.items():
        if canon == canonical_label:
            matching_labels.add(variant)

    # Index subjects by label for reassignment lookups
    subjects_by_label: dict[str, Any] = {s.label: s for s in all_subjects}

    sessions: list[dict[str, Any]] = []
    for subj in all_subjects:
        if subj.label not in matching_labels:
            continue
        subj_overrides = overrides.get(subj.label, {})
        for sess in subj.sessions():
            ovr = subj_overrides.get(sess.label, {})
            if ovr.get("exclude"):
                logger.info(
                    "Excluding %s/%s: %s",
                    subj.label, sess.label, ovr.get("reason", ""),
                )
                continue
            if ovr.get("reassign_to"):
                logger.info(
                    "Skipping %s/%s (reassigned to %s): %s",
                    subj.label, sess.label,
                    ovr["reassign_to"], ovr.get("reason", ""),
                )
                continue
            sessions.append(
                {
                    "fw_subject": subj,
                    "fw_session": sess,
                    "timestamp": sess.timestamp,
                    "acquisitions": sess.acquisitions(),
                }
            )

    # Pick up sessions reassigned TO this canonical subject
    for src_label, src_overrides in overrides.items():
        for ses_label, ovr in src_overrides.items():
            if ovr.get("reassign_to") != canonical_label:
                continue
            src_subj = subjects_by_label.get(src_label)
            if src_subj is None:
                logger.warning(
                    "Reassign source subject '%s' not found in project",
                    src_label,
                )
                continue
            for sess in src_subj.sessions():
                if sess.label == ses_label:
                    logger.info(
                        "Reassigning %s/%s -> %s: %s",
                        src_label, ses_label,
                        canonical_label, ovr.get("reason", ""),
                    )
                    sessions.append(
                        {
                            "fw_subject": src_subj,
                            "fw_session": sess,
                            "timestamp": sess.timestamp,
                            "acquisitions": sess.acquisitions(),
                        }
                    )
                    break

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
