"""Integration of BOLD analyzer with bidsify workflow."""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from neuro_workflow.bids_validation.bold_analyzer import BoldAnalyzer

logger = logging.getLogger(__name__)


def _load_task_tr_counts(config_path: Optional[Path] = None) -> Dict[str, int]:
    """Load per-task TR count specifications from config file.

    Parameters
    ----------
    config_path : Optional[Path], optional
        Path to task_tr_counts.json. If not provided, looks for it at
        neuro_workflow/config/task_tr_counts.json relative to the repo root.

    Returns
    -------
    Dict[str, int]
        Dictionary mapping task names to minimum acceptable TR counts.
        Returns empty dict if file not found.
    """
    if config_path is None:
        # Look for task_tr_counts.json relative to this file
        current_dir = Path(__file__).parent.parent.parent  # Go up to repo root
        config_path = current_dir / "config" / "task_tr_counts.json"

    if not config_path.exists():
        logger.debug(f"Task TR counts config not found at {config_path}, using default duration threshold")
        return {}

    try:
        with open(config_path) as f:
            config = json.load(f)

        # Extract min_acceptable_trs from task_tr_counts sub-dict
        task_tr_counts = {}
        for task_name, task_config in config.get("task_tr_counts", {}).items():
            if isinstance(task_config, dict) and "min_acceptable_trs" in task_config:
                task_tr_counts[task_name] = task_config["min_acceptable_trs"]

        if task_tr_counts:
            logger.info(f"Loaded {len(task_tr_counts)} task-specific TR thresholds from {config_path}")
        return task_tr_counts
    except Exception as e:
        logger.warning(f"Failed to load task TR counts from {config_path}: {e}")
        return {}


def run_bold_analysis_and_update_bidsignore(
    bids_dir: Path,
    tr_threshold_minutes: float = 3.0,
    merge_bidsignore: bool = True,
    verbose: bool = False,
) -> None:
    """Run BOLD analysis on completed BIDS directory and optionally update .bidsignore.

    This function:
    1. Loads per-task TR count specifications from config/task_tr_counts.json
    2. Initializes BoldAnalyzer with the BIDS directory and per-task TR thresholds
    3. Runs analysis to detect BOLD scan issues (short scans, 3D scans, missing metadata)
    4. Saves analysis results to {bids_dir}/.bids-validation/analysis.json
    5. Merges new .bidsignore entries into existing .bidsignore (if merge_bidsignore=True)

    Parameters
    ----------
    bids_dir : Path
        Path to BIDS root directory (must exist and contain sub-*/ses-*/func/)
    tr_threshold_minutes : float, optional
        Global duration threshold for flagging short scans (default: 3.0 minutes).
        Only used if task_tr_counts.json is not found or for tasks without defined TR counts.
    merge_bidsignore : bool, optional
        If True, merge new entries into existing .bidsignore (default: True)
    verbose : bool, optional
        Enable verbose logging (default: False)

    Raises
    ------
    FileNotFoundError
        If BIDS directory does not exist
    """
    bids_dir = Path(bids_dir)

    if not bids_dir.exists():
        raise FileNotFoundError(f"BIDS directory does not exist: {bids_dir}")

    logger.info(f"Running BOLD analysis on {bids_dir}")

    # Load per-task TR count specifications
    task_tr_counts = _load_task_tr_counts()

    # Initialize analyzer with per-task TR thresholds (or duration fallback)
    analyzer = BoldAnalyzer(
        bids_dir,
        tr_threshold_minutes=tr_threshold_minutes,
        task_tr_counts=task_tr_counts,
        verbose=verbose,
    )

    # Run analysis and save report
    analysis_dir = bids_dir / ".bids-validation"
    analysis_file = analysis_dir / "analysis.json"

    analyzer.save_analysis_report(analysis_file)
    logger.info(f"Saved analysis report to {analysis_file}")

    # Generate .bidsignore entries
    bidsignore_entries = analyzer.generate_bidsignore_entries()

    if merge_bidsignore:
        _merge_bidsignore(bids_dir, bidsignore_entries, verbose=verbose)
    else:
        # Just log what would be added
        if bidsignore_entries.strip() and not bidsignore_entries.startswith("# No BOLD"):
            logger.info(
                f"BOLD analysis found issues. Use merge_bidsignore=True to add to .bidsignore"
            )


def _merge_bidsignore(
    bids_dir: Path, new_entries: str, verbose: bool = False
) -> None:
    """Merge new .bidsignore entries into existing .bidsignore file.

    Parameters
    ----------
    bids_dir : Path
        Path to BIDS root directory
    new_entries : str
        New .bidsignore content to merge (with comments and patterns)
    verbose : bool
        Enable verbose logging
    """
    bidsignore_path = bids_dir / ".bidsignore"

    # Parse new entries to extract patterns only (skip comments and blank lines)
    new_patterns = set()
    for line in new_entries.split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            new_patterns.add(line)

    if not new_patterns:
        logger.info("No new BOLD issues to add to .bidsignore")
        return

    # Read existing .bidsignore
    existing_patterns = set()
    if bidsignore_path.exists():
        for line in bidsignore_path.read_text().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                existing_patterns.add(line)

    # Merge (keep both)
    all_patterns = existing_patterns | new_patterns
    num_new = len(all_patterns - existing_patterns)

    if num_new == 0:
        logger.info("No new patterns to add to .bidsignore")
        return

    # Rebuild .bidsignore with header and sorted patterns
    lines = [
        "# BIDS validation exclusions",
        "# Generated by bidsify with BOLD analyzer",
        "# See .bids-validation/analysis.json for details",
        "",
    ]
    for pattern in sorted(all_patterns):
        lines.append(pattern)

    bidsignore_path.write_text("\n".join(lines) + "\n")
    logger.info(
        f"Updated .bidsignore: added {num_new} new patterns "
        f"({len(all_patterns)} total patterns)"
    )
    if verbose:
        logger.debug(f"New patterns added: {', '.join(sorted(new_patterns - existing_patterns))}")
