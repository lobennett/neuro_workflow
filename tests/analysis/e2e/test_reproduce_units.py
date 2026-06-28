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


from neuro_workflow.testing.reproduce.stage_metrics import stage_metrics


def test_stage_metrics_symlinks(tmp_path):
    bids = tmp_path / "bids"; (bids / "derivatives").mkdir(parents=True)
    real_fmriprep = tmp_path / "real_fmriprep_25.2.4"; real_fmriprep.mkdir()
    (real_fmriprep / "marker.txt").write_text("x")
    staged = stage_metrics(bids, fmriprep_src=real_fmriprep, version="25.2.4")
    link = bids / "derivatives" / "fmriprep_25.2.4"
    assert link.is_symlink() and (link / "marker.txt").exists()
    assert staged["fmriprep"] == link


# ---------------------------------------------------------------------------
# Task 5 — canonical set extractors
# ---------------------------------------------------------------------------
from neuro_workflow.testing.reproduce.canonical import (
    compiled_to_keyset, bidsignore_lineset, bids_fileset)


def test_compiled_keyset_normalizes_task_prefix():
    compiled = [
        {"subject": "sub-s10", "session": "ses-01", "task": "task-goNogo",
         "run": "run-1", "action": "exclude", "source": "qa_decisions", "reason": "x"},
        {"subject": "sub-s10", "session": "ses-01", "task": "goNogo",
         "run": "run-1", "action": "exclude", "source": "collection", "reason": "y"},
        {"subject": "sub-s10", "session": "ses-02", "task": "flanker",
         "run": "run-1", "action": "force-include", "source": "override", "reason": "z"},
    ]
    ks = compiled_to_keyset(compiled)
    assert ("sub-s10","ses-01","goNogo","run-1","exclude","qa_decisions") in ks
    assert ("sub-s10","ses-01","goNogo","run-1","exclude","collection") in ks
    # force-include is not a gating action -> excluded from the set
    assert all(t[4] in ("exclude","trim") for t in ks)
    assert len(ks) == 2


def test_bidsignore_lineset_ignores_comments_blanks():
    text = "# header\n\nsub-s10/ses-01/func/foo_bold.*\n  \nsub-s19/ses-02/func/bar_bold.*\n"
    assert bidsignore_lineset(text) == {
        "sub-s10/ses-01/func/foo_bold.*", "sub-s19/ses-02/func/bar_bold.*"}


def test_bids_fileset_relative(tmp_path):
    (tmp_path / "sub-s03/ses-01/func").mkdir(parents=True)
    (tmp_path / "sub-s03/ses-01/func/a_bold.nii.gz").write_bytes(b"")
    (tmp_path / "sub-s03/ses-01/func/a_events.tsv").write_text("")
    (tmp_path / "sourcedata").mkdir()
    (tmp_path / "sourcedata/x.json").write_text("")
    fs = bids_fileset(tmp_path)
    assert "sub-s03/ses-01/func/a_bold.nii.gz" in fs
    assert "sub-s03/ses-01/func/a_events.tsv" in fs
    assert not any(f.startswith("sourcedata/") for f in fs)


# ---------------------------------------------------------------------------
# Task 6 — lev2 reference set
# ---------------------------------------------------------------------------
from neuro_workflow.testing.reproduce.lev2_select import lev2_reference_set


def test_lev2_reference_set_globs_and_filters_belowminruns(tmp_path):
    base = tmp_path / "lev1/sub-s03/task-flanker/fixed_effects"; base.mkdir(parents=True)
    (base / "sub-s03_task-flanker_contrast-incongruent-congruent_rtmodel-RTDur_stat-fixed-effects.nii.gz").write_bytes(b"")
    (base / "sub-s03_task-flanker_contrast-rare_rtmodel-RTDur_desc-belowMinRuns_stat-fixed-effects.nii.gz").write_bytes(b"")
    ref = lev2_reference_set([tmp_path / "lev1"])
    assert ("sub-s03", "flanker", "incongruent-congruent") in ref
    assert all("rare" not in c for (_, _, c) in ref)  # belowMinRuns filtered


# ---------------------------------------------------------------------------
# Task 7 — diff_sets + build_report
# ---------------------------------------------------------------------------
from neuro_workflow.testing.reproduce.report import diff_sets, build_report


def test_diff_sets_partitions():
    d = diff_sets({"a", "b"}, {"b", "c"})
    assert d["matched"] == {"b"} and d["only_produced"] == {"a"} and d["only_reference"] == {"c"}


def test_build_report_pass_fail():
    clean = diff_sets({"a"}, {"a"})
    dirty = diff_sets({"a"}, {"a", "b"})
    rep_ok = build_report("discovery", clean, clean, clean, provenance={"sha": "x"})
    assert "PASS" in rep_ok.splitlines()[0] and "FAIL" not in rep_ok.splitlines()[0]
    rep_bad = build_report("discovery", clean, dirty, clean, provenance={"sha": "x"})
    assert "FAIL" in rep_bad.splitlines()[0]
