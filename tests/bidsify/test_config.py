import json
from pathlib import Path

import pytest

from neuro_workflow.bidsify.config import (
    ACQUISITION_MAP,
    SKIP_ACQUISITIONS,
    load_reconciliation_config,
    map_acquisition,
)


class TestMapAcquisitionBaseTasks:
    @pytest.mark.parametrize(
        "label,expected_task",
        [
            ("task-rest_bold", "rest"),
            ("task-cuedTS_bold", "cuedTS"),
            ("task-directedForgetting_bold", "directedForgetting"),
            ("task-flanker_bold", "flanker"),
            ("task-goNogo_bold", "goNogo"),
            ("task-nBack_bold", "nBack"),
            ("task-shapeMatching_bold", "shapeMatching"),
            ("task-spatialTS_bold", "spatialTS"),
            ("task-stopSignal_bold", "stopSignal"),
        ],
    )
    def test_base_task(self, label, expected_task):
        result = map_acquisition(label)
        assert result["task"] == expected_task
        assert result["modality"] == "func"

    def test_typo_fix_shapeMaching(self):
        result = map_acquisition("task-shapeMaching_bold")
        assert result["task"] == "shapeMatching"
        assert result["modality"] == "func"

    def test_underscore_variant_stopSignal(self):
        result = map_acquisition("task_stopSignal_bold")
        assert result["task"] == "stopSignal"
        assert result["modality"] == "func"


class TestMapAcquisitionDualTasks:
    @pytest.mark.parametrize(
        "label,expected_task",
        [
            ("directed_forgetting_w_flanker_bold", "directedForgettingWFlanker"),
            ("stop_signal_w_directed_forgetting_bold", "stopSignalWDirectedForgetting"),
            ("stop_signal_w_flanker_bold", "stopSignalWFlanker"),
        ],
    )
    def test_dual_task(self, label, expected_task):
        result = map_acquisition(label)
        assert result["task"] == expected_task
        assert result["modality"] == "func"

    def test_verbose_variant_stop_signal_with_directed_forgetting(self):
        result = map_acquisition("task-stop_signal_with_directed_forgetting_bold")
        assert result["task"] == "stopSignalWDirectedForgetting"
        assert result["modality"] == "func"

    def test_abbreviated_variant_stop_with_df(self):
        result = map_acquisition("task-stop_with_df_bold")
        assert result["task"] == "stopSignalWDirectedForgetting"
        assert result["modality"] == "func"

    def test_abbreviated_variant_stop_with_flanker(self):
        result = map_acquisition("task-stop_with_flanker_bold")
        assert result["task"] == "stopSignalWFlanker"
        assert result["modality"] == "func"


class TestMapAcquisitionFieldmap:
    def test_fieldmap(self):
        result = map_acquisition("fmap-fieldmap")
        assert result["modality"] == "fmap"
        assert "task" not in result


class TestMapAcquisitionAnatomical:
    def test_t1w_mprage_promo(self):
        result = map_acquisition("T1w MPRAGE PROMO")
        assert result["modality"] == "anat"
        assert result["suffix"] == "T1w"
        assert result["acq"] == "MPRAGEPromo"

    def test_t1w_new_sag_mprage(self):
        result = map_acquisition("NEW Sag_MPRAGE_T1")
        assert result["modality"] == "anat"
        assert result["suffix"] == "T1w"
        assert result["acq"] == "SagMPRAGE"

    def test_t2w_cube_promo(self):
        result = map_acquisition("T2w CUBE PROMO .8mm sag")
        assert result["modality"] == "anat"
        assert result["suffix"] == "T2w"
        assert result["acq"] == "CubePromo"


class TestMapAcquisitionDiffusion:
    def test_dti_pe0_g105(self):
        result = map_acquisition("DTI_pe0_g105")
        assert result["modality"] == "dwi"
        assert result["dir"] == "AP"
        assert result["acq"] == "g105"

    def test_dti_pe1_g105(self):
        result = map_acquisition("DTI_pe1_g105")
        assert result["modality"] == "dwi"
        assert result["dir"] == "PA"
        assert result["acq"] == "g105"

    def test_dti_pe1_g71(self):
        result = map_acquisition("DTI_pe1_g71")
        assert result["modality"] == "dwi"
        assert result["dir"] == "PA"
        assert result["acq"] == "g71"


class TestMapAcquisitionSkip:
    @pytest.mark.parametrize(
        "label",
        ["3Plane Loc SSFSE", "GE HOS FOV28", "GE HOS FOV28_1", "GE HOS FOV28_2"],
    )
    def test_skip_localizer_and_shim(self, label):
        assert map_acquisition(label) is None
        assert label in SKIP_ACQUISITIONS


class TestMapAcquisitionUnknown:
    def test_unknown_returns_none(self):
        assert map_acquisition("totally_unknown_sequence") is None

    def test_empty_string_returns_none(self):
        assert map_acquisition("") is None


class TestSkipAcquisitions:
    def test_is_a_set(self):
        assert isinstance(SKIP_ACQUISITIONS, (set, frozenset))

    def test_contains_all_skip_labels(self):
        expected = {"3Plane Loc SSFSE", "GE HOS FOV28", "GE HOS FOV28_1", "GE HOS FOV28_2"}
        assert expected == SKIP_ACQUISITIONS


class TestLoadReconciliationConfig:
    def test_loads_json(self):
        config = load_reconciliation_config()
        assert isinstance(config, dict)

    def test_flywheel_project(self):
        config = load_reconciliation_config()
        assert config["flywheel_project"] == "r01network"

    def test_subject_aliases(self):
        config = load_reconciliation_config()
        assert config["subject_aliases"]["s19-2"] == "s19"
        assert config["subject_aliases"]["s29-2"] == "s29"
        assert config["subject_aliases"]["s43-2"] == "s43"

    def test_skip_subjects(self):
        config = load_reconciliation_config()
        assert "n01" in config["skip_subjects"]
        # ex26207 moved to subject_aliases (alias for s297)
        assert "ex26207" not in config["skip_subjects"]
        assert config["subject_aliases"]["ex26207"] == "s297"

    def test_samples_discovery(self):
        config = load_reconciliation_config()
        assert "s03" in config["samples"]["discovery"]
        assert len(config["samples"]["discovery"]) == 5

    def test_samples_validation(self):
        config = load_reconciliation_config()
        assert "s76" in config["samples"]["validation"]
        assert len(config["samples"]["validation"]) == 52
