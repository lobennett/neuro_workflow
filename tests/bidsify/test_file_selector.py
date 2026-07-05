"""Tests for bidsify file_selector module."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from neuro_workflow.bidsify.file_selector import select_files


def _make_file(name, file_type="nifti", size=100, created=None):
    f = MagicMock()
    f.name = name
    f.type = file_type
    f.size = size
    f.created = created or datetime(2021, 1, 1, tzinfo=UTC)
    return f


class TestSelectBoldMultiecho:
    def test_select_bold_multiecho(self):
        """Three echoes selected correctly from mixed files."""
        files = [
            _make_file("dicom.zip", file_type="dicom"),
            _make_file("bold_e1.nii.gz"),
            _make_file("bold_e2.nii.gz"),
            _make_file("bold_e3.nii.gz"),
            _make_file("bold_e1.json", file_type="source code"),
            _make_file("bold_e2.json", file_type="source code"),
            _make_file("bold_e3.json", file_type="source code"),
            _make_file("bold.nii.gz"),  # combined volume, should be skipped
        ]

        result = select_files(files, "func")

        assert len(result) == 3
        echoes = sorted(result, key=lambda r: r["echo"])
        assert echoes[0]["echo"] == 1
        assert echoes[0]["nifti"].name == "bold_e1.nii.gz"
        assert echoes[0]["json"].name == "bold_e1.json"
        assert echoes[1]["echo"] == 2
        assert echoes[2]["echo"] == 3

    def test_select_bold_prefers_newest_duplicate(self):
        """When duplicate NIfTIs exist for same echo, pick newest by .created."""
        old = datetime(2021, 1, 1, tzinfo=UTC)
        new = datetime(2021, 6, 1, tzinfo=UTC)

        files = [
            _make_file("bold_e1.nii.gz", size=100, created=old),
            _make_file("bold_e1.nii.gz", size=200, created=new),
            _make_file("bold_e1.json", file_type="source code", created=new),
        ]

        result = select_files(files, "func")

        assert len(result) == 1
        assert result[0]["nifti"].created == new
        assert result[0]["nifti"].size == 200


class TestSelectFieldmap:
    def test_select_fieldmap(self):
        """Returns fieldmap NIfTI, fieldmap JSON, and magnitude NIfTI."""
        files = [
            _make_file("scan_fieldmap.nii.gz"),
            _make_file("scan_fieldmap.json", file_type="source code"),
            _make_file("scan.nii.gz"),
            _make_file("qa_report.png", file_type="qa"),
        ]

        result = select_files(files, "fmap")

        assert result["fieldmap_nifti"].name == "scan_fieldmap.nii.gz"
        assert result["fieldmap_json"].name == "scan_fieldmap.json"
        assert result["magnitude_nifti"].name == "scan.nii.gz"


class TestSelectAnat:
    def test_select_anat(self):
        """Picks newest NIfTI and newest JSON."""
        old = datetime(2021, 1, 1, tzinfo=UTC)
        new = datetime(2021, 6, 1, tzinfo=UTC)

        files = [
            _make_file("t1w.nii.gz", created=old),
            _make_file("t1w_v2.nii.gz", created=new),
            _make_file("t1w.json", file_type="source code", created=old),
            _make_file("t1w_v2.json", file_type="source code", created=new),
            _make_file("montage.png", file_type="montage"),
        ]

        result = select_files(files, "anat")

        assert result["nifti"].name == "t1w_v2.nii.gz"
        assert result["json"].name == "t1w_v2.json"


class TestSelectDwi:
    def test_select_dwi(self):
        """Picks newest NIfTI + JSON + bval + bvec."""
        files = [
            _make_file("dwi.nii.gz"),
            _make_file("dwi.json", file_type="source code"),
            _make_file("dwi.bval", file_type="bval"),
            _make_file("dwi.bvec", file_type="bvec"),
            _make_file("pfile.7", file_type="pfile"),
        ]

        result = select_files(files, "dwi")

        assert result["nifti"].name == "dwi.nii.gz"
        assert result["json"].name == "dwi.json"
        assert result["bval"].name == "dwi.bval"
        assert result["bvec"].name == "dwi.bvec"
