import pytest


def test_descriptive_single_task_parsing():
    """Descriptive filenames like stop_signal_single_task_network__fmri_results.csv"""
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("stop_signal_single_task_network__fmri_results.csv")
    assert result == "stopSignal"

def test_descriptive_single_task_with_copy_number():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("stop_signal_single_task_network__fmri_results (3).csv")
    assert result == "stopSignal"

def test_descriptive_dual_task_parsing():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("stop_signal_with_flanker__fmri_results.csv")
    assert result == "stopSignalWFlanker"

def test_bids_style_dash_separated():
    """BIDS-style like sub-s29_ses-01_task-stop-signal_desc-raw.csv"""
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("sub-s29_ses-01_task-stop-signal_desc-raw.csv")
    assert result == "stopSignal"

def test_bids_style_camelcase():
    """BIDS-style like sub-s76_ses-01_task-stopSignal_desc-beh.csv"""
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("sub-s76_ses-01_task-stopSignal_desc-beh.csv")
    assert result == "stopSignal"

def test_all_single_tasks():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    cases = {
        "flanker_single_task_network__fmri_results.csv": "flanker",
        "go_nogo_single_task_network__fmri_results.csv": "goNogo",
        "n_back_single_task_network__fmri_results.csv": "nBack",
        "cued_task_switching_single_task_network__fmri_results.csv": "cuedTS",
        "spatial_task_switching_single_task_network__fmri_results.csv": "spatialTS",
        "directed_forgetting_single_task_network__fmri_results.csv": "directedForgetting",
        "shape_matching_single_task_network__fmri_results.csv": "shapeMatching",
    }
    for filename, expected in cases.items():
        assert parse_csv_filename(filename) == expected, f"Failed for {filename}"

def test_all_dual_tasks():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    cases = {
        "stop_signal_with_directed_forgetting__fmri_results.csv": "stopSignalWDirectedForgetting",
        "directed_forgetting_with_flanker__fmri_results.csv": "directedForgettingWFlanker",
        "spatial_task_switching_with_cued_task_switching__fmri_results.csv": "spatialTSWCuedTS",
        "flanker_with_shape_matching__fmri_results.csv": "flankerWShapeMatching",
        "flanker_with_cued_task_switching__fmri_results.csv": "cuedTSWFlanker",
        "n_back_with_shape_matching__fmri_results.csv": "nBackWShapeMatching",
        "n_back_with_spatial_task_switching__fmri_results.csv": "nBackWSpatialTS",
        "shape_matching_with_cued_task_switching__fmri_results.csv": "shapeMatchingWCuedTS",
        "shape_matching_with_spatial_task_switching__fmri_results.csv": "spatialTSWShapeMatching",
        "cued_task_switching_with_directed_forgetting__fmri_results.csv": "directedForgettingWCuedTS",
    }
    for filename, expected in cases.items():
        assert parse_csv_filename(filename) == expected, f"Failed for {filename}"

def test_bids_style_dual_task():
    from scripts.rename_behavioral_to_sourcedata import parse_csv_filename
    result = parse_csv_filename("sub-s29_ses_11_task-stop_signal_with_flanker_desc_raw.csv")
    assert result == "stopSignalWFlanker"

def test_build_output_path():
    from scripts.rename_behavioral_to_sourcedata import build_output_path
    from pathlib import Path
    result = build_output_path(
        output_root=Path("/oak/data/sourcedata"),
        subject="s1035",
        session="ses-1",
        task_name="stopSignal",
    )
    assert result == Path("/oak/data/sourcedata/sub-s1035/ses-01/beh/sub-s1035_ses-01_task-stopSignal_beh.csv")

def test_build_output_path_already_padded():
    from scripts.rename_behavioral_to_sourcedata import build_output_path
    from pathlib import Path
    result = build_output_path(
        output_root=Path("/oak/data/sourcedata"),
        subject="s03",
        session="ses-01",
        task_name="flanker",
    )
    assert result == Path("/oak/data/sourcedata/sub-s03/ses-01/beh/sub-s03_ses-01_task-flanker_beh.csv")
