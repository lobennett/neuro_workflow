#!/usr/bin/env python3
"""Analyze BOLD scans in BIDS directories and generate .bidsignore entries."""

import argparse
import json
import logging
from pathlib import Path
from collections import defaultdict

from neuro_workflow.bids_validation import BoldAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
logger = logging.getLogger(__name__)


def group_issues_by_task(issues):
    """Group SHORT_SCAN issues by task name to reveal patterns."""
    by_task = defaultdict(list)
    for issue in issues:
        by_task[issue.task].append(issue)
    return dict(sorted(by_task.items()))


def print_summary(results, bids_dir):
    """Print a formatted summary of analysis results."""
    print(f"\nBOLD Scan Analysis Report")
    print("=" * 70)
    print(f"BIDS Directory: {bids_dir}")
    print(f"=" * 70)

    total_issues = sum(len(issues) for issues in results.values())
    print(f"Total issues found: {total_issues}\n")

    # Print summary by category
    for category in sorted(results.keys()):
        issues = results[category]
        print(f"{category.upper()}: {len(issues)} scans")

        if category == "short_scan":
            # For SHORT_SCAN, group by task to show patterns
            by_task = group_issues_by_task(issues)
            for task, task_issues in by_task.items():
                # Show TR and duration info
                if task_issues and task_issues[0].tr_seconds:
                    tr = task_issues[0].tr_seconds
                    durations = [
                        issue.duration_seconds for issue in task_issues
                        if issue.duration_seconds
                    ]
                    avg_duration = sum(durations) / len(durations) if durations else 0
                    print(
                        f"  {task}: {len(task_issues)} scans (TR={tr}s, "
                        f"avg duration={avg_duration:.0f}s)"
                    )
                else:
                    print(f"  {task}: {len(task_issues)} scans")
        else:
            # For other categories, just show count and first few examples
            shown = 0
            for issue in issues[:3]:
                print(
                    f"  - sub-{issue.subject} ses-{issue.session:02d} "
                    f"task-{issue.task}: {issue.reason}"
                )
                shown += 1

            if len(issues) > 3:
                print(f"  ... and {len(issues) - 3} more")

        print()


def save_json_report(results, output_path):
    """Save results as JSON with full details."""
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
                "filepath": str(issue.filepath),
            }
            for issue in issues
        ]

    output_path.write_text(json.dumps(issues_dict, indent=2))
    print(f"JSON report saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze BOLD scans in BIDS directory for QA issues"
    )
    parser.add_argument("bids_dir", type=Path, help="Path to BIDS directory")
    parser.add_argument(
        "--tr-threshold-minutes",
        type=float,
        default=3.0,
        help="Threshold for short scans in minutes (default: 3.0)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        help="Save detailed results as JSON",
    )
    parser.add_argument(
        "--output-bidsignore",
        type=Path,
        help="Save .bidsignore entries",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Validate BIDS directory
    if not args.bids_dir.exists():
        logger.error(f"BIDS directory not found: {args.bids_dir}")
        return 1

    # Run analysis
    logger.info(f"Analyzing BIDS directory: {args.bids_dir}")
    analyzer = BoldAnalyzer(
        args.bids_dir,
        tr_threshold_minutes=args.tr_threshold_minutes,
        verbose=args.verbose,
    )
    results = analyzer.analyze()

    # Print summary
    print_summary(results, args.bids_dir)

    # Save JSON if requested
    if args.output_json:
        save_json_report(results, args.output_json)

    # Save .bidsignore entries if requested
    if args.output_bidsignore:
        bidsignore_content = analyzer.generate_bidsignore_entries()
        args.output_bidsignore.write_text(bidsignore_content)
        entry_count = bidsignore_content.count("\n/") if bidsignore_content else 0
        print(f".bidsignore entries saved to: {args.output_bidsignore}")
        print(f"Total entries: {entry_count}")

    return 0


if __name__ == "__main__":
    exit(main())
