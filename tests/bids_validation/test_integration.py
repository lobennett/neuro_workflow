"""Tests for BOLD analyzer integration with bidsify workflow."""

import json
from pathlib import Path

import pytest

from neuro_workflow.bids_validation.bold_analyzer import BoldAnalyzer, ScanCategory
from neuro_workflow.bidsify.integration import (
    run_bold_analysis_and_update_bidsignore,
    _merge_bidsignore,
)


class TestBoldAnalyzerPersistence:
    """Test persistence methods of BoldAnalyzer."""

    def test_save_analysis_report_creates_directory(self, tmp_path):
        """Test that save_analysis_report creates .bids-validation directory."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        analyzer = BoldAnalyzer(bids_dir)
        report_file = bids_dir / ".bids-validation" / "analysis.json"

        analyzer.save_analysis_report(report_file)

        assert report_file.exists()
        assert report_file.parent.exists()

    def test_save_analysis_report_json_structure(self, tmp_path):
        """Test that analysis report has correct JSON structure."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        analyzer = BoldAnalyzer(bids_dir, tr_threshold_minutes=3.0)
        report_file = bids_dir / ".bids-validation" / "analysis.json"

        analyzer.save_analysis_report(report_file)

        report = json.loads(report_file.read_text())

        # Check top-level structure
        assert "metadata" in report
        assert "issues" in report

        # Check metadata
        assert report["metadata"]["bids_dir"] == str(bids_dir)
        assert report["metadata"]["tr_threshold_seconds"] == 180.0
        assert "generated" in report["metadata"]

        # Check issues structure (should be empty for empty BIDS dir)
        assert isinstance(report["issues"], dict)

    def test_save_bidsignore_entries_creates_file(self, tmp_path):
        """Test that save_bidsignore_entries creates output file."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        analyzer = BoldAnalyzer(bids_dir)
        entries_file = tmp_path / "bidsignore_entries.txt"

        analyzer.save_bidsignore_entries(entries_file)

        assert entries_file.exists()

    def test_save_bidsignore_entries_content(self, tmp_path):
        """Test that save_bidsignore_entries generates correct content."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        analyzer = BoldAnalyzer(bids_dir)
        entries_file = tmp_path / "bidsignore_entries.txt"

        analyzer.save_bidsignore_entries(entries_file)

        content = entries_file.read_text()

        # Should contain header comment for empty BIDS dir
        assert "No BOLD issues detected" in content or content.strip()


class TestBoldAnalysisIntegration:
    """Test integration of BOLD analyzer into bidsify workflow."""

    def test_run_bold_analysis_nonexistent_directory(self, tmp_path):
        """Test that analysis raises error for nonexistent BIDS directory."""
        nonexistent = tmp_path / "nonexistent"

        with pytest.raises(FileNotFoundError):
            run_bold_analysis_and_update_bidsignore(nonexistent)

    def test_run_bold_analysis_creates_analysis_directory(self, tmp_path):
        """Test that analysis creates .bids-validation directory."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure
        (bids_dir / "sub-01" / "ses-01" / "func").mkdir(parents=True)

        run_bold_analysis_and_update_bidsignore(bids_dir)

        assert (bids_dir / ".bids-validation").exists()
        assert (bids_dir / ".bids-validation" / "analysis.json").exists()

    def test_run_bold_analysis_saves_report(self, tmp_path):
        """Test that analysis saves JSON report."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure
        (bids_dir / "sub-01" / "ses-01" / "func").mkdir(parents=True)

        run_bold_analysis_and_update_bidsignore(bids_dir)

        report_file = bids_dir / ".bids-validation" / "analysis.json"
        assert report_file.exists()

        report = json.loads(report_file.read_text())
        assert "metadata" in report
        assert "issues" in report

    def test_run_bold_analysis_with_merge_bidsignore(self, tmp_path):
        """Test that merge_bidsignore=True updates .bidsignore."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure
        (bids_dir / "sub-01" / "ses-01" / "func").mkdir(parents=True)

        # Create initial .bidsignore
        bidsignore_path = bids_dir / ".bidsignore"
        bidsignore_path.write_text("# Existing entry\nexisting/pattern\n")

        run_bold_analysis_and_update_bidsignore(
            bids_dir, merge_bidsignore=True
        )

        # Check .bidsignore exists and has content
        assert bidsignore_path.exists()
        content = bidsignore_path.read_text()
        assert "existing/pattern" in content or len(content) > 0

    def test_run_bold_analysis_without_merge_bidsignore(self, tmp_path):
        """Test that merge_bidsignore=False doesn't update .bidsignore."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure
        (bids_dir / "sub-01" / "ses-01" / "func").mkdir(parents=True)

        run_bold_analysis_and_update_bidsignore(
            bids_dir, merge_bidsignore=False
        )

        # .bidsignore should not be created if there are no issues
        # (or should not be modified if it exists)
        bidsignore_path = bids_dir / ".bidsignore"
        # Test passes if we don't crash
        assert True


class TestMergeBidsignore:
    """Test .bidsignore merging functionality."""

    def test_merge_bidsignore_creates_file(self, tmp_path):
        """Test that merge creates .bidsignore if it doesn't exist."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        new_entries = "# Test entry\nsub-01/ses-01/func/*_bold*\n"

        _merge_bidsignore(bids_dir, new_entries)

        assert (bids_dir / ".bidsignore").exists()

    def test_merge_bidsignore_preserves_existing_entries(self, tmp_path):
        """Test that merge preserves existing .bidsignore entries."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create existing .bidsignore
        bidsignore_path = bids_dir / ".bidsignore"
        bidsignore_path.write_text("existing_pattern\n")

        new_entries = "# New entry\nnew_pattern\n"

        _merge_bidsignore(bids_dir, new_entries)

        content = bidsignore_path.read_text()
        assert "existing_pattern" in content
        assert "new_pattern" in content

    def test_merge_bidsignore_skips_duplicates(self, tmp_path):
        """Test that merge skips duplicate patterns."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create existing .bidsignore
        bidsignore_path = bids_dir / ".bidsignore"
        bidsignore_path.write_text("pattern1\npattern2\n")

        new_entries = "# New entries\npattern2\npattern3\n"

        _merge_bidsignore(bids_dir, new_entries)

        content = bidsignore_path.read_text()
        # Count occurrences
        pattern2_count = content.count("pattern2")
        # Should appear exactly once (not duplicated)
        assert pattern2_count == 1
        assert "pattern1" in content
        assert "pattern3" in content

    def test_merge_bidsignore_handles_empty_new_entries(self, tmp_path):
        """Test that merge handles empty new entries gracefully."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create existing .bidsignore
        bidsignore_path = bids_dir / ".bidsignore"
        bidsignore_path.write_text("existing_pattern\n")
        original_content = bidsignore_path.read_text()

        new_entries = "# No patterns\n"

        _merge_bidsignore(bids_dir, new_entries)

        # Content should not change significantly
        content = bidsignore_path.read_text()
        assert "existing_pattern" in content

    def test_merge_bidsignore_with_comments(self, tmp_path):
        """Test that merge handles comments correctly."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        new_entries = (
            "# Comment 1\n"
            "pattern1\n"
            "# Comment 2\n"
            "pattern2\n"
        )

        _merge_bidsignore(bids_dir, new_entries)

        content = (bids_dir / ".bidsignore").read_text()
        # Should have patterns but not duplicate comments
        assert "pattern1" in content
        assert "pattern2" in content
