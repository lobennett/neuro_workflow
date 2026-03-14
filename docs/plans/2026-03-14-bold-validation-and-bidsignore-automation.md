# BOLD Validation & .bidsignore Automation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement systematic TR analysis to identify problematic BOLD scans and automatically add them to .bidsignore with descriptive notes during bidsify.

**Architecture:**
1. Create a BOLD validation tool that extracts NIfTI headers, calculates timepoints, and categorizes scans as normal/short/3D/missing-metadata
2. Generate a JSON report mapping subjects/sessions to issues and .bidsignore entries
3. Integrate into bidsify workflow to automatically populate .bidsignore based on validation results
4. Update code to gracefully handle missing/corrupt files

**Tech Stack:** nibabel (NIfTI header inspection), Python, JSON configuration, BIDS spec

---

## Task 1: Create BOLD Validation Analysis Tool

**Files:**
- Create: `src/neuro_workflow/bids_validation/bold_analyzer.py`
- Create: `tests/bids_validation/test_bold_analyzer.py`
- Modify: `src/neuro_workflow/bids_validation/__init__.py`

**Step 1: Write the test file structure**

Create `tests/bids_validation/test_bold_analyzer.py`:

```python
"""Tests for BOLD scan validation and TR analysis."""

import json
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from neuro_workflow.bids_validation.bold_analyzer import (
    BoldAnalyzer,
    ScanIssue,
    ScanCategory,
)


def test_bold_analyzer_initialization(tmp_path):
    """Test BoldAnalyzer initializes correctly."""
    bids_dir = tmp_path / "bids"
    bids_dir.mkdir()

    analyzer = BoldAnalyzer(bids_dir, tr_threshold_minutes=3.0, verbose=True)

    assert analyzer.bids_dir == bids_dir
    assert analyzer.tr_threshold_minutes == 3.0
    assert analyzer.verbose is True


def test_identify_3d_bold_file(tmp_path):
    """Test detection of 3D BOLD files (should be 4D)."""
    # This test will use a mock to avoid requiring actual NIfTI files
    # The real test will check that the function properly identifies 3D files
    pass


def test_identify_short_scan_under_threshold(tmp_path):
    """Test detection of scans shorter than TR threshold."""
    # Mock a scan with 50 timepoints at 2s TR = 100 seconds (well under 3min)
    pass


def test_identify_missing_tr_metadata(tmp_path):
    """Test detection of BOLD files missing TR in JSON sidecar."""
    pass


def test_generate_bidsignore_entries(tmp_path):
    """Test that proper .bidsignore entries are generated for each issue."""
    pass
```

**Step 2: Implement the BOLD analyzer module**

Create `src/neuro_workflow/bids_validation/bold_analyzer.py`:

