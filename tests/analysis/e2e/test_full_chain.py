"""The literal Flywheel -> lev1 simulation: ONE spec drives the WHOLE chain.

This is the capstone of the simulation campaign. Where
``test_simulate_dataset.py`` started from a synthetic *BIDS* dataset (the
Flywheel pull + raw-jsPsych->events boundaries bypassed), this drives every
REAL stage in order, from a fake Flywheel project all the way to a recovered
lev1 contrast:

  1. **FakeFlywheel -> run_bidsify -> BIDS** — the production
     ``bidsify.run.run_bidsify`` downloads + renames the fake project's
     acquisitions into a real BIDS tree (no Flywheel / network / dcm2niix).
  2. **sourcedata behavioral + events.create -> events.tsv** — raw jsPsych CSVs
     (``testing.raw_jspsych.make_raw_jspsych_csv``) are written to sourcedata
     and the production ``events.create.run_create_events`` turns them into BIDS
     events.tsv files.
  3. **fMRIPrep-derivative stub** — ``testing.synthetic.make_fmriprep_run``
     plants a confounds TSV + preproc BOLD for each scan (a known contrast
     planted into one keep scan's BOLD).
  4. **exclusions** — the REAL behavioral + motion generators ->
     ``compile_exclusions`` -> rendered ``.bidsignore`` (via the existing
     ``simulate_exclusions`` over the produced tree).
  5. **lev1** — the REAL ``FileFinder`` discovery -> ``preprocess_events`` ->
     ``add_junk_trials`` -> ``create_design_matrix`` -> ``fit_run_glm`` ->
     ``compute_run_contrasts`` on the keep scan.

The single spec asserts: (a) bidsify produced the expected BIDS; (b) the
events.tsv is valid for lev1; (c) the compiled exclusion set EXACTLY equals the
planted-excluded scans by source; (d) the planted contrast is recovered through
the REAL lev1 path; (e) excluded scans are honored by the REAL exclusion key
path. Everything load-bearing is production code; only the additive
``neuro_workflow.testing`` helpers are test support.
"""

from __future__ import annotations

import json
import sys
import types

import pytest

# The whole chain needs pandas/nibabel; the lev1 recovery leg needs nilearn.
pd = pytest.importorskip("pandas")
nib = pytest.importorskip("nibabel")
pytest.importorskip("nilearn")

import numpy as np  # noqa: E402

from neuro_workflow.analysis.core.utils import (  # noqa: E402
    load_exclusions,
    normalize_subject_id,
)
from neuro_workflow.analysis.io.file_discovery import FileFinder  # noqa: E402
from neuro_workflow.analysis.lev1.processing.contrasts import (  # noqa: E402
    compute_run_contrasts,
)
from neuro_workflow.analysis.lev1.processing.design import (  # noqa: E402
    create_design_matrix,
)
from neuro_workflow.analysis.lev1.processing.events import (  # noqa: E402
    add_junk_trials,
    preprocess_events,
)
from neuro_workflow.analysis.lev1.processing.glm import fit_run_glm  # noqa: E402
from neuro_workflow.analysis.task_config.loader import (  # noqa: E402
    get_task_contrasts,
    get_task_parameters,
)
from neuro_workflow.testing.fake_flywheel import (  # noqa: E402
    FlywheelAcqSpec,
    FlywheelCohortSpec,
    FlywheelSessionSpec,
    FlywheelSubjectSpec,
)
from neuro_workflow.testing.simulate import simulate_full_pipeline  # noqa: E402
from neuro_workflow.testing.synthetic import make_mask  # noqa: E402

TASK = "flanker"
N_TRS = 120
PLANTED_EFFECT = 5.0  # incongruent - congruent


# --------------------------------------------------------------------------- #
# Monkeypatch seam: make flywheel.Client() return the driver's fake client.
# The driver builds the fake; the test just installs the stub module.
# --------------------------------------------------------------------------- #
@pytest.fixture
def patch_flywheel(monkeypatch):
    def _install(fake_client) -> None:
        stub = types.ModuleType("flywheel")
        stub.Client = lambda *a, **k: fake_client  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "flywheel", stub)

    return _install


