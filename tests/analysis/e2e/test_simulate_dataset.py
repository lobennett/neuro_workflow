"""CAPSTONE end-to-end pipeline simulation on a synthetic cohort.

This is the top of the test pyramid for the simulation campaign:

  * B1 (``tests/analysis/test_synthetic_fmriprep.py``) proved one stubbed
    fMRIPrep run drives the real ``FileFinder`` / ``MotionGenerator``.
  * B2 (``tests/analysis/test_synthetic_cohort.py``) proved a whole synthetic
    cohort's planted scans are each SEEN by their real generator.
  * This module chains the REAL stages end-to-end and asserts the resulting
    *dataset state*: the exact exclusion set, and lev1 recovery + honoring.

Two claims are proved:

1. **Exclusion-set fidelity (headline).** Build a cohort with keep scans plus
   one each of ``exclude:behavioral`` / ``exclude:motion`` /
   ``exclude:collection`` across two subjects and >=2 sessions. Run the REAL
   exclusion pipeline (``simulate_exclusions`` -> real behavioral + motion
   generators -> real ``compile_exclusions`` -> real
   ``render_bidsignore_with_collection``). Assert:

     * the compiled QC excluded set equals EXACTLY the planted behavioral +
       motion scans (right scans, right ``source``, nothing extra, nothing
       missing) — this would fail if a generator mis-fired or the
       subject/session/task/run key-matching regressed;
     * the collection-planted scan is covered by a glob line in the rendered
       ``.bidsignore`` (collection exclusions are a static glob layer, not QC
       entries, by design);
     * every keep scan is excluded by neither layer.

2. **lev1 honors exclusions + recovers signal.** For one keep scan, a known
   ``incongruent - congruent`` contrast is planted into its fMRIPrep BOLD at
   the path the real ``FileFinder`` discovers, then pushed through the REAL
   lev1 component path (``FileFinder`` discovery -> ``create_design_matrix`` ->
   ``fit_run_glm`` -> ``compute_run_contrasts``). The planted +5 contrast is
   recovered (sign + approx magnitude). Separately, a behavioral- and a
   motion-excluded scan are each shown to be honored by lev1's REAL exclusion
   path: ``load_exclusions`` over the compiled file yields a key set, and the
   runner's per-run key (``sub-X_ses-Y_task-T_run-N``) hits it — so
   ``process_single_run`` would early-return (skip), while the keep scan's key
   does not.

Everything load-bearing is production code; only the additive
``neuro_workflow.testing`` helpers (synthetic cohort + the thin
``simulate_exclusions`` driver) are test support.
"""

from __future__ import annotations

import json

import pytest

# Heavy deps: the cohort writers need pandas/nibabel; the lev1 recovery leg
# needs nilearn. Skip cleanly if any is absent (mirrors the lev1 conftest).
pd = pytest.importorskip("pandas")
nib = pytest.importorskip("nibabel")
pytest.importorskip("nilearn")

import numpy as np  # noqa: E402

