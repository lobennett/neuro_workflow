"""Flywheel inventory snapshot <-> FlywheelCohortSpec.

The snapshot JSON captures exactly what bidsify consumes (subject/session/acq
labels + timestamps + echo/n_trs); aliases + session overrides are applied by
production bidsify from pipeline_config.json, NOT here.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from neuro_workflow.testing.fake_flywheel import (
    FlywheelAcqSpec, FlywheelCohortSpec, FlywheelSessionSpec, FlywheelSubjectSpec)


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
