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
