import json
from pathlib import Path

ACQUISITION_MAP = {
    "task-rest_bold": {"modality": "func", "task": "rest"},
    "task-cuedTS_bold": {"modality": "func", "task": "cuedTS"},
    "task-directedForgetting_bold": {"modality": "func", "task": "directedForgetting"},
    "task-flanker_bold": {"modality": "func", "task": "flanker"},
    "task-goNogo_bold": {"modality": "func", "task": "goNogo"},
    "task-nBack_bold": {"modality": "func", "task": "nBack"},
    "task-shapeMatching_bold": {"modality": "func", "task": "shapeMatching"},
    "task-shapeMaching_bold": {"modality": "func", "task": "shapeMatching"},
    "task-spatialTS_bold": {"modality": "func", "task": "spatialTS"},
    "task-stopSignal_bold": {"modality": "func", "task": "stopSignal"},
    "task_stopSignal_bold": {"modality": "func", "task": "stopSignal"},
    "directed_forgetting_w_flanker_bold": {"modality": "func", "task": "directedForgettingWFlanker"},
    "stop_signal_w_directed_forgetting_bold": {"modality": "func", "task": "stopSignalWDirectedForgetting"},
    "stop_signal_w_flanker_bold": {"modality": "func", "task": "stopSignalWFlanker"},
    "task-stop_signal_with_directed_forgetting_bold": {"modality": "func", "task": "stopSignalWDirectedForgetting"},
    "task-stop_with_df_bold": {"modality": "func", "task": "stopSignalWDirectedForgetting"},
    "task-stop_with_flanker_bold": {"modality": "func", "task": "stopSignalWFlanker"},
    "fmap-fieldmap": {"modality": "fmap"},
    "T1w MPRAGE PROMO": {"modality": "anat", "suffix": "T1w", "acq": "MPRAGEPromo"},
    "NEW Sag_MPRAGE_T1": {"modality": "anat", "suffix": "T1w", "acq": "SagMPRAGE"},
    "T2w CUBE PROMO .8mm sag": {"modality": "anat", "suffix": "T2w", "acq": "CubePromo"},
    "DTI_pe0_g105": {"modality": "dwi", "dir": "AP", "acq": "g105"},
    "DTI_pe1_g105": {"modality": "dwi", "dir": "PA", "acq": "g105"},
    "DTI_pe1_g71": {"modality": "dwi", "dir": "PA", "acq": "g71"},
}

SKIP_ACQUISITIONS = {
    "3Plane Loc SSFSE",
    "GE HOS FOV28",
    "GE HOS FOV28_1",
    "GE HOS FOV28_2",
}


def map_acquisition(label):
    if label in SKIP_ACQUISITIONS:
        return None
    return ACQUISITION_MAP.get(label)


def load_reconciliation_config():
    config_path = Path(__file__).parent / "reconciliation_config.json"
    with open(config_path) as f:
        return json.load(f)
