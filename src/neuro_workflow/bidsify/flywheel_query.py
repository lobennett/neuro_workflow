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

    Returns list of dicts sorted by timestamp:
        {fw_subject, fw_session, timestamp, acquisitions}

    Parameters
    ----------
    session_overrides : dict, optional
        Keys are ``"subject_label/session_label"`` strings.  Each value is a
        dict with an ``"action"`` key:

        * ``{"action": "exclude"}`` – drop the session entirely.
        * ``{"action": "reassign_to", "target": "<subject>"}`` – move the
          session to a different subject's timeline.
    """
    if session_overrides is None:
        session_overrides = {}

    # Build set of FW labels that map to this canonical label
    matching_labels = {canonical_label}
    for variant, canon in aliases.items():
        if canon == canonical_label:
            matching_labels.add(variant)

    # Index subjects by label for reassignment lookups
    subjects_by_label: dict[str, Any] = {}
    for subj in all_subjects:
        subjects_by_label[subj.label] = subj

    sessions: list[dict[str, Any]] = []
    for subj in all_subjects:
        if subj.label not in matching_labels:
            continue
        for sess in subj.sessions():
            override_key = f"{subj.label}/{sess.label}"
            ovr = session_overrides.get(override_key)
            if ovr is not None:
                if ovr.get("action") == "exclude":
                    logger.info(
                        "Excluding session %s (override)", override_key
                    )
                    continue
                if ovr.get("action") == "reassign_to":
                    logger.info(
                        "Skipping session %s (reassigned to %s)",
                        override_key,
                        ovr["target"],
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
    for key, ovr in session_overrides.items():
        if ovr.get("action") != "reassign_to":
            continue
        if ovr.get("target") != canonical_label:
            continue
        src_subj_label, src_sess_label = key.split("/", 1)
        src_subj = subjects_by_label.get(src_subj_label)
        if src_subj is None:
            logger.info(
                "Reassign source subject %s not found", src_subj_label
            )
            continue
        for sess in src_subj.sessions():
            if sess.label == src_sess_label:
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
