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
    # physio sidecars are an accepted out-of-scope boundary (gephysio-derived,
    # not modeled by the snapshot replay, not a lev1/lev2 input)
    (tmp_path / "sub-s03/ses-01/func/a_recording-cardiac_physio.tsv.gz").write_bytes(b"")
    (tmp_path / "sub-s03/ses-01/func/a_recording-cardiac_physio.json").write_text("")
    fs = bids_fileset(tmp_path)
    assert "sub-s03/ses-01/func/a_bold.nii.gz" in fs
    assert "sub-s03/ses-01/func/a_events.tsv" in fs
    assert not any(f.startswith("sourcedata/") for f in fs)
    assert not any("_physio." in f for f in fs)


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


# ---------------------------------------------------------------------------
# Task 8 — fw_project_to_inventory
# ---------------------------------------------------------------------------
from neuro_workflow.testing.reproduce.snapshot import fw_project_to_inventory


class _FakeFile:
    """Duck-typed Flywheel file — only .name is read by fw_project_to_inventory."""

    def __init__(self, name):
        self.name = name


class _FakeAcq:
    """Duck-typed Flywheel acquisition."""

    def __init__(self, label, timestamp, files):
        self.label = label
        self.timestamp = timestamp
        self.files = files


class _FakeSess:
    """Duck-typed Flywheel session."""

    def __init__(self, label, timestamp, acqs):
        self.label = label
        self.timestamp = timestamp
        self._acqs = acqs

    def acquisitions(self):
        return list(self._acqs)


class _FakeSubj:
    """Duck-typed Flywheel subject."""

    def __init__(self, label, sessions):
        self.label = label
        self._sessions = sessions

    def sessions(self):
        return list(self._sessions)


class _FakeProject:
    """Duck-typed Flywheel project."""

    def __init__(self, label, subjects):
        self.label = label
        self._subjects = subjects

    def subjects(self):
        return list(self._subjects)


def _make_fake_fw_project():
    """Build a minimal duck-typed Flywheel project with one subject/session/acq."""
    # Multi-echo BOLD acq: files include _e1.nii.gz, _e2.nii.gz, _e3.nii.gz
    bold_files = [
        _FakeFile("task-flanker_bold_e1.nii.gz"),
        _FakeFile("task-flanker_bold_e1.json"),
        _FakeFile("task-flanker_bold_e2.nii.gz"),
        _FakeFile("task-flanker_bold_e2.json"),
        _FakeFile("task-flanker_bold_e3.nii.gz"),
        _FakeFile("task-flanker_bold_e3.json"),
    ]
    # Anatomical acq: no echo files
    anat_files = [
        _FakeFile("T1w_MPRAGE_PROMO.nii.gz"),
        _FakeFile("T1w_MPRAGE_PROMO.json"),
    ]
    acq_bold = _FakeAcq(
        label="task-flanker_bold",
        timestamp="2021-01-15T10:35:00+00:00",
        files=bold_files,
    )
    acq_anat = _FakeAcq(
        label="T1w MPRAGE PROMO",
        timestamp="2021-01-15T10:50:00+00:00",
        files=anat_files,
    )
    sess = _FakeSess(
        label="ses-A",
        timestamp="2021-01-15T10:30:00+00:00",
        acqs=[acq_bold, acq_anat],
    )
    subj = _FakeSubj(label="s03", sessions=[sess])
    return _FakeProject(label="r01network", subjects=[subj])


def test_fw_project_to_inventory_shape(tmp_path):
    """fw_project_to_inventory produces a dict load_inventory can round-trip."""
    project = _make_fake_fw_project()
    inv = fw_project_to_inventory(project)

    # Top-level shape
    assert inv["project"] == "r01network"
    assert len(inv["subjects"]) == 1

    subj_d = inv["subjects"][0]
    assert subj_d["label"] == "s03"
    assert len(subj_d["sessions"]) == 1

    sess_d = subj_d["sessions"][0]
    assert sess_d["label"] == "ses-A"
    # timestamp must be a string (ISO-8601) for JSON serialisation
    assert isinstance(sess_d["timestamp"], str)
    assert "2021-01-15" in sess_d["timestamp"]

    acqs = sess_d["acquisitions"]
    assert len(acqs) == 2
    flanker = next(a for a in acqs if a["label"] == "task-flanker_bold")
    # 3 echo .nii.gz files -> echoes == 3
    assert flanker["echoes"] == 3

    anat = next(a for a in acqs if a["label"] == "T1w MPRAGE PROMO")
    # No echo files -> echoes == 0 (non-func)
    assert anat["echoes"] == 0


