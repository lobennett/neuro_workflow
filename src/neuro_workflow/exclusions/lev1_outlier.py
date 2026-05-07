"""Lev1 outlier exclusion generator.

Reads cohort QC's lev1_outliers.csv (produced by neuro_workflow.qa.lev1_outliers)
and applies three OR'd auto-exclude rules to flag whole scans:

    combined:        vif >= combined_vif AND outlier_pct >= combined_outlier_pct
    strict_vif:      vif >= strict_vif
    strict_outliers: outlier_pct >= strict_outlier_pct

Per-scan aggregation: if any contrast on (subject, session, task, run) fires
any rule, emit one exclusion entry whose `reason` lists the offending
contrasts and which rule fired for each.
"""
from __future__ import annotations

import csv
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path

from neuro_workflow.exclusions.base import register_generator


@dataclass(frozen=True)
class Thresholds:
    """Auto-exclude thresholds. Defaults match spec defaults."""
    combined_vif: float = 10.0
    combined_outlier_pct: float = 10.0
    strict_vif: float = 15.0
    strict_outlier_pct: float = 15.0


class Lev1OutlierGenerator:
    name = "lev1_outlier"
    description = (
        "Auto-exclude scans flagged by cohort lev1 QC. Rules: "
        "(vif>=combined-vif AND outlier_pct>=combined-outlier-pct) OR "
        "vif>=strict-vif OR outlier_pct>=strict-outlier-pct."
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--lev1-outliers-csv", type=Path,
            help="Path to cohort QC's lev1_outliers.csv (full per-(scan, contrast) table).",
        )
        parser.add_argument("--combined-vif", type=float, default=10.0)
        parser.add_argument("--combined-outlier-pct", type=float, default=10.0)
        parser.add_argument("--strict-vif", type=float, default=15.0)
        parser.add_argument("--strict-outlier-pct", type=float, default=15.0)

    def generate(
        self,
        dataset_name: str,
        dataset_config: dict,
        args: Namespace,
    ) -> list[dict]:
        # Filled in by Tasks 3-6.
        return []


register_generator(Lev1OutlierGenerator())
