import json
from pathlib import Path
from neuro_workflow.testing.reproduce.snapshot import load_inventory, dump_inventory
from neuro_workflow.testing.fake_flywheel import FlywheelCohortSpec


def _sample_inventory():
    return {
        "project": "r01network",
        "subjects": [
            {"label": "s03", "sessions": [
                {"label": "ses-A", "timestamp": "2021-01-15T10:30:00+00:00", "acquisitions": [
                    {"label": "task-flanker_bold", "timestamp": "2021-01-15T10:35:00+00:00",
                     "echoes": 3, "n_trs": 10},
                    {"label": "T1w MPRAGE PROMO", "timestamp": "2021-01-15T10:50:00+00:00"},
                ]},
            ]},
        ],
    }


def _w(tmp_path, inv):
    p = tmp_path / "inv.json"; p.write_text(json.dumps(inv)); return p


def test_load_inventory_builds_spec(tmp_path):
    spec = load_inventory(_w(tmp_path, _sample_inventory()))
    assert isinstance(spec, FlywheelCohortSpec)
    assert spec.project == "r01network"
    assert [s.label for s in spec.subjects] == ["s03"]
    sess = spec.subjects[0].sessions[0]
    assert sess.label == "ses-A" and sess.timestamp == "2021-01-15T10:30:00+00:00"
    acqs = sess.acquisitions
    assert acqs[0].label == "task-flanker_bold" and acqs[0].echoes == 3 and acqs[0].n_trs == 10
    assert acqs[1].label == "T1w MPRAGE PROMO"


def test_inventory_roundtrip(tmp_path):
    spec = load_inventory(_w(tmp_path, _sample_inventory()))
    out = tmp_path / "rt.json"
    dump_inventory(spec, out)
    spec2 = load_inventory(out)
    assert [a.label for a in spec2.subjects[0].sessions[0].acquisitions] == \
           [a.label for a in spec.subjects[0].sessions[0].acquisitions]


import sys
import types

from neuro_workflow.testing.reproduce.replay import replay_to_bids
from neuro_workflow.testing.fake_flywheel import (
    FlywheelCohortSpec, FlywheelSubjectSpec, FlywheelSessionSpec, FlywheelAcqSpec)


def _mini_spec():
    acq = FlywheelAcqSpec(label="task-flanker_bold", timestamp="2021-01-15T10:35:00+00:00",
                          echoes=1, n_trs=12)
    sess = FlywheelSessionSpec(label="ses-A", timestamp="2021-01-15T10:30:00+00:00",
                               acquisitions=[acq])
    return FlywheelCohortSpec(project="r01network",
                              subjects=[FlywheelSubjectSpec(label="s03", sessions=[sess])])


def test_replay_produces_named_trimmed_bids(tmp_path, monkeypatch):
    spec = _mini_spec()
    def install(fake):
        # flywheel SDK is not installed in the test venv; inject a stub module
        # whose Client returns our fake, matching the seam used in
        # tests/bidsify/test_fake_flywheel_e2e.py::patch_flywheel.
        stub = types.ModuleType("flywheel")
        stub.Client = lambda *a, **k: fake
        monkeypatch.setitem(sys.modules, "flywheel", stub)
    bids = replay_to_bids(spec, tmp_path, sample_name="discovery",
                          behavioral_dir=tmp_path / "empty_beh", install_flywheel=install)
    bold = list(bids.glob("sub-s03/ses-01/func/*task-flanker*_bold.nii.gz"))
    assert bold, "bidsify must produce a flanker bold with the expected name"
    import json as _j
    sc = _j.loads(next(bids.glob("sub-s03/ses-01/func/*task-flanker*_bold.json")).read_text())
    assert sc.get("NumberOfVolumesDiscardedByUser") == 7