def test_fw_project_to_inventory_roundtrip(tmp_path):
    """fw_project_to_inventory output -> JSON -> load_inventory round-trips."""
    import json

    project = _make_fake_fw_project()
    inv = fw_project_to_inventory(project)
    p = tmp_path / "inv.json"
    p.write_text(json.dumps(inv, default=str))

    spec = load_inventory(p)
    assert spec.project == "r01network"
    assert [s.label for s in spec.subjects] == ["s03"]
    sess = spec.subjects[0].sessions[0]
    assert sess.label == "ses-A"
    acq_labels = [a.label for a in sess.acquisitions]
    assert "task-flanker_bold" in acq_labels
    assert "T1w MPRAGE PROMO" in acq_labels
    flanker_spec = next(a for a in sess.acquisitions if a.label == "task-flanker_bold")
    assert flanker_spec.echoes == 3


# ---------------------------------------------------------------------------
# FIX 1 regression — override seeding into the hermetic lock dir
# ---------------------------------------------------------------------------

import shutil

import neuro_workflow.core.exclusions as _excl_mod
from neuro_workflow.core.exclusions import _overrides_path


def test_override_seeding_copies_to_correct_lockdir_path(tmp_path):
    """Seeding logic copies committed overrides to _overrides_path() under the
    redirected LOCKFILE_DIR so compile_exclusions -> load_overrides finds them.

    This is a regression test for the bug where the hermetic seam redirected
    LOCKFILE_DIR to a scratch dir but nothing seeded the committed overrides
    file there, causing load_overrides to silently return [].
    """
    import json

    # Create a fake committed overrides file
    committed_overrides_dir = tmp_path / "data" / "exclusions"
    committed_overrides_dir.mkdir(parents=True)
    overrides_payload = [
        {"subject": "s10", "session": "ses-01", "task": "goNogo",
         "run": "run-1", "action": "force-include", "reason": "keep this scan"},
    ]
    committed_file = committed_overrides_dir / "discovery_overrides.json"
    committed_file.write_text(json.dumps(overrides_payload))

    # Redirect LOCKFILE_DIR to a scratch lock dir (mirrors _hermetic_exclusion_paths)
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    original_lockfile_dir = _excl_mod.LOCKFILE_DIR
    _excl_mod.LOCKFILE_DIR = lock_dir
    try:
        # Replicate the seeding logic from reproduce_cohort._run_all_generators
        committed_overrides = committed_overrides_dir / "discovery_overrides.json"
        if committed_overrides.is_file():
            shutil.copy2(committed_overrides, _overrides_path("discovery"))

        # The file must land at the path load_overrides will read
        dest = _overrides_path("discovery")
        assert dest.exists(), f"Seeded overrides file not found at {dest}"
        assert dest.parent == lock_dir, (
            f"Expected dest parent {lock_dir}, got {dest.parent}"
        )
        loaded = json.loads(dest.read_text())
        assert loaded == overrides_payload
    finally:
        _excl_mod.LOCKFILE_DIR = original_lockfile_dir


def test_override_seeding_noop_when_source_absent(tmp_path):
    """If no committed overrides file exists, seeding is a no-op (no crash)."""
    lock_dir = tmp_path / "lock"
    lock_dir.mkdir()
    original_lockfile_dir = _excl_mod.LOCKFILE_DIR
    _excl_mod.LOCKFILE_DIR = lock_dir
    try:
        committed_overrides = tmp_path / "data" / "exclusions" / "discovery_overrides.json"
        # File does not exist — seeding should be a no-op
        if committed_overrides.is_file():
            shutil.copy2(committed_overrides, _overrides_path("discovery"))
        # Nothing should have been written to lock_dir
        assert not list(lock_dir.iterdir()), "No files expected when source absent"
    finally:
        _excl_mod.LOCKFILE_DIR = original_lockfile_dir
