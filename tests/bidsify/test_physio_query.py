"""Tests for physio Flywheel query module."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from neuro_workflow.bidsify.physio_query import (
    find_gephysio_analyses,
    match_analyses_to_acquisitions,
)


def _make_analysis(label, gear_name, input_name, input_acq_id, files=None, created=None):
    """Create a mock Flywheel analysis object."""
    a = MagicMock()
    a.label = label
    a.gear_info = {"name": gear_name}
    a.created = created or datetime(2026, 1, 29, tzinfo=UTC)
    a.files = files or []

    # Mock the input object
    inp = MagicMock()
    inp._name = input_name
    inp._parents = {"acquisition": input_acq_id}
    a.inputs = [inp]

    # reload returns self
    a.reload.return_value = a

    return a


def _make_file(name, ftype="tabular data", size=100):
    f = MagicMock()
    f.name = name
    f.type = ftype
    f.size = size
    return f


class TestFindGephysioAnalyses:
    def test_finds_gephysio_analyses(self):
        """Filters to only gephysio gear analyses with files."""
        gephysio_a = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq123",
            files=[_make_file("PPG_FltData.csv")],
        )
        other_a = _make_analysis(
            "mriqc 01/28/2026",
            "mriqc",
            "scan.nii.gz",
            "acq123",
            files=[_make_file("report.html")],
        )
        empty_a = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq456",
            files=[],
        )

        session = MagicMock()
        session.analyses = [gephysio_a, other_a, empty_a]

        result = find_gephysio_analyses(session)

        assert len(result) == 1
        assert result[0].label == "gephysio 01/28/2026"

    def test_picks_most_recent_batch(self):
        """When multiple runs exist, picks the most recently created."""
        old = _make_analysis(
            "gephysio 10/17/2025",
            "gephysio",
            "scan.gephysio.zip",
            "acq123",
            files=[_make_file("PPG_FltData.csv")],
            created=datetime(2025, 10, 17, tzinfo=UTC),
        )
        new = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq123",
            files=[_make_file("PPG_FltData.csv")],
            created=datetime(2026, 1, 28, tzinfo=UTC),
        )

        session = MagicMock()
        session.analyses = [old, new]

        result = find_gephysio_analyses(session)

        assert len(result) == 1
        assert result[0].created == datetime(2026, 1, 28, tzinfo=UTC)


class TestMatchAnalysesToAcquisitions:
    def test_matches_by_acquisition_id(self):
        """Maps analysis to acquisition via input._parents['acquisition']."""
        analysis = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq_rest",
            files=[_make_file("PPG_FltData.csv")],
        )

        acq_map = {"acq_rest": {"task": "rest", "run": 1}}

        result = match_analyses_to_acquisitions([analysis], acq_map)

        assert len(result) == 1
        assert result[0]["task"] == "rest"
        assert result[0]["run"] == 1
        assert result[0]["analysis"] is analysis

    def test_skips_unmatched_acquisition(self):
        """Analyses for unknown acquisitions are skipped."""
        analysis = _make_analysis(
            "gephysio 01/28/2026",
            "gephysio",
            "scan.gephysio.zip",
            "acq_unknown",
            files=[_make_file("PPG_FltData.csv")],
        )

        acq_map = {"acq_rest": {"task": "rest", "run": 1}}

        result = match_analyses_to_acquisitions([analysis], acq_map)

        assert len(result) == 0
