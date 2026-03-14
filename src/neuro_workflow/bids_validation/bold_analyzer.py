"""BOLD validation analyzer for identifying problematic BOLD scans in BIDS datasets."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Try to import nibabel, but make it optional
try:
    import nibabel as nib
except ImportError:
    nib = None  # type: ignore


class ScanCategory(str, Enum):
    """Categories of BOLD scan issues.

    Note: Only problematic scans are reported; normal scans are not included in
    analyze() results. The NORMAL value is reserved for future use in distinguishing
    between different scan classifications.
    """

    NORMAL = "normal"
    SHORT_SCAN = "short_scan"
    THREE_D = "three_d"
    MISSING_TR = "missing_tr"
    MISSING_METADATA = "missing_metadata"
    CORRUPT_NIFTI = "corrupt_nifti"
    CORRUPT_JSON = "corrupt_json"


@dataclass
class ScanIssue:
    """Represents a single BOLD scan problem."""

    subject: str
    session: int
    task: str
    category: ScanCategory
    reason: str
    filepath: str
    run: Optional[int] = None
    echo: Optional[int] = None
    timepoints: Optional[int] = None
    duration_seconds: Optional[float] = None
    tr_seconds: Optional[float] = None

    @property
    def bidsignore_entry(self) -> str:
        """Generate .bidsignore entry pattern for this scan."""
        parts = [f"sub-{self.subject}", f"ses-{self.session:02d}", "func"]

        # Build entity string (order matters: task, run, echo)
        entities = []
        if self.task:
            entities.append(f"task-{self.task}")
        if self.run is not None:
            entities.append(f"run-{self.run}")
        if self.echo is not None:
            entities.append(f"echo-{self.echo}")

        entity_str = "_".join(entities) if entities else "*"
        pattern = f"{'/'.join(parts)}/*{entity_str}_bold*"

        return pattern

    @property
    def bidsignore_comment(self) -> str:
        """Generate human-readable comment for .bidsignore entry."""
        base_comment = f"sub-{self.subject} ses-{self.session:02d}: {self.reason}"

        if self.duration_seconds is not None and self.tr_seconds is not None:
            base_comment += f" (duration: {self.duration_seconds:.1f}s, TR: {self.tr_seconds}s)"
        elif self.duration_seconds is not None:
            base_comment += f" (duration: {self.duration_seconds:.1f}s)"
        elif self.tr_seconds is not None:
            base_comment += f" (TR: {self.tr_seconds}s)"

        return base_comment


class BoldAnalyzer:
    """Analyzer for identifying problematic BOLD scans in BIDS datasets."""

    def __init__(
        self,
        bids_dir: Path,
        tr_threshold_minutes: float = 3.0,
        task_tr_counts: Optional[Dict[str, int]] = None,
        verbose: bool = False,
    ) -> None:
        """Initialize BOLD analyzer.

        Parameters
        ----------
        bids_dir : Path
            Path to BIDS dataset directory
        tr_threshold_minutes : float, optional
            Global minimum scan duration in minutes (default: 3.0).
            Used only as fallback when task_tr_counts is not provided.
        task_tr_counts : Optional[Dict[str, int]], optional
            Per-task TR count specifications. Dict maps task name to min acceptable TR count.
            If provided, uses per-task detection. Otherwise falls back to duration-based.
        verbose : bool, optional
            Enable verbose logging (default: False)
        """
        self.bids_dir = Path(bids_dir)
        self.tr_threshold_seconds = tr_threshold_minutes * 60
        self.task_tr_counts = task_tr_counts or {}
        self.verbose = verbose
        self.use_tr_based_detection = len(self.task_tr_counts) > 0

        if not self.bids_dir.exists():
            logger.warning(f"BIDS directory does not exist: {self.bids_dir}")

    def _get_min_tr_count_for_task(self, task: str) -> Optional[int]:
        """Get minimum acceptable TR count for a task.

        Parameters
        ----------
        task : str
            Task name

        Returns
        -------
        Optional[int]
            Minimum acceptable TR count, or None if not defined for this task.
        """
        return self.task_tr_counts.get(task)

    def analyze(self) -> Dict[str, List[ScanIssue]]:
        """Analyze all BOLD files in BIDS dataset.

        Returns
        -------
        Dict[str, List[ScanIssue]]
            Issues grouped by category name. Only problematic scans are included;
            scans that pass all validation checks are not reported.
        """
        issues_by_category: Dict[str, List[ScanIssue]] = {}

        # Find all BOLD files
        func_dirs = list(self.bids_dir.glob("sub-*/ses-*/func"))
        if self.verbose:
            logger.info(f"Found {len(func_dirs)} func directories")

        for func_dir in func_dirs:
            bold_files = list(func_dir.glob("*_bold.nii.gz"))
            if self.verbose and bold_files:
                logger.info(f"Analyzing {len(bold_files)} BOLD files in {func_dir}")

            for bold_file in bold_files:
                issue = self._analyze_bold_file(bold_file)
                if issue:
                    category = issue.category.value
                    if category not in issues_by_category:
                        issues_by_category[category] = []
                    issues_by_category[category].append(issue)

        if self.verbose:
            total_issues = sum(len(v) for v in issues_by_category.values())
            logger.info(f"Found {total_issues} total issues across all categories")

        return issues_by_category

    def _analyze_bold_file(self, bold_file: Path) -> Optional[ScanIssue]:
        """Analyze a single BOLD file for issues.

        Parameters
        ----------
        bold_file : Path
            Path to BOLD NIfTI file

        Returns
        -------
        Optional[ScanIssue]
            ScanIssue if a problem is found, None otherwise
        """
        # Parse filename
        parsed = self._parse_bold_filename(bold_file)
        if not parsed:
            logger.warning(f"Could not parse BOLD filename: {bold_file.name}")
            return None

        subject, session, task, run, echo = parsed

        # Handle .nii.gz suffix properly
        if bold_file.suffix == ".gz":
            json_file = bold_file.with_suffix("").with_suffix(".json")
        else:
            json_file = bold_file.with_suffix(".json")

        # Check for missing JSON sidecar
        if not json_file.exists():
            logger.warning(f"Missing JSON sidecar for {bold_file.name}")
            return ScanIssue(
                subject=subject,
                session=session,
                task=task,
                run=run,
                echo=echo,
                category=ScanCategory.MISSING_METADATA,
                reason="Missing JSON sidecar",
                filepath=str(bold_file),
            )

        # Get TR from JSON
        tr = self._get_tr_from_json(json_file)
        if tr is None:
            logger.warning(f"Missing RepetitionTime in JSON for {bold_file.name}")
            return ScanIssue(
                subject=subject,
                session=session,
                task=task,
                run=run,
                echo=echo,
                category=ScanCategory.MISSING_TR,
                reason="RepetitionTime not found in JSON sidecar",
                filepath=str(bold_file),
            )

        # Try to read NIfTI file
        if nib is None:
            logger.debug("nibabel not installed, skipping 3D/short scan detection")
            return None

        try:
            img = nib.load(bold_file)
        except Exception as e:
            logger.error(f"Error reading NIfTI file {bold_file.name}: {e}")
            return ScanIssue(
                subject=subject,
                session=session,
                task=task,
                run=run,
                echo=echo,
                category=ScanCategory.CORRUPT_NIFTI,
                reason=f"Error reading NIfTI: {type(e).__name__}",
                filepath=str(bold_file),
                tr_seconds=tr,
            )

        # Check for 3D scan
        if len(img.shape) != 4:
            logger.warning(
                f"3D BOLD scan detected: {bold_file.name} (shape: {img.shape})"
            )
            return ScanIssue(
                subject=subject,
                session=session,
                task=task,
                run=run,
                echo=echo,
                category=ScanCategory.THREE_D,
                reason=f"3D scan (shape: {img.shape})",
                filepath=str(bold_file),
                tr_seconds=tr,
            )

        # Check for short scan
        num_timepoints = img.shape[3]
        duration_seconds = num_timepoints * tr

        # Use TR-based detection if available, otherwise fall back to duration-based
        if self.use_tr_based_detection:
            min_acceptable_trs = self._get_min_tr_count_for_task(task)
            if min_acceptable_trs is not None and num_timepoints < min_acceptable_trs:
                logger.warning(
                    f"Short BOLD scan detected: {bold_file.name} "
                    f"({num_timepoints} TRs, minimum {min_acceptable_trs} TRs required)"
                )
                short_scan_reason = (
                    f"Scan has {num_timepoints} TRs, but minimum {min_acceptable_trs} TRs required"
                )
                return ScanIssue(
                    subject=subject,
                    session=session,
                    task=task,
                    run=run,
                    echo=echo,
                    category=ScanCategory.SHORT_SCAN,
                    reason=short_scan_reason,
                    filepath=str(bold_file),
                    timepoints=num_timepoints,
                    duration_seconds=duration_seconds,
                    tr_seconds=tr,
                )
        else:
            # Fall back to duration-based detection
            if duration_seconds < self.tr_threshold_seconds:
                logger.warning(
                    f"Short BOLD scan detected: {bold_file.name} "
                    f"({num_timepoints} TRs × {tr}s = {duration_seconds:.1f}s, "
                    f"threshold: {self.tr_threshold_seconds:.1f}s)"
                )
                short_scan_reason = (
                    f"Scan duration {duration_seconds:.1f}s below threshold "
                    f"{self.tr_threshold_seconds:.1f}s"
                )
                return ScanIssue(
                    subject=subject,
                    session=session,
                    task=task,
                    run=run,
                    echo=echo,
                    category=ScanCategory.SHORT_SCAN,
                    reason=short_scan_reason,
                    filepath=str(bold_file),
                    timepoints=num_timepoints,
                    duration_seconds=duration_seconds,
                    tr_seconds=tr,
                )

        # No issues found
        return None

    def _parse_bold_filename(
        self, bold_file: Path
    ) -> Optional[Tuple[str, int, str, Optional[int], Optional[int]]]:
        """Parse BOLD filename to extract BIDS entities.

        Parameters
        ----------
        bold_file : Path
            Path to BOLD NIfTI file

        Returns
        -------
        Optional[Tuple[str, int, str, Optional[int], Optional[int]]]
            Tuple of (subject, session, task, run, echo) or None if parsing fails.
            Components:
            - subject: BIDS subject label
            - session: Session number (parsed as int from string)
            - task: Task label
            - run: Run number (optional)
            - echo: Echo number (optional)
        """
        filename = bold_file.name
        # Remove .nii.gz extension
        if filename.endswith(".nii.gz"):
            filename = filename[:-7]

        # BIDS filename pattern:
        # sub-<label>_ses-<label>_task-<label>_[run-<index>_][echo-<index>_]bold
        pattern = (
            r"sub-([a-zA-Z0-9]+)_ses-(\d+)_task-([a-zA-Z0-9]+)"
            r"(?:_run-(\d+))?(?:_echo-(\d+))?"
        )

        match = re.match(pattern, filename)
        if not match:
            return None

        subject = match.group(1)
        session = int(match.group(2))
        task = match.group(3)
        run = int(match.group(4)) if match.group(4) else None
        echo = int(match.group(5)) if match.group(5) else None

        return (subject, session, task, run, echo)

    def _get_tr_from_json(self, json_file: Path) -> Optional[float]:
        """Extract TR (RepetitionTime) from JSON sidecar.

        Parameters
        ----------
        json_file : Path
            Path to JSON sidecar file

        Returns
        -------
        Optional[float]
            RepetitionTime in seconds, or None if not found
        """
        if not json_file.exists():
            return None

        try:
            data = json.loads(json_file.read_text())
            tr = data.get("RepetitionTime")
            if tr is not None:
                return float(tr)
        except (json.JSONDecodeError, ValueError, OSError) as e:
            logger.warning(f"Error reading JSON sidecar {json_file.name}: {e}")

        return None

    def generate_bidsignore_entries(
        self, exclude_categories: Optional[List[str]] = None
    ) -> str:
        """Generate .bidsignore content from all issues.

        Parameters
        ----------
        exclude_categories : Optional[List[str]]
            List of category names to exclude from output (default: None means include all)

        Returns
        -------
        str
            .bidsignore content with comments
        """
        issues = self.analyze()

        if not issues:
            return "# No BOLD issues detected\n"

        lines = ["# Generated by BoldAnalyzer"]
        lines.append("# Issues detected in BOLD scans")
        lines.append("")

        for category in sorted(issues.keys()):
            if exclude_categories and category in exclude_categories:
                continue

            lines.append(f"# {category.replace('_', ' ').title()}")
            for issue in sorted(
                issues[category],
                key=lambda x: (x.subject, x.session, x.task, x.run or 0, x.echo or 0),
            ):
                lines.append(f"{issue.bidsignore_entry}  # {issue.bidsignore_comment}")

            lines.append("")

        return "\n".join(lines)

    def save_analysis_report(self, output_file: Path) -> None:
        """Save analysis results as JSON with full details.

        Parameters
        ----------
        output_file : Path
            Path to write JSON report to
        """
        issues_by_category = self.analyze()

        # Convert ScanIssue objects to JSON-serializable dicts
        report = {
            "metadata": {
                "bids_dir": str(self.bids_dir),
                "tr_threshold_seconds": self.tr_threshold_seconds,
                "generated": datetime.now(timezone.utc).isoformat(),
            },
            "issues": {},
        }

        for category, issues in sorted(issues_by_category.items()):
            report["issues"][category] = [
                {
                    "subject": issue.subject,
                    "session": issue.session,
                    "task": issue.task,
                    "run": issue.run,
                    "echo": issue.echo,
                    "reason": issue.reason,
                    "filepath": issue.filepath,
                    "timepoints": issue.timepoints,
                    "duration_seconds": issue.duration_seconds,
                    "tr_seconds": issue.tr_seconds,
                }
                for issue in sorted(
                    issues,
                    key=lambda x: (x.subject, x.session, x.task, x.run or 0, x.echo or 0),
                )
            ]

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(report, indent=2))
        if self.verbose:
            logger.info(f"Saved analysis report to {output_file}")

    def save_bidsignore_entries(
        self,
        output_file: Path,
        exclude_categories: Optional[List[str]] = None,
    ) -> None:
        """Save .bidsignore entries to file.

        Parameters
        ----------
        output_file : Path
            Path to write .bidsignore entries to (for merging)
        exclude_categories : Optional[List[str]]
            List of category names to exclude from output
        """
        content = self.generate_bidsignore_entries(exclude_categories)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(content)
        if self.verbose:
            logger.info(f"Saved .bidsignore entries to {output_file}")
