import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "reproduce_cohort", Path(__file__).resolve().parents[2] / "scripts" / "reproduce_cohort.py"
)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def test_default_paths_unchanged():
    p = rc._resolve_cohort_paths("discovery")
    assert p["bids"] == Path("/scratch/users/logben/discovery_bids")
    assert p["committed_bidsignore"] == Path("/scratch/users/logben/discovery_bids/.bidsignore")


def test_bids_root_override_recomputes_derived_paths():
    root = Path("/oak/stanford/groups/russpold/data/network_grant/bids/discovery")
    p = rc._resolve_cohort_paths("discovery", bids_root=root)
    assert p["bids"] == root
    assert p["fmriprep_src"] == root / "derivatives" / "fmriprep_25.2.4"
    assert p["lev1_fe_dir"] == root / "derivatives" / "lev1_surface"
    assert p["committed_bidsignore"] == root / ".bidsignore"
    # snapshot / behavioral / decisions_tsv are NOT under the bids root
    assert p["snapshot"] == rc._COHORT_PATHS["discovery"]["snapshot"]
    assert p["behavioral"] == rc._OAK_BEHAVIORAL


def test_lev1_outliers_csv_override():
    p = rc._resolve_cohort_paths("discovery", lev1_outliers_csv=Path("/tmp/x.csv"))
    assert p["lev1_outliers_csv"] == Path("/tmp/x.csv")


def test_validation_cohort_retargets_too():
    root = Path("/oak/stanford/groups/russpold/data/network_grant/bids/validation")
    p = rc._resolve_cohort_paths("validation", bids_root=root)
    assert p["bids"] == root
    assert p["fmriprep_src"] == root / "derivatives" / "fmriprep_25.2.4"
    assert p["lev1_fe_dir"] == root / "derivatives" / "lev1_surface"


def test_both_overrides_together():
    root = Path("/oak/x/discovery")
    p = rc._resolve_cohort_paths("discovery", bids_root=root, lev1_outliers_csv=Path("/tmp/y.csv"))
    assert p["bids"] == root
    assert p["lev1_outliers_csv"] == Path("/tmp/y.csv")
