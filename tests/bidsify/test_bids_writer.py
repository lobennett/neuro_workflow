import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from neuro_workflow.bidsify.bids_writer import (
    bids_filename,
    download_and_place,
    patch_sidecar,
    write_dataset_description,
)


class TestBidsFilename:
    def test_bids_filename_bold_echo(self):
        result = bids_filename("s03", "ses-01", task="rest", run=1, echo=1, suffix="bold")
        assert result == "sub-s03_ses-01_task-rest_run-1_echo-1_bold"

    def test_bids_filename_fieldmap(self):
        result = bids_filename("s03", "ses-01", run=1, suffix="fieldmap")
        assert result == "sub-s03_ses-01_run-1_fieldmap"

    def test_bids_filename_magnitude(self):
        result = bids_filename("s03", "ses-01", run=1, suffix="magnitude")
        assert result == "sub-s03_ses-01_run-1_magnitude"

    def test_bids_filename_t1w_with_acq(self):
        result = bids_filename("s03", "ses-04", acq="MPRAGEPromo", suffix="T1w")
        assert result == "sub-s03_ses-04_acq-MPRAGEPromo_T1w"

    def test_bids_filename_dwi(self):
        result = bids_filename("s03", "ses-01", acq="g105", dir="AP", run=1, suffix="dwi")
        assert result == "sub-s03_ses-01_acq-g105_dir-AP_run-1_dwi"

    def test_bids_filename_physio(self):
        result = bids_filename(
            "s1175", "ses-02", task="rest", run=1, recording="cardiac", suffix="physio"
        )
        assert result == "sub-s1175_ses-02_task-rest_run-1_recording-cardiac_physio"


class TestPatchSidecar:
    def test_patch_sidecar_adds_b0field_to_fieldmap(self, tmp_path):
        sidecar = tmp_path / "fieldmap.json"
        sidecar.write_text(json.dumps({"RepetitionTime": 2.0}))

        patch_sidecar(sidecar, b0_field_identifier="fmap_rest")

        data = json.loads(sidecar.read_text())
        assert data["B0FieldIdentifier"] == "fmap_rest"
        assert data["RepetitionTime"] == 2.0

    def test_patch_sidecar_adds_b0field_source_to_bold(self, tmp_path):
        sidecar = tmp_path / "bold.json"
        sidecar.write_text(json.dumps({"TaskName": "rest"}))

        patch_sidecar(sidecar, b0_field_source="fmap_rest")

        data = json.loads(sidecar.read_text())
        assert data["B0FieldSource"] == "fmap_rest"
        assert data["TaskName"] == "rest"


class TestWriteDatasetDescription:
    def test_write_dataset_description(self, tmp_path):
        output_dir = tmp_path / "bids_output"
        write_dataset_description(output_dir, "My Dataset")

        desc_path = output_dir / "dataset_description.json"
        assert desc_path.exists()

        data = json.loads(desc_path.read_text())
        assert data["Name"] == "My Dataset"
        assert data["BIDSVersion"] == "1.10.0"
        assert data["DatasetType"] == "raw"
        assert data["Authors"] == ["Patrick Bissett", "Russell Poldrack", "Logan Bennett"]
        assert data["GeneratedBy"] == [
            {"Name": "neuro-workflow bidsify", "Version": "0.2.0"}
        ]


class TestDownloadAndPlace:
    def test_download_and_place(self, tmp_path):
        acq = MagicMock()
        file_obj = MagicMock()
        file_obj.name = "bold.nii.gz"
        file_obj.size = 1024
        file_obj.created = "2025-01-01T00:00:00"

        dest_path = tmp_path / "sub-s03" / "ses-01" / "func" / "bold.nii.gz"

        result = download_and_place(acq, file_obj, dest_path)

        acq.download_file.assert_called_once_with("bold.nii.gz", str(dest_path))
        assert dest_path.parent.exists()
        assert result == {
            "fw_filename": "bold.nii.gz",
            "bids_path": str(dest_path),
            "size": 1024,
            "created": "2025-01-01T00:00:00",
        }
