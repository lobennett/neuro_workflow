from argparse import Namespace
from pathlib import Path

from neuro_workflow.pipelines.lev2 import Lev2Pipeline, _discover_contrasts_from_lev1_dirs
from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_lev2_pipeline_is_registered():
    pipeline = get_pipeline("lev2")
    assert pipeline is not None
    assert pipeline.name == "lev2"


def test_lev2_has_no_docker_uri():
    p = Lev2Pipeline()
    assert p.docker_uri is None


def test_lev2_default_resources():
    p = Lev2Pipeline()
    assert p.default_resources["nthreads"] == 2
    assert p.default_resources["mem_gb"] == 4
    assert p.default_resources["time"] == "04:00:00"


def test_lev2_template_exists():
    p = Lev2Pipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_discover_contrasts_from_lev1_dirs(tmp_path):
    """Create fake fixed-effects files and verify discovery."""
    # Subject 1: flanker task
    fe_dir1 = tmp_path / "sub-s03" / "task-flanker" / "fixed_effects"
    fe_dir1.mkdir(parents=True)
    (fe_dir1 / "sub-s03_task-flanker_contrast-incongruentGtCongruent_stat-fixed-effects.nii.gz").touch()
    (fe_dir1 / "sub-s03_task-flanker_contrast-congruentGtIncongruent_stat-fixed-effects.nii.gz").touch()

    # Subject 2: flanker task (same contrasts)
    fe_dir2 = tmp_path / "sub-s10" / "task-flanker" / "fixed_effects"
    fe_dir2.mkdir(parents=True)
    (fe_dir2 / "sub-s10_task-flanker_contrast-incongruentGtCongruent_stat-fixed-effects.nii.gz").touch()

    # Subject 1: stroop task
    fe_dir3 = tmp_path / "sub-s03" / "task-stroop" / "fixed_effects"
    fe_dir3.mkdir(parents=True)
    (fe_dir3 / "sub-s03_task-stroop_contrast-incongruentGtCongruent_stat-fixed-effects.nii.gz").touch()

    contrasts = _discover_contrasts_from_lev1_dirs([str(tmp_path)])
    assert len(contrasts) == 3
    assert "task-flanker_contrast-congruentGtIncongruent" in contrasts
    assert "task-flanker_contrast-incongruentGtCongruent" in contrasts
    assert "task-stroop_contrast-incongruentGtCongruent" in contrasts


def test_discover_contrasts_preserves_underscored_contrast_names(tmp_path):
    """Real lev1 outputs have multi-underscore contrast names like
    `cue_switch_cost`, `task_switch_cue_switch-task_stay_cue_stay`,
    `response_time`, `stop_success`. The discovery regex must capture
    the FULL contrast name, not truncate at the first underscore.

    Regression test for the bug discovered 2026-05-08 when discovery
    lev2 (job 24280825) produced contrast list entries like
    `task-cuedTS_contrast-cue` (truncated from `cue_switch_cost`),
    causing 23/34 array tasks to fail with `No input files found`.
    """
    fe_dir = tmp_path / "sub-s03" / "task-cuedTS" / "fixed_effects"
    fe_dir.mkdir(parents=True)
    # Real lev1 output naming: include _rtmodel-RTDur_ between contrast and stat
    (fe_dir / "sub-s03_task-cuedTS_contrast-cue_switch_cost_rtmodel-RTDur_stat-fixed-effects.nii.gz").touch()
    (fe_dir / "sub-s03_task-cuedTS_contrast-task_switch_cost_rtmodel-RTDur_stat-fixed-effects.nii.gz").touch()
    (fe_dir / "sub-s03_task-cuedTS_contrast-task-baseline_rtmodel-RTDur_stat-fixed-effects.nii.gz").touch()
    (fe_dir / "sub-s03_task-cuedTS_contrast-response_time_rtmodel-RTDur_stat-fixed-effects.nii.gz").touch()

    contrasts = _discover_contrasts_from_lev1_dirs([str(tmp_path)])
    assert "task-cuedTS_contrast-cue_switch_cost" in contrasts
    assert "task-cuedTS_contrast-task_switch_cost" in contrasts
    assert "task-cuedTS_contrast-task-baseline" in contrasts
    assert "task-cuedTS_contrast-response_time" in contrasts
    # And the truncated forms must NOT appear (would mean regex still broken)
    assert "task-cuedTS_contrast-cue" not in contrasts
    assert "task-cuedTS_contrast-task" not in contrasts
    assert "task-cuedTS_contrast-response" not in contrasts


