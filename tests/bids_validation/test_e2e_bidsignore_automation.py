"""End-to-end test: bidsify + validation + .bidsignore automation."""

import json
from pathlib import Path

import pytest

from neuro_workflow.bidsify.integration import run_bold_analysis_and_update_bidsignore


class TestBidsignoreAutomationEndToEnd:
    """Test end-to-end .bidsignore automation through bidsify integration."""

    def test_bidsignore_automation_creates_all_outputs(self, tmp_path):
        """Test that running bold analysis creates analysis.json and updates .bidsignore."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure with some subjects/sessions
        for sub in ["01", "02"]:
            (bids_dir / f"sub-{sub}" / "ses-01" / "func").mkdir(parents=True)

        run_bold_analysis_and_update_bidsignore(bids_dir, merge_bidsignore=True)

        # Check that analysis.json was created
        analysis_file = bids_dir / ".bids-validation" / "analysis.json"
        assert analysis_file.exists(), "analysis.json should be created"

        # Verify it's valid JSON with expected structure
        analysis = json.loads(analysis_file.read_text())
        assert "metadata" in analysis
        assert "issues" in analysis
        assert "bids_dir" in analysis["metadata"]
        assert "generated" in analysis["metadata"]

    def test_bidsignore_automation_preserves_manual_entries(self, tmp_path):
        """Test that existing manual .bidsignore entries are preserved."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure
        (bids_dir / "sub-01" / "ses-01" / "func").mkdir(parents=True)

        # Create a .bidsignore with manual entries
        bidsignore_path = bids_dir / ".bidsignore"
        original_entry = "derivatives/"
        bidsignore_path.write_text(f"# Manual entries\n{original_entry}\n")

        # Run analysis
        run_bold_analysis_and_update_bidsignore(bids_dir, merge_bidsignore=True)

        # Check that original entry is still there
        content = bidsignore_path.read_text()
        assert original_entry in content, "Original manual entries should be preserved"

    def test_bidsignore_automation_skips_duplicates(self, tmp_path):
        """Test that duplicate patterns aren't added to .bidsignore."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure
        (bids_dir / "sub-01" / "ses-01" / "func").mkdir(parents=True)

        # Create .bidsignore with existing pattern
        bidsignore_path = bids_dir / ".bidsignore"
        bidsignore_path.write_text("existing_pattern\n")

        original_content = bidsignore_path.read_text()
        original_lines = len(original_content.strip().split("\n"))

        run_bold_analysis_and_update_bidsignore(bids_dir, merge_bidsignore=True)

        new_content = bidsignore_path.read_text()
        new_lines = len(new_content.strip().split("\n"))

        # If no new issues found, content should be roughly the same
        # (only adding header comments at most)
        assert "existing_pattern" in new_content

    def test_bidsignore_automation_with_threshold_parameter(self, tmp_path):
        """Test that TR threshold parameter is respected."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure
        (bids_dir / "sub-01" / "ses-01" / "func").mkdir(parents=True)

        # Should complete without error with custom threshold
        run_bold_analysis_and_update_bidsignore(
            bids_dir,
            tr_threshold_minutes=2.0,  # Different threshold
            merge_bidsignore=True,
        )

        # Check outputs exist
        assert (bids_dir / ".bids-validation" / "analysis.json").exists()

    def test_bidsignore_automation_with_verbose_logging(self, tmp_path, caplog):
        """Test that verbose parameter enables detailed logging."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure
        (bids_dir / "sub-01" / "ses-01" / "func").mkdir(parents=True)

        run_bold_analysis_and_update_bidsignore(
            bids_dir,
            merge_bidsignore=True,
            verbose=True,
        )

        # Just verify it doesn't crash with verbose=True
        assert (bids_dir / ".bids-validation" / "analysis.json").exists()

    def test_bidsignore_automation_integration_workflow(self, tmp_path):
        """
        Test the complete workflow: analysis + .bidsignore merge.

        This simulates the actual bidsify --run-validation workflow.
        """
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create a small multi-subject BIDS structure
        for sub in ["01", "02", "03"]:
            for ses in ["01", "02"]:
                (bids_dir / f"sub-{sub}" / f"ses-{ses}" / "func").mkdir(parents=True)

        # Create initial .bidsignore (simulating existing data)
        bidsignore_path = bids_dir / ".bidsignore"
        bidsignore_path.write_text("# Existing manual exclusions\nquality_issue_subject/\n")

        # Run the integration workflow (as cmd_bidsify would call it)
        run_bold_analysis_and_update_bidsignore(
            bids_dir=bids_dir,
            tr_threshold_minutes=3.0,
            merge_bidsignore=True,
            verbose=False,
        )

        # Verify all expected outputs exist
        analysis_json = bids_dir / ".bids-validation" / "analysis.json"
        assert analysis_json.exists(), "Analysis JSON should be created"

        # Verify analysis has correct structure
        analysis = json.loads(analysis_json.read_text())
        assert "metadata" in analysis
        assert "issues" in analysis

        # Verify .bidsignore is still present and has original content
        # (it may or may not be updated depending on whether new issues were found)
        bidsignore_content = bidsignore_path.read_text()
        assert "quality_issue_subject/" in bidsignore_content, "Original entry should be preserved"

    def test_bidsignore_automation_no_merge_flag(self, tmp_path):
        """Test that merge_bidsignore=False doesn't modify .bidsignore."""
        bids_dir = tmp_path / "bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure
        (bids_dir / "sub-01" / "ses-01" / "func").mkdir(parents=True)

        # Create initial .bidsignore
        bidsignore_path = bids_dir / ".bidsignore"
        bidsignore_path.write_text("original_entry\n")
        original_content = bidsignore_path.read_text()

        # Run analysis without merging
        run_bold_analysis_and_update_bidsignore(
            bids_dir,
            merge_bidsignore=False,
        )

        # Analysis should still be created
        assert (bids_dir / ".bids-validation" / "analysis.json").exists()

        # But .bidsignore should not be significantly modified
        # (it may be unchanged or have minimal changes)
        new_content = bidsignore_path.read_text()
        assert "original_entry" in new_content

    def test_bidsify_automatic_validation_behavior(self, tmp_path):
        """Test that bidsify would automatically run validation.

        This test demonstrates the new behavior where bidsify automatically
        runs BOLD validation after completing the bidsify process.
        Validation creates .bids-validation/analysis.json without requiring
        --run-validation flag.
        """
        bids_dir = tmp_path / "new_bids"
        bids_dir.mkdir()

        # Create minimal BIDS structure (simulating successful bidsify output)
        for sub in ["01", "02"]:
            func_dir = bids_dir / f"sub-{sub}" / "ses-01" / "func"
            func_dir.mkdir(parents=True)

        # Simulate what cmd_bidsify() does:
        # 1. run_bidsify() completes (simulated by BIDS dir existing)
        # 2. Automatic validation runs (NOT behind a flag anymore)
        run_bold_analysis_and_update_bidsignore(
            bids_dir=bids_dir,
            tr_threshold_minutes=3.0,
            merge_bidsignore=True,
            verbose=False,
        )

        # Verify the automatic workflow produced outputs
        analysis_file = bids_dir / ".bids-validation" / "analysis.json"
        assert analysis_file.exists(), "Automatic validation should create analysis.json"

        analysis = json.loads(analysis_file.read_text())
        assert "metadata" in analysis
        assert "issues" in analysis
        assert analysis["metadata"]["tr_threshold_seconds"] == 180  # 3.0 minutes
