"""Query Flywheel for gephysio gear analysis outputs."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)


def find_gephysio_analyses(session: Any) -> list[Any]:
    """Find gephysio analyses on a Flywheel session.

    When the gear has been run multiple times, returns only the most
    recent batch (by created timestamp). Skips analyses with no output files.

    Args:
        session: A reloaded Flywheel session object.

    Returns:
        List of Flywheel analysis objects from the latest gear run.
    """
    all_analyses = session.analyses or []
    gephysio = [
        a for a in all_analyses if a.gear_info and a.gear_info.get("name") == "gephysio" and a.files
    ]

    if not gephysio:
        return []

    # Group by acquisition ID to find duplicates, keep newest per acquisition
    by_acq: dict[str, list[Any]] = defaultdict(list)
    for a in gephysio:
        a = a.reload()
        if not a.inputs:
            continue
        acq_id = a.inputs[0]._parents.get("acquisition", "unknown")
        by_acq[acq_id].append(a)

    # For each acquisition, keep only the most recently created analysis
    latest = []
    for acq_id, analyses in by_acq.items():
        newest = max(analyses, key=lambda a: a.created or "")
        latest.append(newest)

    return latest


def match_analyses_to_acquisitions(
    analyses: list[Any],
    acq_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Match gephysio analyses to their source acquisitions.

    Args:
        analyses: List of gephysio analysis objects.
        acq_map: Mapping of acquisition ID -> {"task": str, "run": int}.

    Returns:
        List of dicts with keys: task, run, analysis.
    """
    matched = []
    for a in analyses:
        if not a.inputs:
            continue
        acq_id = a.inputs[0]._parents.get("acquisition")
        if acq_id not in acq_map:
            logger.debug("Gephysio analysis for unknown acquisition %s, skipping", acq_id)
            continue
        info = acq_map[acq_id]
        matched.append(
            {
                "task": info["task"],
                "run": info["run"],
                "analysis": a,
            }
        )
    return matched
