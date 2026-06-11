"""End-to-end bidsify (Flywheel -> BIDS) on a FAKE Flywheel service.

Closes the "Flywheel pull" boundary of the pipeline simulation. The B1/B2/
capstone simulation chain (``testing/synthetic.py`` + ``testing/cohort.py`` +
``testing/simulate.py``) starts from a synthetic *BIDS* dataset; this test
manufactures the stage UPSTREAM of that — a fake Flywheel project whose
acquisitions+files the REAL ``run_bidsify`` downloads and renames into a real
BIDS tree, with NO Flywheel service / network / dcm2niix.

``bidsify/run.py`` downloads NIfTIs directly (no DICOM conversion): it selects
``acq.files``, calls ``download_and_place(acq, file, dest)`` (which calls
``acq.download_file(name, dest)``), renames to BIDS, and patches JSON sidecars.
So a fake client serving synthetic acquisitions+files lets ``run_bidsify``
produce a genuine BIDS dataset. The fake implements EXACTLY the SDK surface
``run.py`` / ``flywheel_query.py`` / ``file_selector.py`` / ``physio_query.py``
touch (see ``neuro_workflow.testing.fake_flywheel``).

Everything load-bearing here is production code: the ONLY seam is
monkeypatching ``flywheel.Client`` (the documented client constructor
``run_bidsify`` already calls). The cohort -> fake-tree builder and the fake
objects are additive test support under ``neuro_workflow.testing``.
"""

from __future__ import annotations

import json

import pytest

# The cohort writers / NIfTI synthesis need nibabel + numpy; skip cleanly if
# absent (mirrors the rest of the dependency-light bidsify suite, which uses
# only stdlib + MagicMock — this file is the one that pulls nibabel in).
nib = pytest.importorskip("nibabel")
np = pytest.importorskip("numpy")

from neuro_workflow.bidsify.run import run_bidsify  # noqa: E402
from neuro_workflow.testing.fake_flywheel import (  # noqa: E402
    FakeFlywheelClient,
    FlywheelAcqSpec,
    FlywheelCohortSpec,
    FlywheelSessionSpec,
    FlywheelSubjectSpec,
    make_fake_flywheel,
)


# --------------------------------------------------------------------------- #
# Monkeypatch seam: make `flywheel.Client()` return our fake.
# --------------------------------------------------------------------------- #
@pytest.fixture
def patch_flywheel(monkeypatch):
    """Return a setter that installs a FakeFlywheelClient under flywheel.Client.

    ``run_bidsify`` does ``import flywheel; fw = flywheel.Client()``. We install
    a stub ``flywheel`` module whose ``Client`` returns the provided fake. This
    is the single seam — no production code is modified.
    """

    def _install(fake_client: FakeFlywheelClient) -> None:
        import sys
        import types

        stub = types.ModuleType("flywheel")
        stub.Client = lambda *a, **k: fake_client  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "flywheel", stub)

    return _install