def test_discover_contrasts_with_task_filter(tmp_path):
    """Task filter limits results to matching tasks only."""
    fe_flanker = tmp_path / "sub-s03" / "task-flanker" / "fixed_effects"
    fe_flanker.mkdir(parents=True)
    (fe_flanker / "sub-s03_task-flanker_contrast-incongruentGtCongruent_stat-fixed-effects.nii.gz").touch()

    fe_stroop = tmp_path / "sub-s03" / "task-stroop" / "fixed_effects"
    fe_stroop.mkdir(parents=True)
    (fe_stroop / "sub-s03_task-stroop_contrast-incongruentGtCongruent_stat-fixed-effects.nii.gz").touch()

    contrasts = _discover_contrasts_from_lev1_dirs([str(tmp_path)], task_filter=["flanker"])
    assert len(contrasts) == 1
    assert "task-flanker_contrast-incongruentGtCongruent" in contrasts


def test_lev2_build_context_explicit_contrasts(tmp_path):
    """Verify context dict when explicit contrasts are provided."""
    p = Lev2Pipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        lev1_dirs=["/path/to/lev1"],
        results_dir=str(tmp_path / "lev2_results"),
        contrasts=["task-flanker_contrast-incongruentGtCongruent", "task-stroop_contrast-test"],
        contrasts_flag=None,
        mask_threshold=0.9,
        num_permutations=5000,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["dataset_name"] == "test_ds"
    assert ctx["n_contrasts"] == 2
    assert ctx["nthreads"] == 2
    assert ctx["mem_gb"] == 4
    assert ctx["time"] == "04:00:00"
    assert ctx["partition"] == "russpold"
    assert ctx["mail_line"] == ""
    assert ctx["mask_threshold"] == 0.9
    assert ctx["num_permutations"] == 5000
    assert ctx["lev1_dirs"] == "/path/to/lev1"

    # Verify contrast list file was written
    contrast_list_file = Path(ctx["contrast_list_file"])
    assert contrast_list_file.exists()
    lines = contrast_list_file.read_text().strip().split("\n")
    assert len(lines) == 2
    assert "task-flanker_contrast-incongruentGtCongruent" in lines
    assert "task-stroop_contrast-test" in lines


def test_lev2_render_full_template(tmp_path):
    """Integration test: build context + render template produces valid script."""
    p = Lev2Pipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "partition": "russpold",
        "mail_user": None,
    }
    args = Namespace(
        lev1_dirs=["/path/to/lev1a", "/path/to/lev1b"],
        results_dir=str(tmp_path / "lev2_results"),
        contrasts=["task-flanker_contrast-test"],
        contrasts_flag=None,
        mask_threshold=0.9,
        num_permutations=5000,
        nthreads=None,
        mem_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "#SBATCH -J lev2_test_ds" in script
    assert "#SBATCH --array=1-1" in script
    assert "#SBATCH --cpus-per-task=2" in script
    assert "#SBATCH --mem=4G" in script
    assert "#SBATCH --time=04:00:00" in script
    assert "#SBATCH -p russpold" in script
    assert "--mask-threshold 0.9" in script
    assert "--num-permutations 5000" in script
    assert "--level1-dirs /path/to/lev1a /path/to/lev1b" in script
    assert "--mail-user" not in script