```python
"""Validate BOLD scans and identify problematic files for .bidsignore."""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import nibabel as nib
except ImportError:
    nib = None

logger = logging.getLogger(__name__)


class ScanCategory(str, Enum):
    """Categories for BOLD scan issues."""
    NORMAL = "normal"
    SHORT_SCAN = "short_scan"  # Under threshold duration
    THREE_D = "three_d"  # Missing time dimension
    MISSING_TR = "missing_tr"  # TR not in JSON sidecar
    MISSING_METADATA = "missing_metadata"  # Other critical metadata missing
    CORRUPT_NIFTI = "corrupt_nifti"  # Can't read NIfTI header
    CORRUPT_JSON = "corrupt_json"  # Invalid JSON sidecar


@dataclass
class ScanIssue:
    """Represents a problem with a BOLD scan."""
    subject: str
    session: str
    task: str
    run: Optional[int]
    echo: Optional[int]
    category: ScanCategory
    reason: str
    filepath: Path
    timepoints: Optional[int] = None
    duration_seconds: Optional[float] = None
    tr_seconds: Optional[float] = None

    @property
    def bidsignore_entry(self) -> str:
        """Generate appropriate .bidsignore entry and comment."""
        if self.run and self.echo:
            pattern = f"sub-{self.subject}/ses-{self.session:02d}/func/*task-{self.task}_run-{self.run}_echo-{self.echo}_bold*"
        elif self.run:
            pattern = f"sub-{self.subject}/ses-{self.session:02d}/func/*task-{self.task}_run-{self.run}_bold*"
        else:
            pattern = f"sub-{self.subject}/ses-{self.session:02d}/func/*task-{self.task}_bold*"

        return pattern

    @property
    def bidsignore_comment(self) -> str:
        """Generate human-readable comment for .bidsignore."""
        if self.category == ScanCategory.THREE_D:
            return f"3D BOLD (dim missing time axis): {self.reason}"
        elif self.category == ScanCategory.SHORT_SCAN:
            return f"Short scan ({self.duration_seconds:.0f}s / {self.timepoints} TRs): {self.reason}"
        elif self.category == ScanCategory.MISSING_TR:
            return f"Missing TR metadata: {self.reason}"
        else:
            return f"{self.category.value}: {self.reason}"


class BoldAnalyzer:
    """Analyze BOLD scans in BIDS directory and identify issues."""

    def __init__(
        self,
        bids_dir: Path,
        tr_threshold_minutes: float = 3.0,
        verbose: bool = False,
    ):
        """
        Initialize BOLD analyzer.

        Args:
            bids_dir: Path to BIDS root directory
            tr_threshold_minutes: Scans shorter than this (in minutes) are flagged
            verbose: Enable verbose logging
        """
        self.bids_dir = Path(bids_dir)
        self.tr_threshold_minutes = tr_threshold_minutes
        self.tr_threshold_seconds = tr_threshold_minutes * 60
        self.verbose = verbose
        self.issues: List[ScanIssue] = []

    def analyze(self) -> Dict[str, List[ScanIssue]]:
        """
        Analyze all BOLD files in BIDS directory.

        Returns:
            Dict mapping category names to lists of ScanIssues
        """
        if nib is None:
            logger.error("nibabel not installed. Cannot analyze BOLD files.")
            return {}

        self.issues = []

        # Find all BOLD files
        bold_files = sorted(self.bids_dir.glob("sub-*/ses-*/func/*_bold.nii.gz"))

        if self.verbose:
            logger.info(f"Found {len(bold_files)} BOLD files to analyze")

        for bold_file in bold_files:
            self._analyze_bold_file(bold_file)

        # Group by category
        by_category = {}
        for issue in self.issues:
            cat = issue.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(issue)

        return by_category

    def _analyze_bold_file(self, bold_file: Path) -> None:
        """Analyze a single BOLD file."""
        # Parse BIDS filename to extract subject, session, task, run, echo
        parts = self._parse_bold_filename(bold_file)
        if not parts:
            logger.warning(f"Could not parse BIDS filename: {bold_file.name}")
            return

        subject, session, task, run, echo = parts

        # Check for 3D or metadata issues
        try:
            img = nib.load(bold_file)
            shape = img.shape
            header = img.header

            # Check if 3D (missing 4th dimension)
            if len(shape) != 4:
                issue = ScanIssue(
                    subject=subject,
                    session=int(session),
                    task=task,
                    run=run,
                    echo=echo,
                    category=ScanCategory.THREE_D,
                    reason=f"Header dim={shape}, expected 4D",
                    filepath=bold_file,
                )
                self.issues.append(issue)
                if self.verbose:
                    logger.warning(f"3D BOLD: {bold_file.name}")
                return

            timepoints = shape[3]

            # Get TR from JSON sidecar
            json_file = bold_file.with_suffix("").with_suffix(".json")
            tr_seconds = self._get_tr_from_json(json_file)

            if tr_seconds is None:
                issue = ScanIssue(
                    subject=subject,
                    session=int(session),
                    task=task,
                    run=run,
                    echo=echo,
                    category=ScanCategory.MISSING_TR,
                    reason="TR not found in JSON sidecar",
                    filepath=bold_file,
                    timepoints=timepoints,
                )
                self.issues.append(issue)
                if self.verbose:
                    logger.warning(f"Missing TR: {bold_file.name}")
                return

            # Calculate duration
            duration_seconds = timepoints * tr_seconds

            # Check if scan is too short
            if duration_seconds < self.tr_threshold_seconds:
                issue = ScanIssue(
                    subject=subject,
                    session=int(session),
                    task=task,
                    run=run,
                    echo=echo,
                    category=ScanCategory.SHORT_SCAN,
                    reason=f"Duration {duration_seconds:.0f}s < threshold {self.tr_threshold_seconds:.0f}s",
                    filepath=bold_file,
                    timepoints=timepoints,
                    duration_seconds=duration_seconds,
                    tr_seconds=tr_seconds,
                )
                self.issues.append(issue)
                if self.verbose:
                    logger.info(f"Short scan: {bold_file.name} ({duration_seconds:.0f}s)")

        except Exception as e:
            issue = ScanIssue(
                subject=subject,
                session=int(session),
                task=task,
                run=run,
                echo=echo,
                category=ScanCategory.CORRUPT_NIFTI,
                reason=f"Error reading NIfTI: {str(e)}",
                filepath=bold_file,
            )
            self.issues.append(issue)
            logger.error(f"Error analyzing {bold_file}: {e}")

    def _parse_bold_filename(self, bold_file: Path) -> Optional[Tuple[str, str, str, Optional[int], Optional[int]]]:
        """
        Parse BIDS filename to extract subject, session, task, run, echo.

        Returns:
            Tuple of (subject, session, task, run, echo) or None if parse fails
        """
        import re

        name = bold_file.name

        # Extract components from BIDS filename
        # Format: sub-{subject}_ses-{session}_task-{task}_[run-{run}_][echo-{echo}_]bold.nii.gz
        match = re.search(
            r"sub-([^_]+)_ses-(\d+)_task-([^_]+)(?:_run-(\d+))?(?:_echo-(\d+))?",
            name
        )

        if not match:
            return None

        subject = match.group(1)
        session = match.group(2)
        task = match.group(3)
        run = int(match.group(4)) if match.group(4) else None
        echo = int(match.group(5)) if match.group(5) else None

        return subject, session, task, run, echo

    def _get_tr_from_json(self, json_file: Path) -> Optional[float]:
        """Extract TR (RepetitionTime) from JSON sidecar."""
        if not json_file.exists():
            return None

        try:
            with open(json_file) as f:
                data = json.load(f)
            return data.get("RepetitionTime")
        except Exception as e:
            logger.debug(f"Error reading JSON {json_file}: {e}")
            return None

    def generate_bidsignore_entries(self, exclude_categories: Optional[List[str]] = None) -> str:
        """
        Generate .bidsignore content for problematic scans.

        Args:
            exclude_categories: Categories to exclude from .bidsignore (e.g., ['missing_tr'] if you'll fix those)

        Returns:
            String containing .bidsignore entries with comments
        """
        exclude_categories = exclude_categories or []

        # Filter issues
        issues_to_ignore = [
            issue for issue in self.issues
            if issue.category.value not in exclude_categories
        ]

        if not issues_to_ignore:
            return ""

        lines = []
        for issue in sorted(issues_to_ignore, key=lambda x: (x.subject, x.session, x.task)):
            lines.append(f"# {issue.bidsignore_comment}")
            lines.append(issue.bidsignore_entry)
            lines.append("")

        return "\n".join(lines)
```