from neuro_workflow.analysis.core.utils import (  # noqa: E402
    create_exclusion_key,
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
from neuro_workflow.analysis.lev1.processing.glm import fit_run_glm  # noqa: E402
from neuro_workflow.analysis.task_config.loader import (  # noqa: E402
    get_task_contrasts,
    get_task_parameters,
)
from neuro_workflow.core.exclusions import is_excluded  # noqa: E402
from neuro_workflow.testing.cohort import (  # noqa: E402
    CohortSpec,
    ScanSpec,
    SessionSpec,
    SubjectSpec,
    make_synthetic_cohort,
)
from neuro_workflow.testing.simulate import simulate_exclusions  # noqa: E402
from neuro_workflow.testing.synthetic import (  # noqa: E402
    as_4d_nifti,
    make_mask,
    plant_bold,
)

TASK = "flanker"
N_TRS = 120  # ~3 min run; ample to estimate the well-separated flanker trials
PLANTED = {"incongruent": 10.0, "congruent": 5.0, "constant": 100.0}
PLANTED_EFFECT = PLANTED["incongruent"] - PLANTED["congruent"]  # = +5.0


def _capstone_spec() -> CohortSpec:
    """A 2-subject, multi-session cohort with one scan per exclusion mechanism.

    Layout (every scan run-1 so the behavioral generator's hardcoded run-1
    entry lands on the right scan):

      sub-s01 ses-01 flanker     -> keep                 (lev1 recovery scan)
      sub-s01 ses-01 stopSignal  -> exclude:behavioral   (slow go RT)
      sub-s01 ses-02 flanker     -> exclude:motion        (high FD/DVARS)
      sub-s02 ses-01 goNogo      -> exclude:collection    (static glob)
      sub-s02 ses-01 flanker     -> keep
    """
    return CohortSpec(
        subjects=[
            SubjectSpec(
                subject="s01",
                sessions=[
                    SessionSpec(
                        session="01",
                        scans=[
                            ScanSpec(task=TASK, run="1", outcome="keep", n_trs=N_TRS),
                            ScanSpec(
                                task="stopSignal",
                                run="1",
                                outcome="exclude:behavioral",
                            ),
                        ],
                    ),
                    SessionSpec(
                        session="02",
                        scans=[
                            ScanSpec(
                                task=TASK,
                                run="1",
                                outcome="exclude:motion",
                                n_trs=N_TRS,
                            ),
                        ],
                    ),
                ],
            ),
            SubjectSpec(
                subject="s02",
                sessions=[
                    SessionSpec(
                        session="01",
                        scans=[
                            ScanSpec(
                                task="goNogo",
                                run="1",
                                outcome="exclude:collection",
                            ),
                            ScanSpec(task=TASK, run="1", outcome="keep", n_trs=N_TRS),
                        ],
                    ),
                ],
            ),
        ]
    )


def _planted_key(scan: dict) -> tuple:
    """The (subject, session, task, run) tuple a compiled entry keys on.

    Manifest scan records store ``task`` BARE (e.g. ``flanker``) but the
    compiled entries (and the lev1 runner key) carry the ``task-`` prefix, so
    normalise the manifest record to the prefixed form for comparison.
    """
    return (
        scan["subject"],
        scan["session"],
        f"task-{scan['task']}",
        scan["run"],
    )


@pytest.fixture
def cohort(tmp_path):
    """Build the capstone synthetic cohort under tmp_path; return its manifest."""
    root = tmp_path / "cohort"
    manifest = make_synthetic_cohort(root, _capstone_spec())
    return root, manifest


# --------------------------------------------------------------------------- #
# Claim 1: Exclusion-set fidelity (headline).
# --------------------------------------------------------------------------- #
class TestExclusionSetFidelity:
    def test_compiled_qc_set_equals_planted_behavioral_and_motion(self, cohort):
        """The compiled QC excluded set is EXACTLY the planted behavioral +
        motion scans — right scans, right source, nothing extra/missing."""
        root, manifest = cohort
        result = simulate_exclusions(root, manifest, dataset="sim")

        # Expected from the plant: behavioral-qc for the behavioral scan,
        # motion for the motion scan. (Collection is a separate static layer,
        # asserted below.)
        expected = set()
        for scan in manifest["scans"]:
            if scan["outcome"] == "exclude:behavioral":
                expected.add((*_planted_key(scan), "behavioral-qc"))
            elif scan["outcome"] == "exclude:motion":
                expected.add((*_planted_key(scan), "motion"))

        # Sanity: the plant actually contained one of each (guards the test
        # itself against a silently-empty expectation).
        sources = {src for *_rest, src in expected}
        assert sources == {
            "behavioral-qc",
            "motion",
        }, f"plant should contain one behavioral + one motion scan; got {sources}"

        compiled_set = result.excluded_keys_with_source()
        assert compiled_set == expected, (
            "compiled QC exclusion set != planted set\n"
            f"  missing (planted, not compiled): {expected - compiled_set}\n"
            f"  extra (compiled, not planted):   {compiled_set - expected}"
        )

    def test_collection_scan_is_covered_by_rendered_bidsignore(self, cohort):
        """The exclude:collection scan is covered by a glob line in the rendered
        .bidsignore (static-collection layer), and is NOT a compiled QC entry."""
        root, manifest = cohort
        result = simulate_exclusions(root, manifest, dataset="sim")

        coll_scans = [s for s in manifest["scans"] if s["outcome"] == "exclude:collection"]
        assert len(coll_scans) == 1  # guard the plant
        scan = coll_scans[0]

        assert result.bidsignore is not None
        # The cohort plants the glob as the committed-collection style line;
        # the renderer folds it in verbatim ahead of the QC block.
        expected_glob = (
            f"{scan['subject']}/{scan['session']}/func/"
            f"{scan['subject']}_{scan['session']}_task-{scan['task']}_"
            f"{scan['run']}_echo-*_bold.*"
        )
        assert expected_glob in result.bidsignore.splitlines(), (
            f"collection glob {expected_glob!r} not found in rendered .bidsignore:\n"
            f"{result.bidsignore}"
        )

        # And it must NOT have leaked into the compiled QC entries (it passes
        # behavioral + motion QC; only the static layer excludes it).
        assert _planted_key(scan) not in result.excluded_keys()

    def test_keep_scans_are_not_excluded_by_either_layer(self, cohort):
        """No keep scan appears in the compiled QC set or the rendered glob lines."""
        root, manifest = cohort
        result = simulate_exclusions(root, manifest, dataset="sim")

        keep_scans = [s for s in manifest["scans"] if s["outcome"] == "keep"]
        assert keep_scans  # guard the plant

        excluded = result.excluded_keys()
        bidsignore_lines = result.bidsignore.splitlines() if result.bidsignore else []
        for scan in keep_scans:
            key = _planted_key(scan)
            assert key not in excluded, f"keep scan {key} wrongly in compiled QC set"
            # No glob line should reference a keep scan's run prefix.
            run_prefix = (
                f"{scan['subject']}_{scan['session']}_task-{scan['task']}_" f"{scan['run']}_"
            )
            offending = [ln for ln in bidsignore_lines if run_prefix in ln]
            assert (
                not offending
            ), f"keep scan {key} wrongly covered by .bidsignore line(s): {offending}"

    def test_compiled_lockfile_and_artifacts_are_hermetic(self, cohort):
        """The simulation writes its compiled artifacts under the work dir, not
        the version-controlled tree (proves the path redirect held)."""
        root, manifest = cohort
        result = simulate_exclusions(root, manifest, dataset="sim")

        compiled_json = result.exclusions_dir / "sim" / "compiled_exclusions.json"
        assert compiled_json.is_file()
        on_disk = json.loads(compiled_json.read_text())
        # Same entries the driver returned (round-trips through real compile).
        assert {(e["subject"], e["session"], e["task"], e["run"]) for e in on_disk} == (
            result.excluded_keys()
        )


# --------------------------------------------------------------------------- #
# Claim 2: lev1 honors exclusions + recovers a planted contrast.
# --------------------------------------------------------------------------- #
class TestLev1RecoveryAndExclusionHonoring:
    @staticmethod
    def _discover_run(manifest, subject, task):
        """Discover one (session, run, files) via the REAL FileFinder."""
        finder = FileFinder(manifest["bids_dir"], manifest["fmriprep_dir"])
        files = finder.get_files(
            subject,
            task,
            required_files=FileFinder.get_required_files_for_space("MNI"),
        )
        assert files, f"FileFinder found no complete runs for {subject}/{task}"
        session = sorted(files.keys())[0]
        run = sorted(files[session].keys())[0]
        return session, run, files[session][run]

    def test_planted_contrast_recovered_through_real_lev1_components(self, cohort):
        """Plant +5 incongruent-congruent into a KEEP scan's fMRIPrep BOLD at the
        discoverable path and recover it via the REAL lev1 component path."""
        root, manifest = cohort
        subject = "sub-s01"  # the ses-01 flanker keep scan

        # REAL discovery of the keep scan's complete run.
        session, run, run_files = self._discover_run(manifest, subject, TASK)
        tr = get_task_parameters(TASK)["tr"]

        # Build the design from the scan's REAL events via the REAL design code.
        events = pd.read_csv(run_files["events"], sep="\t")
        confounds = pd.DataFrame({"constant": np.ones(N_TRS)})
        design, _ = create_design_matrix(
            events_df=events,
            confounds_df=confounds,
            task_name=TASK,
            n_scans=N_TRS,
            tr=tr,
        )
        assert {"congruent", "incongruent"} <= set(design.columns)

        # Plant the known contrast and OVERWRITE the discovered fMRIPrep BOLD
        # so the rest of the path reads exactly the file FileFinder found.
        ts = plant_bold(design, PLANTED, noise_sd=0.5, seed=42)
        planted_img = as_4d_nifti(ts)
        nib.save(planted_img, str(run_files["mni_data"]))

        # REAL first-level fit (explicit mask so the uniform synthetic block is
        # not rejected by auto-masking — mask_img is a real fit_run_glm param).
        reloaded = nib.load(str(run_files["mni_data"]))
        fitted = fit_run_glm(
            reloaded,
            design,
            analysis_type="task",
            tr=tr,
            mask_img=make_mask(planted_img),
        )

        # REAL contrast formula + REAL saver (the same call the runner makes).
        formula = get_task_contrasts(TASK)["incongruent-congruent"]
        assert formula == "incongruent - congruent"  # guard config drift
        saved = compute_run_contrasts(
            fitted_glm=fitted,
            task_name=TASK,
            output_dir=root / "lev1_out",
            base_filename=f"{subject}_{session}_task-{TASK}_{run}",
            contrasts={"incongruent-congruent": formula},
        )

        effect_path = saved["incongruent-congruent"]["effect_size"]
        assert effect_path.exists()
        recovered = float(np.mean(nib.load(str(effect_path)).get_fdata()))

        # Directional + approximate-magnitude recovery. A flipped sign
        # (incongruent < congruent) or a zeroed contrast would fail here.
        assert recovered > 0, f"expected positive contrast, got {recovered}"
        assert recovered == pytest.approx(
            PLANTED_EFFECT, abs=1.0
        ), f"recovered {recovered:.3f} not within 1.0 of planted {PLANTED_EFFECT}"

    def test_lev1_exclusion_path_honors_excluded_scans(self, cohort):
        """The REAL lev1 exclusion path (load_exclusions over the compiled file
        + the runner's per-run key) honors the behavioral- and motion-excluded
        scans and lets the keep scan through."""
        root, manifest = cohort
        result = simulate_exclusions(root, manifest, dataset="sim")

        # The runner builds its key set from the compiled file via the REAL
        # analysis.core.utils.load_exclusions. Point it at the file the driver
        # compiled (hermetic copy under the work dir).
        compiled_file = result.exclusions_dir / "sim" / "compiled_exclusions.json"
        exclusion_keys = load_exclusions(compiled_file)

        # Build the runner's per-run key exactly as runner.process_single_run
        # does: f"{subj_id}_{session}_task-{task}_{run}" with subj_id normalised.
        def runner_key(scan):
            subj = normalize_subject_id(scan["subject"])
            return f"{subj}_{scan['session']}_task-{scan['task']}_{scan['run']}"

        by_outcome = {}
        for scan in manifest["scans"]:
            by_outcome.setdefault(scan["outcome"], []).append(scan)

        # Behavioral- and motion-excluded scans: the runner key must be in the
        # set (process_single_run early-returns "skip" for these).
        for outcome in ("exclude:behavioral", "exclude:motion"):
            scan = by_outcome[outcome][0]
            key = runner_key(scan)
            assert key in exclusion_keys, (
                f"{outcome} scan key {key!r} NOT honored by lev1 load_exclusions; "
                f"keys were {sorted(exclusion_keys)}"
            )

        # Keep scans: the runner key must NOT be in the set (processed normally).
        for scan in by_outcome["keep"]:
            key = runner_key(scan)
            assert (
                key not in exclusion_keys
            ), f"keep scan key {key!r} wrongly present in lev1 exclusion set"

    def test_is_excluded_agrees_on_planted_scans(self, cohort):
        """Cross-check via core.exclusions.is_excluded on the compiled entries:
        behavioral + motion scans are excluded; keep scans are not."""
        root, manifest = cohort
        result = simulate_exclusions(root, manifest, dataset="sim")
        compiled = result.compiled

        for scan in manifest["scans"]:
            subj, ses = scan["subject"], scan["session"]
            task, run = f"task-{scan['task']}", scan["run"]
            excluded = is_excluded(subj, ses, task, run, compiled)
            if scan["outcome"] in ("exclude:behavioral", "exclude:motion"):
                assert excluded, f"{scan['outcome']} scan should be is_excluded"
            else:
                # keep + exclude:collection are NOT compiled QC entries.
                assert not excluded, f"{scan['outcome']} scan should not be a compiled QC exclusion"
