"""Tests for BOLD analyzer module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from neuro_workflow.bids_validation.bold_analyzer import (
    BoldAnalyzer,
    ScanCategory,
    ScanIssue,
)


class TestScanIssue:
    """Tests for ScanIssue dataclass."""

    def test_scan_issue_creation(self) -> None:
        """Test basic ScanIssue instantiation."""
        issue = ScanIssue(
            subject="s03",
            session=1,
            task="goNogo",
            category=ScanCategory.SHORT_SCAN,
            reason="Duration too short",
            filepath="/path/to/bold.nii.gz",
        )
        assert issue.subject == "s03"
        assert issue.session == 1
        assert issue.task == "goNogo"
        assert issue.run is None
        assert issue.echo is None

    def test_bidsignore_entry_minimal(self) -> None:
        """Test .bidsignore entry generation without run/echo."""
        issue = ScanIssue(
            subject="s03",
            session=1,
            task="goNogo",
            category=ScanCategory.SHORT_SCAN,
            reason="Duration too short",
            filepath="/path/to/bold.nii.gz",
        )
        entry = issue.bidsignore_entry
        assert entry == "sub-s03/ses-01/func/*task-goNogo_bold*"

    def test_bidsignore_entry_with_run_and_echo(self) -> None:
        """Test .bidsignore entry generation with run and echo."""
        issue = ScanIssue(
            subject="s03",
            session=1,
            task="goNogo",
            run=1,
            echo=2,
            category=ScanCategory.SHORT_SCAN,
            reason="Duration too short",
            filepath="/path/to/bold.nii.gz",
        )
        entry = issue.bidsignore_entry
        assert entry == "sub-s03/ses-01/func/*task-goNogo_run-1_echo-2_bold*"

    def test_bidsignore_entry_with_run_only(self) -> None:
        """Test .bidsignore entry generation with run but no echo."""
        issue = ScanIssue(
            subject="s03",
            session=1,
            task="goNogo",
            run=2,
            category=ScanCategory.SHORT_SCAN,
            reason="Duration too short",
            filepath="/path/to/bold.nii.gz",
        )
        entry = issue.bidsignore_entry
        assert entry == "sub-s03/ses-01/func/*task-goNogo_run-2_bold*"

    def test_bidsignore_entry_session_formatting(self) -> None:
        """Test that session is zero-padded to 2 digits."""
        issue = ScanIssue(
            subject="s03",
            session=5,
            task="rest",
            category=ScanCategory.THREE_D,
            reason="3D scan",
            filepath="/path/to/bold.nii.gz",
        )
        entry = issue.bidsignore_entry
        assert "ses-05" in entry

    def test_bidsignore_comment_minimal(self) -> None:
        """Test comment generation without metrics."""
        issue = ScanIssue(
            subject="s03",
            session=1,
            task="goNogo",
            category=ScanCategory.MISSING_TR,
            reason="RepetitionTime not found",
            filepath="/path/to/bold.nii.gz",
        )
        comment = issue.bidsignore_comment
        assert "sub-s03" in comment
        assert "ses-01" in comment
        assert "RepetitionTime not found" in comment

    def test_bidsignore_comment_with_duration_and_tr(self) -> None:
        """Test comment generation with duration and TR metrics."""
        issue = ScanIssue(
            subject="s03",
            session=1,
            task="goNogo",
            category=ScanCategory.SHORT_SCAN,
            reason="Scan duration below threshold",
            filepath="/path/to/bold.nii.gz",
            duration_seconds=90.0,
            tr_seconds=2.0,
        )
        comment = issue.bidsignore_comment
        assert "90.0s" in comment
        assert "TR: 2.0s" in comment


class TestBoldAnalyzerInitialization:
    """Tests for BoldAnalyzer initialization."""

    def test_bold_analyzer_initialization(self, tmp_path: Path) -> None:
        """Test BoldAnalyzer initialization with default parameters."""
        analyzer = BoldAnalyzer(tmp_path)
        assert analyzer.bids_dir == tmp_path
        assert analyzer.tr_threshold_seconds == 180.0  # 3 minutes default
        assert analyzer.verbose is False

    def test_bold_analyzer_custom_threshold(self, tmp_path: Path) -> None:
        """Test BoldAnalyzer with custom TR threshold."""
        analyzer = BoldAnalyzer(tmp_path, tr_threshold_minutes=5.0)
        assert analyzer.tr_threshold_seconds == 300.0

    def test_bold_analyzer_verbose(self, tmp_path: Path) -> None:
        """Test BoldAnalyzer with verbose mode enabled."""
        analyzer = BoldAnalyzer(tmp_path, verbose=True)
        assert analyzer.verbose is True


class TestParseFilename:
    """Tests for BOLD filename parsing."""

    def test_parse_bold_filename_all_components(self, tmp_path: Path) -> None:
        """Test parsing filename with all components."""
        analyzer = BoldAnalyzer(tmp_path)
        bold_file = tmp_path / "sub-s03_ses-01_task-goNogo_run-1_echo-2_bold.nii.gz"

        result = analyzer._parse_bold_filename(bold_file)
        assert result is not None
        subject, session, task, run, echo = result
        assert subject == "s03"
        assert session == 1
        assert task == "goNogo"
        assert run == 1
        assert echo == 2

    def test_parse_bold_filename_minimal(self, tmp_path: Path) -> None:
        """Test parsing filename with minimal components."""
        analyzer = BoldAnalyzer(tmp_path)
        bold_file = tmp_path / "sub-s03_ses-01_task-rest_bold.nii.gz"

        result = analyzer._parse_bold_filename(bold_file)
        assert result is not None
        subject, session, task, run, echo = result
        assert subject == "s03"
        assert session == 1
        assert task == "rest"
        assert run is None
        assert echo is None

    def test_parse_bold_filename_with_run(self, tmp_path: Path) -> None:
        """Test parsing filename with run but no echo."""
        analyzer = BoldAnalyzer(tmp_path)
        bold_file = tmp_path / "sub-s03_ses-01_task-goNogo_run-2_bold.nii.gz"

        result = analyzer._parse_bold_filename(bold_file)
        assert result is not None
        subject, session, task, run, echo = result
        assert run == 2
        assert echo is None

    def test_parse_bold_filename_invalid(self, tmp_path: Path) -> None:
        """Test parsing invalid BOLD filename."""
        analyzer = BoldAnalyzer(tmp_path)
        bold_file = tmp_path / "invalid_filename.nii.gz"

        result = analyzer._parse_bold_filename(bold_file)
        assert result is None

    def test_parse_bold_filename_no_session(self, tmp_path: Path) -> None:
        """Test parsing filename without session (invalid BIDS)."""
        analyzer = BoldAnalyzer(tmp_path)
        bold_file = tmp_path / "sub-s03_task-goNogo_bold.nii.gz"

        result = analyzer._parse_bold_filename(bold_file)
        assert result is None


class TestGetTrFromJson:
    """Tests for TR extraction from JSON sidecar."""

    def test_tr_from_json_exists(self, tmp_path: Path) -> None:
        """Test TR extraction from valid JSON sidecar."""
        analyzer = BoldAnalyzer(tmp_path)
        json_file = tmp_path / "bold.json"
        json_file.write_text(json.dumps({"RepetitionTime": 2.0}))

        tr = analyzer._get_tr_from_json(json_file)
        assert tr == 2.0

    def test_tr_from_json_missing_field(self, tmp_path: Path) -> None:
        """Test TR extraction when RepetitionTime field is missing."""
        analyzer = BoldAnalyzer(tmp_path)
        json_file = tmp_path / "bold.json"
        json_file.write_text(json.dumps({"EchoTime": 0.03}))

        tr = analyzer._get_tr_from_json(json_file)
        assert tr is None

    def test_tr_from_json_file_missing(self, tmp_path: Path) -> None:
        """Test TR extraction when JSON sidecar does not exist."""
        analyzer = BoldAnalyzer(tmp_path)
        json_file = tmp_path / "nonexistent.json"

        tr = analyzer._get_tr_from_json(json_file)
        assert tr is None

    def test_tr_from_json_malformed(self, tmp_path: Path) -> None:
        """Test TR extraction from malformed JSON."""
        analyzer = BoldAnalyzer(tmp_path)
        json_file = tmp_path / "bold.json"
        json_file.write_text("{invalid json")

        tr = analyzer._get_tr_from_json(json_file)
        assert tr is None


class TestAnalyzeBoldFile:
    """Tests for BOLD file analysis."""

    def test_analyze_bold_file_normal_scan(self, tmp_path: Path) -> None:
        """Test analysis of a normal BOLD scan."""
        # Create proper BIDS structure
        func_dir = tmp_path / "sub-s03" / "ses-01" / "func"
        func_dir.mkdir(parents=True)

        bold_file = func_dir / "sub-s03_ses-01_task-rest_bold.nii.gz"
        json_file = func_dir / "sub-s03_ses-01_task-rest_bold.json"

        bold_file.write_text("")  # Placeholder
        json_file.write_text(json.dumps({"RepetitionTime": 2.0}))

        analyzer = BoldAnalyzer(tmp_path)

        # Mock nibabel to return a 4D image with many timepoints
        mock_img = MagicMock()
        mock_img.shape = (64, 64, 32, 500)  # 4D image with 500 timepoints

        with patch("neuro_workflow.bids_validation.bold_analyzer.nib") as mock_nib:
            mock_nib.load.return_value = mock_img
            issue = analyzer._analyze_bold_file(bold_file)
            assert issue is None  # No issues for normal scan

    def test_analyze_bold_file_3d_scan(self, tmp_path: Path) -> None:
        """Test detection of 3D BOLD scan."""
        # Create proper BIDS structure
        func_dir = tmp_path / "sub-s03" / "ses-01" / "func"
        func_dir.mkdir(parents=True)

        bold_file = func_dir / "sub-s03_ses-01_task-rest_bold.nii.gz"
        json_file = func_dir / "sub-s03_ses-01_task-rest_bold.json"

        bold_file.write_text("")
        json_file.write_text(json.dumps({"RepetitionTime": 2.0}))

        analyzer = BoldAnalyzer(tmp_path)

        # Mock 3D image
        mock_img = MagicMock()
        mock_img.shape = (64, 64, 32)  # 3D image

        with patch("neuro_workflow.bids_validation.bold_analyzer.nib") as mock_nib:
            mock_nib.load.return_value = mock_img
            issue = analyzer._analyze_bold_file(bold_file)
            assert issue is not None
            assert issue.category == ScanCategory.THREE_D
            assert "3D scan" in issue.reason
            assert issue.tr_seconds == 2.0

    def test_analyze_bold_file_short_scan(self, tmp_path: Path) -> None:
        """Test detection of short BOLD scan."""
        # Create proper BIDS structure
        func_dir = tmp_path / "sub-s03" / "ses-01" / "func"
        func_dir.mkdir(parents=True)

        bold_file = func_dir / "sub-s03_ses-01_task-rest_bold.nii.gz"
        json_file = func_dir / "sub-s03_ses-01_task-rest_bold.json"

        bold_file.write_text("")
        json_file.write_text(json.dumps({"RepetitionTime": 2.0}))

        analyzer = BoldAnalyzer(tmp_path, tr_threshold_minutes=3.0)

        # Mock 4D image with only 50 timepoints (100 seconds total)
        mock_img = MagicMock()
        mock_img.shape = (64, 64, 32, 50)

        with patch("neuro_workflow.bids_validation.bold_analyzer.nib") as mock_nib:
            mock_nib.load.return_value = mock_img
            issue = analyzer._analyze_bold_file(bold_file)
            assert issue is not None
            assert issue.category == ScanCategory.SHORT_SCAN
            assert issue.duration_seconds == 100.0
            assert issue.timepoints == 50
            assert issue.tr_seconds == 2.0
            assert "100.0s" in issue.reason

    def test_analyze_bold_file_missing_json(self, tmp_path: Path) -> None:
        """Test detection of missing JSON sidecar."""
        analyzer = BoldAnalyzer(tmp_path)

        bold_file = tmp_path / "sub-s03_ses-01_task-rest_bold.nii.gz"
        bold_file.write_text("")

        issue = analyzer._analyze_bold_file(bold_file)
        assert issue is not None
        assert issue.category == ScanCategory.MISSING_METADATA
        assert "Missing JSON sidecar" in issue.reason

    def test_analyze_bold_file_missing_tr(self, tmp_path: Path) -> None:
        """Test detection of missing RepetitionTime in JSON."""
        # Create proper BIDS structure
        func_dir = tmp_path / "sub-s03" / "ses-01" / "func"
        func_dir.mkdir(parents=True)

        bold_file = func_dir / "sub-s03_ses-01_task-rest_bold.nii.gz"
        json_file = func_dir / "sub-s03_ses-01_task-rest_bold.json"

        bold_file.write_text("")
        json_file.write_text(json.dumps({"EchoTime": 0.03}))

        analyzer = BoldAnalyzer(tmp_path)

        with patch("neuro_workflow.bids_validation.bold_analyzer.nib") as mock_nib:
            # Even though nib won't be called, we patch it to avoid any issues
            issue = analyzer._analyze_bold_file(bold_file)
            assert issue is not None
            assert issue.category == ScanCategory.MISSING_TR
            assert "RepetitionTime" in issue.reason

    def test_analyze_bold_file_corrupt_nifti(self, tmp_path: Path) -> None:
        """Test detection of corrupt NIfTI file."""
        # Create proper BIDS structure
        func_dir = tmp_path / "sub-s03" / "ses-01" / "func"
        func_dir.mkdir(parents=True)

        bold_file = func_dir / "sub-s03_ses-01_task-rest_bold.nii.gz"
        json_file = func_dir / "sub-s03_ses-01_task-rest_bold.json"

        bold_file.write_text("")
        json_file.write_text(json.dumps({"RepetitionTime": 2.0}))

        analyzer = BoldAnalyzer(tmp_path)

        with patch("neuro_workflow.bids_validation.bold_analyzer.nib") as mock_nib:
            mock_nib.load.side_effect = RuntimeError("Unable to read NIfTI file")
            issue = analyzer._analyze_bold_file(bold_file)
            assert issue is not None
            assert issue.category == ScanCategory.CORRUPT_NIFTI
            assert "RuntimeError" in issue.reason
            assert issue.tr_seconds == 2.0

    def test_analyze_bold_file_nibabel_not_installed(self, tmp_path: Path) -> None:
        """Test graceful handling when nibabel is not installed."""
        # Create proper BIDS structure
        func_dir = tmp_path / "sub-s03" / "ses-01" / "func"
        func_dir.mkdir(parents=True)

        bold_file = func_dir / "sub-s03_ses-01_task-rest_bold.nii.gz"
        json_file = func_dir / "sub-s03_ses-01_task-rest_bold.json"

        bold_file.write_text("")
        json_file.write_text(json.dumps({"RepetitionTime": 2.0}))

        analyzer = BoldAnalyzer(tmp_path)

        # Mock nib to be None (simulating nibabel not installed)
        with patch("neuro_workflow.bids_validation.bold_analyzer.nib", None):
            issue = analyzer._analyze_bold_file(bold_file)
            # Should return None, not raise exception
            assert issue is None


class TestGenerateBidsignoreEntries:
    """Tests for .bidsignore entry generation."""

    def test_generate_bidsignore_entries_no_issues(self, tmp_path: Path) -> None:
        """Test generation when no issues are found."""
        analyzer = BoldAnalyzer(tmp_path)

        with patch.object(analyzer, "analyze", return_value={}):
            result = analyzer.generate_bidsignore_entries()
            assert "No BOLD issues detected" in result

    def test_generate_bidsignore_entries_with_issues(self, tmp_path: Path) -> None:
        """Test generation with actual issues."""
        analyzer = BoldAnalyzer(tmp_path)

        issues = {
            "short_scan": [
                ScanIssue(
                    subject="s03",
                    session=1,
                    task="goNogo",
                    run=1,
                    category=ScanCategory.SHORT_SCAN,
                    reason="Duration too short",
                    filepath="/path/to/bold.nii.gz",
                    duration_seconds=100.0,
                    tr_seconds=2.0,
                ),
            ],
            "three_d": [
                ScanIssue(
                    subject="s03",
                    session=1,
                    task="rest",
                    category=ScanCategory.THREE_D,
                    reason="3D scan",
                    filepath="/path/to/bold.nii.gz",
                    tr_seconds=2.0,
                ),
            ],
        }

        with patch.object(analyzer, "analyze", return_value=issues):
            result = analyzer.generate_bidsignore_entries()
            assert "Short Scan" in result
            assert "Three D" in result
            assert "sub-s03/ses-01/func/*task-goNogo_run-1_bold*" in result
            assert "sub-s03/ses-01/func/*task-rest_bold*" in result

    def test_generate_bidsignore_entries_exclude_categories(self, tmp_path: Path) -> None:
        """Test filtering of categories in output."""
        analyzer = BoldAnalyzer(tmp_path)

        issues = {
            "short_scan": [
                ScanIssue(
                    subject="s03",
                    session=1,
                    task="goNogo",
                    category=ScanCategory.SHORT_SCAN,
                    reason="Duration too short",
                    filepath="/path/to/bold.nii.gz",
                ),
            ],
            "three_d": [
                ScanIssue(
                    subject="s03",
                    session=1,
                    task="rest",
                    category=ScanCategory.THREE_D,
                    reason="3D scan",
                    filepath="/path/to/bold.nii.gz",
                ),
            ],
        }

        with patch.object(analyzer, "analyze", return_value=issues):
            result = analyzer.generate_bidsignore_entries(exclude_categories=["three_d"])
            assert "Short Scan" in result
            assert "Three D" not in result
            assert "sub-s03/ses-01/func/*task-rest_bold*" not in result
            assert "sub-s03/ses-01/func/*task-goNogo_bold*" in result


class TestAnalyzeFullDataset:
    """Tests for full dataset analysis."""

    def test_analyze_empty_dataset(self, tmp_path: Path) -> None:
        """Test analysis of dataset with no BOLD files."""
        analyzer = BoldAnalyzer(tmp_path)

        result = analyzer.analyze()
        assert result == {}

    def test_analyze_dataset_with_multiple_issues(self, tmp_path: Path) -> None:
        """Test analysis of dataset with multiple BOLD files and issues."""
        # Create BIDS directory structure
        func_dir = tmp_path / "sub-s03" / "ses-01" / "func"
        func_dir.mkdir(parents=True)

        # Create normal scan
        (func_dir / "sub-s03_ses-01_task-goNogo_run-1_bold.nii.gz").write_text("")
        (func_dir / "sub-s03_ses-01_task-goNogo_run-1_bold.json").write_text(
            json.dumps({"RepetitionTime": 2.0})
        )

        # Create short scan
        (func_dir / "sub-s03_ses-01_task-rest_bold.nii.gz").write_text("")
        (func_dir / "sub-s03_ses-01_task-rest_bold.json").write_text(
            json.dumps({"RepetitionTime": 2.0})
        )

        analyzer = BoldAnalyzer(tmp_path, tr_threshold_minutes=3.0)

        # Mock nibabel for the short scan only
        def mock_load(path):
            if "rest" in str(path):
                mock_img = MagicMock()
                mock_img.shape = (64, 64, 32, 50)  # 100 seconds, below 180s threshold
                return mock_img
            else:
                mock_img = MagicMock()
                mock_img.shape = (64, 64, 32, 500)  # 1000 seconds, above threshold
                return mock_img

        with patch("neuro_workflow.bids_validation.bold_analyzer.nib") as mock_nib:
            mock_nib.load.side_effect = mock_load
            result = analyzer.analyze()

        # Should have one short scan issue
        assert "short_scan" in result
        assert len(result["short_scan"]) == 1
        assert result["short_scan"][0].task == "rest"
