"""Flywheel inventory snapshot <-> FlywheelCohortSpec.

The snapshot JSON captures exactly what bidsify consumes (subject/session/acq
labels + timestamps + echo/n_trs); aliases + session overrides are applied by
production bidsify from pipeline_config.json, NOT here.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from neuro_workflow.testing.fake_flywheel import (
    FlywheelAcqSpec, FlywheelCohortSpec, FlywheelSessionSpec, FlywheelSubjectSpec)

# Pattern for multi-echo BOLD file names: *_eN.nii.gz  (N is one or more digits)
_ECHO_RE = re.compile(r"_e\d+\.nii\.gz$")


def _count_echoes(files: list[Any]) -> int:
    """Count the number of multi-echo BOLD NIfTI files in an acquisition's file list.

    Each echo contributes one ``*_eN.nii.gz`` file.  For non-func acquisitions
    (anatomical, fieldmap, dwi) there are none, so the result is 0.
    """
    return sum(1 for f in files if _ECHO_RE.search(f.name))


def _ts_to_str(ts: Any) -> str | None:
    """Coerce a session/acquisition timestamp to an ISO-8601 string (or None).

    The real Flywheel SDK returns ``datetime`` objects for ``session.timestamp``
    and strings for ``acq.timestamp`` (production ``run.py`` sorts acqs via
    ``a.timestamp or ""``).  We normalise both to a string for JSON storage so
    ``load_inventory`` can read them back without a datetime import.
    """
    if ts is None:
        return None
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts)


def fw_project_to_inventory(project: Any) -> dict:
    """Walk a (real or duck-typed) Flywheel project and return an inventory dict.

    The returned dict has the exact shape ``load_inventory`` expects::

        {
            "project": "<project label>",
            "subjects": [
                {
                    "label": "<subject label>",
                    "sessions": [
                        {
                            "label": "<session label>",
                            "timestamp": "<ISO-8601 str or null>",
                            "acquisitions": [
                                {
                                    "label": "<acq label>",
                                    "timestamp": "<ISO-8601 str or null>",
                                    "echoes": <int>,
                                }
                            ],
                        }
                    ],
                }
            ],
        }

    Access pattern mirrors production ``bidsify/flywheel_query.py``:

    * ``project.subjects()``  -> list of subject objects
    * ``subject.label``       -> str
    * ``subject.sessions()``  -> list of session objects
    * ``session.label``       -> str
    * ``session.timestamp``   -> datetime (real SDK) or str or None
    * ``session.acquisitions()`` -> list of acquisition objects
    * ``acq.label``           -> str
    * ``acq.timestamp``       -> str or None
    * ``acq.files``           -> list of file objects with ``.name`` attribute

    No ``flywheel`` import is required here — this operates on duck-typed objects
    so unit tests can pass a pure-Python fake without the SDK installed.

    Args:
        project: A Flywheel Project object (real or duck-typed).

    Returns:
        Inventory dict suitable for ``json.dumps`` + ``load_inventory``.
    """
    subjects_out = []
    for subj in project.subjects():
        sessions_out = []
        for sess in subj.sessions():
            acqs_out = []
            for acq in sess.acquisitions():
                acqs_out.append({
                    "label": acq.label,
                    "timestamp": _ts_to_str(acq.timestamp),
                    "echoes": _count_echoes(acq.files),
                })
            sessions_out.append({
                "label": sess.label,
                "timestamp": _ts_to_str(sess.timestamp),
                "acquisitions": acqs_out,
            })
        subjects_out.append({
            "label": subj.label,
            "sessions": sessions_out,
        })
    return {
        "project": project.label,
        "subjects": subjects_out,
    }


def load_inventory(path: Path) -> FlywheelCohortSpec:
    data = json.loads(Path(path).read_text())
    subjects = []
    for subj in data.get("subjects", []):
        sessions = []
        for sess in subj.get("sessions", []):
            acqs = [
                FlywheelAcqSpec(
                    label=a["label"], timestamp=a.get("timestamp"),
                    echoes=a.get("echoes", 3), n_trs=a.get("n_trs", 10),
                    with_physio=a.get("with_physio", False))
                for a in sess.get("acquisitions", [])
            ]
            sessions.append(FlywheelSessionSpec(
                label=sess["label"], timestamp=sess.get("timestamp"), acquisitions=acqs))
        subjects.append(FlywheelSubjectSpec(label=subj["label"], sessions=sessions))
    return FlywheelCohortSpec(project=data.get("project", "r01network"), subjects=subjects)


def dump_inventory(spec: FlywheelCohortSpec, path: Path) -> None:
    Path(path).write_text(json.dumps(asdict(spec), indent=2, default=str))