**Step 3: Create __init__ file for bids_validation module**

Modify `src/neuro_workflow/bids_validation/__init__.py`:

```python
"""BIDS validation and QA utilities."""

from .bold_analyzer import BoldAnalyzer, ScanCategory, ScanIssue

__all__ = [
    "BoldAnalyzer",
    "ScanCategory",
    "ScanIssue",
]
```

**Step 4: Run tests to verify they fail**

Run: `cd /home/users/logben/neuro_workflow && pytest tests/bids_validation/test_bold_analyzer.py -v`

Expected: TESTS SKIP or FAIL (because tests are placeholders)

**Step 5: Implement real tests using mock data**

Update `tests/bids_validation/test_bold_analyzer.py` with concrete test implementations using temporary BIDS directories and mock NIfTI files.

**Step 6: Run tests to verify implementation**

Run: `pytest tests/bids_validation/test_bold_analyzer.py -v`

Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/neuro_workflow/bids_validation/bold_analyzer.py tests/bids_validation/test_bold_analyzer.py
git commit -m "feat: add BOLD validation analyzer for TR and dimensionality checking"
```

---

## Task 2: Run TR Analysis on Current BIDS Directories

**Files:**
- Create: `scripts/analyze_bold_scans.py` (standalone analysis script)
- Create: `docs/bold-analysis-report-2026-03-14.md` (results)

**Step 1: Create analysis script**

Create `scripts/analyze_bold_scans.py`:

```python
#!/usr/bin/env python3
"""Analyze BOLD scans in BIDS directories and generate .bidsignore entries."""

import argparse
import json
from pathlib import Path
from neuro_workflow.bids_validation.bold_analyzer import BoldAnalyzer