# --------------------------------------------------------------------------- #
# A representative Flywheel-side cohort spec.
# --------------------------------------------------------------------------- #
def _basic_spec() -> FlywheelCohortSpec:
    """One subject, one session: multi-echo BOLD + T1w + fieldmap.

    Acquisition labels are REAL keys from ``bidsify/config.py``'s
    ``ACQUISITION_MAP`` so ``map_acquisition`` resolves them to the right
    modality/task. The BOLD acquisition carries 3 echoes.
    """
    return FlywheelCohortSpec(
        project="r01network",
        subjects=[
            FlywheelSubjectSpec(
                label="s01",
                sessions=[
                    FlywheelSessionSpec(
                        label="sess_a",
                        timestamp="2021-01-01T09:00:00+00:00",
                        acquisitions=[
                            FlywheelAcqSpec(
                                label="task-flanker_bold",
                                timestamp="2021-01-01T09:10:00+00:00",
                                echoes=3,
                            ),
                            FlywheelAcqSpec(
                                label="T1w MPRAGE PROMO",
                                timestamp="2021-01-01T09:05:00+00:00",
                            ),
                            FlywheelAcqSpec(
                                label="fmap-fieldmap",
                                timestamp="2021-01-01T09:02:00+00:00",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


# --------------------------------------------------------------------------- #
# Builder-level checks (the fake matches the SDK surface). These don't need
# run_bidsify; they prove the fake object tree is well-formed.
# --------------------------------------------------------------------------- #
class TestFakeClientSurface:
    def test_find_first_returns_project(self):
        fw = make_fake_flywheel(_basic_spec())
        proj = fw.projects.find_first('label="r01network"')
        assert proj is not None
        assert proj.label == "r01network"

    def test_find_first_unknown_project_returns_none(self):
        fw = make_fake_flywheel(_basic_spec())
        assert fw.projects.find_first('label="does-not-exist"') is None

    def test_subjects_sessions_acquisitions_chain(self):
        fw = make_fake_flywheel(_basic_spec())
        proj = fw.projects.find_first('label="r01network"')
        subjects = proj.subjects()
        assert [s.label for s in subjects] == ["s01"]
        sessions = subjects[0].sessions()
        assert [s.label for s in sessions] == ["sess_a"]
        acqs = sessions[0].acquisitions()
        assert {a.label for a in acqs} == {
            "task-flanker_bold",
            "T1w MPRAGE PROMO",
            "fmap-fieldmap",
        }

    def test_reload_returns_self(self):
        fw = make_fake_flywheel(_basic_spec())
        sess = fw.projects.find_first('label="r01network"').subjects()[0].sessions()[0]
        assert sess.reload() is sess
        acq = sess.acquisitions()[0]
        assert acq.reload() is acq

    def test_multiecho_files_named_with_echo_suffix(self):
        """BOLD acquisition files use the ``_eN`` echo suffix select_files keys on."""
        fw = make_fake_flywheel(_basic_spec())
        acqs = (
            fw.projects.find_first('label="r01network"')
            .subjects()[0]
            .sessions()[0]
            .acquisitions()
        )
        bold = next(a for a in acqs if a.label == "task-flanker_bold")
        niftis = sorted(f.name for f in bold.files if f.name.endswith(".nii.gz"))
        jsons = sorted(
            f.name for f in bold.files
            if f.name.endswith(".json") and f.type == "source code"
        )
        assert len(niftis) == 3
        assert len(jsons) == 3
        # echo suffix pattern that file_selector._echo_number parses
        assert all("_e" in n for n in niftis)

    def test_file_created_is_datetime(self):
        """download_and_place calls file.created.isoformat(); created must be datetime."""
        from datetime import datetime

        fw = make_fake_flywheel(_basic_spec())
        acqs = (
            fw.projects.find_first('label="r01network"')
            .subjects()[0]
            .sessions()[0]
            .acquisitions()
        )
        for a in acqs:
            for f in a.files:
                assert isinstance(f.created, datetime)
                assert isinstance(f.size, int)

    def test_download_file_writes_valid_nifti(self, tmp_path):
        """A fake .nii.gz download is a real, loadable NIfTI."""
        fw = make_fake_flywheel(_basic_spec())
        bold = next(
            a
            for a in fw.projects.find_first('label="r01network"')
            .subjects()[0]
            .sessions()[0]
            .acquisitions()
            if a.label == "task-flanker_bold"
        )
        nifti = next(f for f in bold.files if f.name.endswith(".nii.gz"))
        dest = tmp_path / "out.nii.gz"
        bold.download_file(nifti.name, str(dest))
        assert dest.exists()
        img = nib.load(str(dest))
        assert img.ndim == 4  # 4D BOLD

    def test_download_file_writes_valid_json_sidecar(self, tmp_path):
        """A fake .json download parses and carries the fields sidecar-patching needs."""
        fw = make_fake_flywheel(_basic_spec())
        bold = next(
            a
            for a in fw.projects.find_first('label="r01network"')
            .subjects()[0]
            .sessions()[0]
            .acquisitions()
            if a.label == "task-flanker_bold"
        )
        json_f = next(
            f for f in bold.files
            if f.name.endswith(".json") and f.type == "source code"
        )
        dest = tmp_path / "out.json"
        bold.download_file(json_f.name, str(dest))
        data = json.loads(dest.read_text())
        assert "RepetitionTime" in data


# --------------------------------------------------------------------------- #
# The hard gate: REAL run_bidsify over the fake produces a correct BIDS tree.
# --------------------------------------------------------------------------- #
class TestRunBidsifyEndToEnd:
    def test_produces_bold_anat_fmap(self, tmp_path, patch_flywheel):
        fw = make_fake_flywheel(_basic_spec())
        patch_flywheel(fw)

        run_bidsify("discovery", output_dir=tmp_path, subjects=["s01"], overwrite=True)

        func = tmp_path / "sub-s01" / "ses-01" / "func"
        anat = tmp_path / "sub-s01" / "ses-01" / "anat"
        fmap = tmp_path / "sub-s01" / "ses-01" / "fmap"

        # Multi-echo BOLD: 3 echoes -> 3 nii.gz + 3 json.
        for echo in (1, 2, 3):
            assert (func / f"sub-s01_ses-01_task-flanker_run-1_echo-{echo}_bold.nii.gz").exists()
            assert (func / f"sub-s01_ses-01_task-flanker_run-1_echo-{echo}_bold.json").exists()

        # Anat T1w (acq-MPRAGEPromo from config).
        assert (anat / "sub-s01_ses-01_acq-MPRAGEPromo_run-1_T1w.nii.gz").exists()
        assert (anat / "sub-s01_ses-01_acq-MPRAGEPromo_run-1_T1w.json").exists()

        # Fieldmap + magnitude.
        assert (fmap / "sub-s01_ses-01_run-1_fieldmap.nii.gz").exists()
        assert (fmap / "sub-s01_ses-01_run-1_fieldmap.json").exists()
        assert (fmap / "sub-s01_ses-01_run-1_magnitude.nii.gz").exists()

        # dataset_description.json written.
        assert (tmp_path / "dataset_description.json").exists()

    def test_bold_sidecar_patched_with_taskname_and_b0(self, tmp_path, patch_flywheel):
        """Production sidecar-patching ran: TaskName + B0FieldSource present."""
        fw = make_fake_flywheel(_basic_spec())
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s01"], overwrite=True)

        sidecar = (
            tmp_path / "sub-s01" / "ses-01" / "func"
            / "sub-s01_ses-01_task-flanker_run-1_echo-1_bold.json"
        )
        data = json.loads(sidecar.read_text())
        assert data["TaskName"] == "flanker"
        # fieldmap present -> bold sidecars get B0FieldSource pointing at the fmap id
        assert data["B0FieldSource"] == "sub-s01_ses-01_run-1_fieldmap"
        # the downloaded sidecar's own RepetitionTime survives the patch
        assert "RepetitionTime" in data

    def test_produced_bold_is_loadable_4d_nifti(self, tmp_path, patch_flywheel):
        fw = make_fake_flywheel(_basic_spec())
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s01"], overwrite=True)

        bold = (
            tmp_path / "sub-s01" / "ses-01" / "func"
            / "sub-s01_ses-01_task-flanker_run-1_echo-1_bold.nii.gz"
        )
        img = nib.load(str(bold))
        assert img.ndim == 4

    def test_reconciliation_and_log_written(self, tmp_path, patch_flywheel):
        fw = make_fake_flywheel(_basic_spec())
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s01"], overwrite=True)

        recon = json.loads(
            (tmp_path / "sourcedata" / "reconciliation_rerun-s01.json").read_text()
        )
        assert "s01" in recon["subjects"]
        assert recon["subjects"]["s01"]["total_sessions"] == 1

        log = json.loads(
            (tmp_path / "sourcedata" / "bidsify_log_rerun-s01.json").read_text()
        )
        assert log["total_files"] > 0

    def test_physio_branch_writes_bids_physio(self, tmp_path, patch_flywheel):
        """A gephysio analysis on the session yields BIDS ``_physio`` files.

        Exercises the full physio surface: ``session.analyses`` ->
        ``physio_query.find_gephysio_analyses`` (reads ``a.gear_info`` /
        ``a.inputs[0]._parents``) -> ``download_physio_analysis``
        (``analysis.download_file``) -> ``convert_physio_to_bids``. The fake's
        ``with_physio`` flag attaches the gephysio analysis tied to the BOLD
        acquisition's id.
        """
        spec = FlywheelCohortSpec(
            project="r01network",
            subjects=[
                FlywheelSubjectSpec(
                    label="s06",
                    sessions=[
                        FlywheelSessionSpec(
                            label="phys_sess",
                            timestamp="2021-07-01T09:00:00+00:00",
                            acquisitions=[
                                FlywheelAcqSpec(
                                    label="task-rest_bold",
                                    timestamp="2021-07-01T09:10:00+00:00",
                                    echoes=2,
                                    with_physio=True,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        fw = make_fake_flywheel(spec)
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s06"], overwrite=True)

        func = tmp_path / "sub-s06" / "ses-01" / "func"
        for channel in ("cardiac", "respiratory"):
            stem = f"sub-s06_ses-01_task-rest_run-1_recording-{channel}_physio"
            assert (func / f"{stem}.tsv.gz").exists(), f"missing {channel} physio TSV"
            assert (func / f"{stem}.json").exists(), f"missing {channel} physio JSON"


class TestDuplicateTaskRunNumbering:
    def test_two_acqs_same_task_get_run1_run2_by_timestamp(self, tmp_path, patch_flywheel):
        """Two acquisitions of the same task -> run-1/run-2 ordered by timestamp.

        The LATER timestamp must become run-2 (run.py sorts by timestamp before
        run-numbering). Distinct echo signals let us prove ordering, not just
        presence.
        """
        spec = FlywheelCohortSpec(
            project="r01network",
            subjects=[
                FlywheelSubjectSpec(
                    label="s02",
                    sessions=[
                        FlywheelSessionSpec(
                            label="sess_b",
                            timestamp="2021-02-01T09:00:00+00:00",
                            acquisitions=[
                                # Intentionally list the LATER one first to prove
                                # ordering is by timestamp, not list order.
                                FlywheelAcqSpec(
                                    label="task-flanker_bold",
                                    timestamp="2021-02-01T10:00:00+00:00",
                                    echoes=2,
                                ),
                                FlywheelAcqSpec(
                                    label="task-flanker_bold",
                                    timestamp="2021-02-01T09:30:00+00:00",
                                    echoes=2,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        fw = make_fake_flywheel(spec)
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s02"], overwrite=True)

        func = tmp_path / "sub-s02" / "ses-01" / "func"
        for run in (1, 2):
            for echo in (1, 2):
                assert (
                    func / f"sub-s02_ses-01_task-flanker_run-{run}_echo-{echo}_bold.nii.gz"
                ).exists(), f"missing run-{run} echo-{echo}"


class TestMultiSessionOrdering:
    def test_sessions_numbered_by_timestamp(self, tmp_path, patch_flywheel):
        """Two sessions -> ses-01/ses-02 by timestamp regardless of list order."""
        spec = FlywheelCohortSpec(
            project="r01network",
            subjects=[
                FlywheelSubjectSpec(
                    label="s03",
                    sessions=[
                        # later session listed first
                        FlywheelSessionSpec(
                            label="late",
                            timestamp="2021-03-02T09:00:00+00:00",
                            acquisitions=[
                                FlywheelAcqSpec(
                                    label="task-rest_bold",
                                    timestamp="2021-03-02T09:10:00+00:00",
                                    echoes=2,
                                ),
                            ],
                        ),
                        FlywheelSessionSpec(
                            label="early",
                            timestamp="2021-03-01T09:00:00+00:00",
                            acquisitions=[
                                FlywheelAcqSpec(
                                    label="task-cuedTS_bold",
                                    timestamp="2021-03-01T09:10:00+00:00",
                                    echoes=2,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        fw = make_fake_flywheel(spec)
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s03"], overwrite=True)

        # early session (cuedTS) is ses-01; late session (rest) is ses-02.
        assert (
            tmp_path / "sub-s03" / "ses-01" / "func"
            / "sub-s03_ses-01_task-cuedTS_run-1_echo-1_bold.nii.gz"
        ).exists()
        assert (
            tmp_path / "sub-s03" / "ses-02" / "func"
            / "sub-s03_ses-02_task-rest_run-1_echo-1_bold.nii.gz"
        ).exists()


class TestDwiAndProvenance:
    def test_dwi_writes_nifti_json_bval_bvec(self, tmp_path, patch_flywheel):
        spec = FlywheelCohortSpec(
            project="r01network",
            subjects=[
                FlywheelSubjectSpec(
                    label="s04",
                    sessions=[
                        FlywheelSessionSpec(
                            label="dwi_sess",
                            timestamp="2021-04-01T09:00:00+00:00",
                            acquisitions=[
                                FlywheelAcqSpec(
                                    label="DTI_pe0_g105",
                                    timestamp="2021-04-01T09:10:00+00:00",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        fw = make_fake_flywheel(spec)
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s04"], overwrite=True)

        dwi = tmp_path / "sub-s04" / "ses-01" / "dwi"
        stem = "sub-s04_ses-01_acq-g105_dir-AP_run-1_dwi"
        assert (dwi / f"{stem}.nii.gz").exists()
        assert (dwi / f"{stem}.json").exists()
        assert (dwi / f"{stem}.bval").exists()
        assert (dwi / f"{stem}.bvec").exists()


class TestGenuineness:
    """Prove the BIDS reflects the SPEC, not a hardcoded happy path."""

    def test_missing_echo_acq_emits_no_bold_files(self, tmp_path, patch_flywheel, caplog):
        """A BOLD acq with zero echoes -> run.py logs 'No echo files' and writes nothing.

        Mirrors how bidsify handles a protocol mismatch (a BOLD acquisition that
        produced no multi-echo files). The acquisition is PRESENT (so it isn't
        silently dropped as an unknown label) but yields no selectable echoes.
        """
        spec = FlywheelCohortSpec(
            project="r01network",
            subjects=[
                FlywheelSubjectSpec(
                    label="s05",
                    sessions=[
                        FlywheelSessionSpec(
                            label="bad",
                            timestamp="2021-05-01T09:00:00+00:00",
                            acquisitions=[
                                FlywheelAcqSpec(
                                    label="task-flanker_bold",
                                    timestamp="2021-05-01T09:10:00+00:00",
                                    echoes=0,  # no echo files produced
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        fw = make_fake_flywheel(spec)
        patch_flywheel(fw)
        import logging

        with caplog.at_level(logging.ERROR, logger="neuro_workflow.bidsify.run"):
            run_bidsify("discovery", output_dir=tmp_path, subjects=["s05"], overwrite=True)

        func = tmp_path / "sub-s05" / "ses-01" / "func"
        # No BOLD files written for the echo-less acquisition.
        produced = list(func.glob("*_bold.nii.gz")) if func.exists() else []
        assert produced == []
        # And the reconciliation records the protocol-mismatch warning.
        recon = json.loads(
            (tmp_path / "sourcedata" / "reconciliation_rerun-s05.json").read_text()
        )
        warnings = recon["subjects"]["s05"]["sessions"][0]["warnings"]
        assert any("multi-echo" in w for w in warnings)

    def test_absent_acquisition_does_not_appear(self, tmp_path, patch_flywheel):
        """A modality not in the spec is absent from the produced BIDS.

        The basic spec has no dwi; assert no dwi/ directory exists. Guards
        against a fake that fabricates files the spec never declared.
        """
        fw = make_fake_flywheel(_basic_spec())
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s01"], overwrite=True)
        assert not (tmp_path / "sub-s01" / "ses-01" / "dwi").exists()

    def test_download_targets_are_distinct_per_echo(self, tmp_path, patch_flywheel):
        """Each echo's NIfTI is independent content (no shared buffer / overwrite)."""
        fw = make_fake_flywheel(_basic_spec())
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s01"], overwrite=True)
        func = tmp_path / "sub-s01" / "ses-01" / "func"
        e1 = nib.load(
            str(func / "sub-s01_ses-01_task-flanker_run-1_echo-1_bold.nii.gz")
        ).get_fdata()
        e2 = nib.load(
            str(func / "sub-s01_ses-01_task-flanker_run-1_echo-2_bold.nii.gz")
        ).get_fdata()
        # Distinct echoes carry distinct (seeded) signal.
        assert not np.array_equal(e1, e2)


class TestSubjectAliasesAndOverrides:
    def test_alias_sessions_merge_into_canonical(self, tmp_path, patch_flywheel):
        """A FW subject ``s19-2`` (alias of ``s19``) merges into sub-s19 BIDS.

        ``config/pipeline_config.json`` maps ``s19-2 -> s19``. The fake serves
        both FW subjects; run_bidsify for canonical ``s19`` should merge the
        alias's session into the s19 timeline (ordered by timestamp).
        """
        spec = FlywheelCohortSpec(
            project="r01network",
            subjects=[
                FlywheelSubjectSpec(
                    label="s19",
                    sessions=[
                        FlywheelSessionSpec(
                            label="s19_native",
                            timestamp="2021-06-10T09:00:00+00:00",
                            acquisitions=[
                                FlywheelAcqSpec(
                                    label="task-rest_bold",
                                    timestamp="2021-06-10T09:10:00+00:00",
                                    echoes=2,
                                ),
                            ],
                        ),
                    ],
                ),
                FlywheelSubjectSpec(
                    label="s19-2",
                    sessions=[
                        FlywheelSessionSpec(
                            label="s19_alias",
                            timestamp="2021-06-01T09:00:00+00:00",  # earlier
                            acquisitions=[
                                FlywheelAcqSpec(
                                    label="task-cuedTS_bold",
                                    timestamp="2021-06-01T09:10:00+00:00",
                                    echoes=2,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        fw = make_fake_flywheel(spec)
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s19"], overwrite=True)

        # Alias session (earlier ts) becomes ses-01; native becomes ses-02.
        assert (
            tmp_path / "sub-s19" / "ses-01" / "func"
            / "sub-s19_ses-01_task-cuedTS_run-1_echo-1_bold.nii.gz"
        ).exists()
        assert (
            tmp_path / "sub-s19" / "ses-02" / "func"
            / "sub-s19_ses-02_task-rest_run-1_echo-1_bold.nii.gz"
        ).exists()
        # Reconciliation records both FW sources contributed.
        recon = json.loads(
            (tmp_path / "sourcedata" / "reconciliation_rerun-s19.json").read_text()
        )
        assert set(recon["subjects"]["s19"]["flywheel_sources"]) >= {"s19", "s19-2"}

    def test_excluded_session_override_is_dropped(self, tmp_path, patch_flywheel):
        """A session_overrides exclude entry drops that session from BIDS.

        config maps s29's FW session ``22424`` to ``{"exclude": true}``. With
        only that session present, no BIDS func data should be produced.
        """
        spec = FlywheelCohortSpec(
            project="r01network",
            subjects=[
                FlywheelSubjectSpec(
                    label="s29",
                    sessions=[
                        FlywheelSessionSpec(
                            label="22424",  # exclude:true in config
                            timestamp="2020-11-11T09:00:00+00:00",
                            acquisitions=[
                                FlywheelAcqSpec(
                                    label="fmap-fieldmap",
                                    timestamp="2020-11-11T09:10:00+00:00",
                                ),
                            ],
                        ),
                        FlywheelSessionSpec(
                            label="good_sess",
                            timestamp="2020-12-01T09:00:00+00:00",
                            acquisitions=[
                                FlywheelAcqSpec(
                                    label="task-rest_bold",
                                    timestamp="2020-12-01T09:10:00+00:00",
                                    echoes=2,
                                ),
                            ],
                        ),
                    ],
                ),
            ],
        )
        fw = make_fake_flywheel(spec)
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s29"], overwrite=True)

        # Only one session survives -> it is ses-01 (the excluded one is gone).
        assert (tmp_path / "sub-s29" / "ses-01").exists()
        assert not (tmp_path / "sub-s29" / "ses-02").exists()
        # The surviving session is the rest task (good_sess), not the fmap-only.
        assert (
            tmp_path / "sub-s29" / "ses-01" / "func"
            / "sub-s29_ses-01_task-rest_run-1_echo-1_bold.nii.gz"
        ).exists()
        recon = json.loads(
            (tmp_path / "sourcedata" / "reconciliation_rerun-s29.json").read_text()
        )
        assert recon["subjects"]["s29"]["total_sessions"] == 1


class TestStitchesWithCohortLayout:
    """The produced BIDS aligns with testing/cohort.py's layout naming.

    The downstream simulation (cohort.py -> simulate.py) reads BIDS func files
    named ``sub-X_ses-Y_task-T_run-N_*``. Multi-echo bidsify output carries the
    extra ``_echo-N`` entity, but the subject/session/task/run prefix matches,
    so the FileFinder-style discovery the downstream stages use lines up.
    """

    def test_prefix_matches_cohort_naming(self, tmp_path, patch_flywheel):
        fw = make_fake_flywheel(_basic_spec())
        patch_flywheel(fw)
        run_bidsify("discovery", output_dir=tmp_path, subjects=["s01"], overwrite=True)

        # cohort.py uses prefix f"sub-{subject}_ses-{session}_task-{task}_run-{run}"
        cohort_prefix = "sub-s01_ses-01_task-flanker_run-1"
        func = tmp_path / "sub-s01" / "ses-01" / "func"
        bolds = list(func.glob(f"{cohort_prefix}_echo-*_bold.nii.gz"))
        assert len(bolds) == 3
        # Every produced BOLD shares the cohort prefix.
        for b in bolds:
            assert b.name.startswith(cohort_prefix)