# --------------------------------------------------------------------------- #
# A spec with one acquisition per exclusion mechanism + a planted-contrast keep.
#
# Each func acq carries an ``outcome`` tag (keep / exclude:behavioral /
# exclude:motion / exclude:collection); a single ``plant_contrast=True`` keep
# scan gets the known +5 incongruent-congruent contrast. Sessions are ordered
# by timestamp -> the EARLIER session becomes ses-01.
# --------------------------------------------------------------------------- #
def _full_spec() -> FlywheelCohortSpec:
    return FlywheelCohortSpec(
        project="r01network",
        subjects=[
            FlywheelSubjectSpec(
                label="s01",
                sessions=[
                    FlywheelSessionSpec(
                        label="sess_a",
                        timestamp="2021-01-01T09:00:00+00:00",  # -> ses-01
                        acquisitions=[
                            FlywheelAcqSpec(
                                label="task-flanker_bold",
                                timestamp="2021-01-01T09:10:00+00:00",
                                echoes=3, n_trs=N_TRS,
                                outcome="keep", plant_contrast=True,
                            ),
                            FlywheelAcqSpec(
                                label="task-stopSignal_bold",
                                timestamp="2021-01-01T09:20:00+00:00",
                                echoes=3, n_trs=N_TRS,
                                outcome="exclude:behavioral",
                            ),
                        ],
                    ),
                    FlywheelSessionSpec(
                        label="sess_b",
                        timestamp="2021-02-01T09:00:00+00:00",  # -> ses-02
                        acquisitions=[
                            FlywheelAcqSpec(
                                label="task-flanker_bold",
                                timestamp="2021-02-01T09:10:00+00:00",
                                echoes=3, n_trs=N_TRS,
                                outcome="exclude:motion",
                            ),
                        ],
                    ),
                ],
            ),
            FlywheelSubjectSpec(
                label="s02",
                sessions=[
                    FlywheelSessionSpec(
                        label="sess_c",
                        timestamp="2021-03-01T09:00:00+00:00",  # -> ses-01
                        acquisitions=[
                            FlywheelAcqSpec(
                                label="task-goNogo_bold",
                                timestamp="2021-03-01T09:10:00+00:00",
                                echoes=3, n_trs=N_TRS,
                                outcome="exclude:collection",
                            ),
                            FlywheelAcqSpec(
                                label="task-flanker_bold",
                                timestamp="2021-03-01T09:20:00+00:00",
                                echoes=3, n_trs=N_TRS,
                                outcome="keep",
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


@pytest.fixture
def chain(tmp_path, patch_flywheel):
    """Drive the WHOLE chain once; return (root, result)."""
    root = tmp_path / "chain"
    result = simulate_full_pipeline(
        _full_spec(), root, dataset="sim", install_flywheel=patch_flywheel,
    )
    return root, result


def _excluded_scans(manifest):
    return [s for s in manifest["scans"] if s["outcome"].startswith("exclude:")]


def _keep_scans(manifest):
    return [s for s in manifest["scans"] if s["outcome"] == "keep"]


# --------------------------------------------------------------------------- #
# (a) bidsify produced the expected BIDS.
# --------------------------------------------------------------------------- #
class TestBidsProduced:
    def test_multiecho_bold_and_sidecars_written(self, chain):
        """The REAL run_bidsify produced multi-echo BOLD + patched sidecars for
        every planted scan, at the expected sub/ses/task/run prefix."""
        root, result = chain
        bids_dir = result.manifest["bids_dir"]
        assert result.manifest["scans"], "no scans produced"
        for scan in result.manifest["scans"]:
            func = (
                f"{bids_dir}/{scan['subject']}/{scan['session']}/func"
            )
            from pathlib import Path

            bolds = list(
                Path(func).glob(
                    f"{scan['subject']}_{scan['session']}_task-{scan['task']}_"
                    f"{scan['run']}_echo-*_bold.nii.gz"
                )
            )
            assert len(bolds) == 3, f"expected 3 echoes for {scan}, got {len(bolds)}"
            # one is a loadable 4D NIfTI
            assert nib.load(str(bolds[0])).ndim == 4

    def test_session_numbering_is_timestamp_ordered(self, chain):
        """s01's earlier session is ses-01, later is ses-02 (bidsify orders by
        timestamp) — proves the driver mapped spec->BIDS sessions correctly."""
        _, result = chain
        s01 = [s for s in result.manifest["scans"] if s["subject"] == "sub-s01"]
        # ses-01 holds the keep + behavioral scans; ses-02 holds the motion scan.
        ses01_tasks = {s["task"] for s in s01 if s["session"] == "ses-01"}
        ses02_tasks = {s["task"] for s in s01 if s["session"] == "ses-02"}
        assert ses01_tasks == {"flanker", "stopSignal"}
        assert ses02_tasks == {"flanker"}


# --------------------------------------------------------------------------- #
# (b) events.tsv is valid for lev1.
# --------------------------------------------------------------------------- #
class TestEventsValidForLev1:
    def test_events_tsv_built_by_real_create_events(self, chain):
        """Every scan has an events.tsv (written by the REAL run_create_events)
        with monotonic onsets and the task trial_types."""
        from pathlib import Path

        root, result = chain
        bids_dir = result.manifest["bids_dir"]
        flanker_scans = [
            s for s in result.manifest["scans"] if s["task"] == "flanker"
        ]
        assert flanker_scans
        for scan in flanker_scans:
            ev_path = Path(
                f"{bids_dir}/{scan['subject']}/{scan['session']}/func/"
                f"{scan['subject']}_{scan['session']}_task-flanker_"
                f"{scan['run']}_events.tsv"
            )
            assert ev_path.is_file(), f"missing events.tsv for {scan}"
            ev = pd.read_csv(ev_path, sep="\t")
            assert pd.to_numeric(ev["onset"]).is_monotonic_increasing
            assert {"congruent", "incongruent"} <= set(ev["trial_type"].unique())

    def test_keep_scan_events_drive_a_valid_design(self, chain):
        """The keep scan's events.tsv, through the REAL lev1 events path +
        create_design_matrix, yields the flanker regressors (non-degenerate)."""
        root, result = chain
        keep = result.recovery_scan  # the planted-contrast keep scan
        events = pd.read_csv(keep["events"], sep="\t")
        tr = get_task_parameters(TASK)["tr"]
        prepped = preprocess_events(events, TASK, n_scans=N_TRS, tr=tr)
        junked, _ = add_junk_trials(prepped, TASK)
        confounds = pd.DataFrame({"constant": np.ones(N_TRS)})
        design, _ = create_design_matrix(junked, confounds, TASK, N_TRS, tr)
        assert {"congruent", "incongruent"} <= set(design.columns)
        for reg in ("congruent", "incongruent"):
            assert np.abs(design[reg].to_numpy()).sum() > 0


# --------------------------------------------------------------------------- #
# (c) compiled exclusion set EXACTLY equals the planted-excluded scans by source.
# --------------------------------------------------------------------------- #
class TestExactExclusionSet:
    def test_compiled_qc_set_equals_planted_by_source(self, chain):
        """The compiled QC excluded set == planted behavioral + motion scans
        (right scans, right source, nothing extra/missing)."""
        _, result = chain
        manifest = result.manifest

        expected = set()
        for scan in manifest["scans"]:
            key = (scan["subject"], scan["session"], f"task-{scan['task']}", scan["run"])
            if scan["outcome"] == "exclude:behavioral":
                expected.add((*key, "behavioral-qc"))
            elif scan["outcome"] == "exclude:motion":
                expected.add((*key, "motion"))

        sources = {src for *_r, src in expected}
        assert sources == {"behavioral-qc", "motion"}, (
            f"plant should contain behavioral + motion; got {sources}"
        )

        compiled_set = result.exclusions.excluded_keys_with_source()
        assert compiled_set == expected, (
            "compiled QC exclusion set != planted set\n"
            f"  missing: {expected - compiled_set}\n"
            f"  extra:   {compiled_set - expected}"
        )

    def test_collection_scan_covered_by_rendered_bidsignore(self, chain):
        """The exclude:collection scan is covered by a rendered .bidsignore glob
        and is NOT a compiled QC entry."""
        _, result = chain
        coll = [
            s for s in result.manifest["scans"]
            if s["outcome"] == "exclude:collection"
        ]
        assert len(coll) == 1
        scan = coll[0]
        assert result.exclusions.bidsignore is not None
        run_prefix = (
            f"{scan['subject']}/{scan['session']}/func/"
            f"{scan['subject']}_{scan['session']}_task-{scan['task']}_{scan['run']}_"
        )
        lines = result.exclusions.bidsignore.splitlines()
        assert any(run_prefix in ln for ln in lines), (
            f"collection glob for {run_prefix!r} not in rendered .bidsignore"
        )
        key = (scan["subject"], scan["session"], f"task-{scan['task']}", scan["run"])
        assert key not in result.exclusions.excluded_keys()

    def test_keep_scans_not_excluded(self, chain):
        _, result = chain
        excluded = result.exclusions.excluded_keys()
        for scan in _keep_scans(result.manifest):
            key = (scan["subject"], scan["session"], f"task-{scan['task']}", scan["run"])
            assert key not in excluded, f"keep scan {key} wrongly excluded"


# --------------------------------------------------------------------------- #
# (d) planted contrast recovered through the REAL lev1 path.
# --------------------------------------------------------------------------- #
class TestLev1Recovery:
    def test_planted_contrast_recovered(self, chain):
        """Plant +5 incongruent-congruent into the keep scan's preproc BOLD (at
        the path FileFinder discovers) and recover it through the REAL lev1
        component path."""
        root, result = chain
        keep = result.recovery_scan
        subject = keep["subject"]

        finder = FileFinder(result.manifest["bids_dir"], result.manifest["fmriprep_dir"])
        files = finder.get_files(
            subject, TASK,
            required_files=FileFinder.get_required_files_for_space("MNI"),
        )
        assert files, f"FileFinder found no complete runs for {subject}/{TASK}"
        # The keep scan's own (session, run).
        session = keep["session"]
        run = keep["run"]
        assert session in files and run in files[session], (
            f"keep scan {session}/{run} not discovered; got {files}"
        )
        run_files = files[session][run]

        tr = get_task_parameters(TASK)["tr"]
        events = pd.read_csv(run_files["events"], sep="\t")
        prepped = preprocess_events(events, TASK, n_scans=N_TRS, tr=tr)
        junked, _ = add_junk_trials(prepped, TASK)
        confounds = pd.DataFrame({"constant": np.ones(N_TRS)})
        design, _ = create_design_matrix(junked, confounds, TASK, N_TRS, tr)
        assert {"congruent", "incongruent"} <= set(design.columns)

        # The driver planted the contrast into this BOLD already. Refit + recover.
        reloaded = nib.load(str(run_files["mni_data"]))
        fitted = fit_run_glm(
            reloaded, design, analysis_type="task", tr=tr,
            mask_img=make_mask(reloaded),
        )
        formula = get_task_contrasts(TASK)["incongruent-congruent"]
        assert formula == "incongruent - congruent"
        saved = compute_run_contrasts(
            fitted_glm=fitted, task_name=TASK,
            output_dir=root / "lev1_out",
            base_filename=f"{subject}_{session}_task-{TASK}_{run}",
            contrasts={"incongruent-congruent": formula},
        )
        effect_path = saved["incongruent-congruent"]["effect_size"]
        recovered = float(np.mean(nib.load(str(effect_path)).get_fdata()))
        assert recovered > 0, f"expected positive contrast, got {recovered}"
        assert recovered == pytest.approx(PLANTED_EFFECT, abs=1.0), (
            f"recovered {recovered:.3f} not within 1.0 of planted {PLANTED_EFFECT}"
        )
        # The driver also reports the recovered value in its manifest.
        assert result.recovered_contrast == pytest.approx(recovered, abs=1e-6)


# --------------------------------------------------------------------------- #
# (e) excluded scans are honored by the REAL lev1 exclusion key path.
# --------------------------------------------------------------------------- #
class TestExcludedHonored:
    def test_lev1_exclusion_keys_honor_excluded_and_pass_keep(self, chain):
        """load_exclusions over the compiled file + the runner's per-run key:
        excluded scans hit the set; keep scans do not."""
        _, result = chain
        compiled_file = (
            result.exclusions.exclusions_dir / "sim" / "compiled_exclusions.json"
        )
        keys = load_exclusions(compiled_file)

        def runner_key(scan):
            subj = normalize_subject_id(scan["subject"])
            return f"{subj}_{scan['session']}_task-{scan['task']}_{scan['run']}"

        for scan in _excluded_scans(result.manifest):
            if scan["outcome"] == "exclude:collection":
                continue  # collection is a static glob layer, not a QC key
            assert runner_key(scan) in keys, (
                f"{scan['outcome']} scan {runner_key(scan)!r} not honored by lev1"
            )
        for scan in _keep_scans(result.manifest):
            assert runner_key(scan) not in keys, (
                f"keep scan {runner_key(scan)!r} wrongly in lev1 exclusion set"
            )


# --------------------------------------------------------------------------- #
# Hermeticity guard (mirrors the dataset-sim test): nothing written into the
# version-controlled exclusions tree.
# --------------------------------------------------------------------------- #
def test_compiled_artifacts_are_hermetic(chain):
    _, result = chain
    compiled_json = (
        result.exclusions.exclusions_dir / "sim" / "compiled_exclusions.json"
    )
    assert compiled_json.is_file()
    on_disk = json.loads(compiled_json.read_text())
    assert {
        (e["subject"], e["session"], e["task"], e["run"]) for e in on_disk
    } == result.exclusions.excluded_keys()