def main():
    parser = argparse.ArgumentParser(description="Analyze BOLD scans for QA issues")
    parser.add_argument("bids_dir", type=Path, help="Path to BIDS directory")
    parser.add_argument("--tr-threshold-minutes", type=float, default=3.0, help="Threshold for short scans (minutes)")
    parser.add_argument("--output-json", type=Path, help="Save results as JSON")
    parser.add_argument("--output-bidsignore", type=Path, help="Save .bidsignore entries")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    analyzer = BoldAnalyzer(args.bids_dir, tr_threshold_minutes=args.tr_threshold_minutes, verbose=args.verbose)
    results = analyzer.analyze()

    # Print summary
    print(f"\nBOLD Scan Analysis: {args.bids_dir}")
    print("=" * 60)
    for category, issues in sorted(results.items()):
        print(f"{category}: {len(issues)} scans")
        for issue in issues[:3]:  # Show first 3 of each category
            print(f"  - {issue.filepath.relative_to(args.bids_dir)}")
        if len(issues) > 3:
            print(f"  ... and {len(issues) - 3} more")

    # Save JSON if requested
    if args.output_json:
        issues_dict = {}
        for category, issues in results.items():
            issues_dict[category] = [
                {
                    "subject": issue.subject,
                    "session": issue.session,
                    "task": issue.task,
                    "run": issue.run,
                    "echo": issue.echo,
                    "reason": issue.reason,
                    "timepoints": issue.timepoints,
                    "duration_seconds": issue.duration_seconds,
                    "tr_seconds": issue.tr_seconds,
                }
                for issue in issues
            ]
        args.output_json.write_text(json.dumps(issues_dict, indent=2))
        print(f"\nJSON report saved to: {args.output_json}")

    # Save .bidsignore if requested
    if args.output_bidsignore:
        bidsignore_content = analyzer.generate_bidsignore_entries()
        args.output_bidsignore.write_text(bidsignore_content)
        print(f".bidsignore entries saved to: {args.output_bidsignore}")

if __name__ == "__main__":
    main()
```

**Step 2: Run analysis on all three BIDS directories**

Run three commands (in repo root):

```bash
# Discovery
uv run python scripts/analyze_bold_scans.py /scratch/users/logben/discovery_bids \
    --output-json /tmp/discovery_bold_analysis.json \
    --output-bidsignore /tmp/discovery_bidsignore_additions.txt \
    -v

# Validation
uv run python scripts/analyze_bold_scans.py /scratch/users/logben/validation_bids \
    --output-json /tmp/validation_bold_analysis.json \
    --output-bidsignore /tmp/validation_bidsignore_additions.txt \
    -v

# Excluded
uv run python scripts/analyze_bold_scans.py /scratch/users/logben/excluded_bids \
    --output-json /tmp/excluded_bold_analysis.json \
    --output-bidsignore /tmp/excluded_bidsignore_additions.txt \
    -v
```

**Step 3: Review and document results**

Create `docs/bold-analysis-report-2026-03-14.md` with summary of findings.

**Step 4: Commit**

```bash
git add scripts/analyze_bold_scans.py docs/bold-analysis-report-2026-03-14.md
git commit -m "feat: add BOLD scan analysis script and initial QA report"
```

---

## Task 3: Update Bidsify Integration to Use Analysis Results

**Files:**
- Modify: `src/neuro_workflow/bids_validation/bold_analyzer.py` (add persistence methods)
- Create: `src/neuro_workflow/bidsify/integration.py` (new integration module)
- Modify: `src/neuro_workflow/bidsify/main.py` or similar (add analysis step)

**Steps defined below as 6-10**

---

## Task 4: Update .bidsignore During Bidsify

**Task 4a**: Integrate analyzer into bidsify workflow to automatically populate .bidsignore

**Task 4b**: Add validation test to ensure .bidsignore is correctly populated

**Task 4c**: Test full pipeline with sample BIDS data

---

## Next Steps (After Task 1)

- **Execution:** Once Task 1 tests pass, proceed with Task 2 (TR analysis on real data)
- **Review:** After Task 2, review results to understand scope before Task 3-4 (integration)
- **Integration:** Tasks 3-4 will wire analysis into automatic bidsify workflow

---

## Notes / Risks

- **NIfTI header parsing** depends on nibabel; need to ensure installed in environment
- **Long analysis time** for 57 subjects × 12 sessions × 5 tasks × 3 echoes ≈ 10k files; run with `-v` flag to monitor
- **TR threshold (3 min default)** is configurable; may need adjustment based on actual scan durations
- **.bidsignore pattern matching** must be careful with wildcards to match multi-echo properly
