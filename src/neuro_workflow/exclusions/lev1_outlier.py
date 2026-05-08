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


def _to_float_or_zero(value: str | None) -> float:
    """Empty string / NaN-ish -> 0.0; otherwise parsed float."""
    if value is None or value == "":
        return 0.0
    try:
        f = float(value)
    except ValueError:
        return 0.0
    if f != f:  # NaN check without importing math
        return 0.0
    return f


def _read_outliers_csv(path: Path) -> list[dict]:
    """Read the lev1_outliers.csv into a list of dicts."""
    if not path.is_file():
        raise FileNotFoundError(f"lev1_outliers.csv not found: {path}")
    with path.open() as f:
        return list(csv.DictReader(f))


def _load_dataset_subjects(dataset_config: dict) -> set[str] | None:
    """Return the dataset's subject IDs (with `sub-` prefix) from `subjects_file`,
    or None if the config has no resolvable subjects file. Bare IDs in the file
    (e.g. `s10`) are normalised to `sub-s10` to match CSV row IDs."""
    raw = dataset_config.get("subjects_file")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        # subjects_file is stored relative to the cwd at registration time.
        # Try cwd first; the user runs CLI from the repo root.
        path = Path.cwd() / raw
    if not path.is_file():
        return None
    subjects: set[str] = set()
    for line in path.read_text().splitlines():
        sid = line.strip()
        if not sid or sid.startswith("#"):
            continue
        subjects.add(sid if sid.startswith("sub-") else f"sub-{sid}")
    return subjects or None


def _rules_fired(vif: float, outlier_pct: float, t: Thresholds) -> list[str]:
    """Return the names of all rules that fire for this (vif, outlier_pct) pair."""
    fired: list[str] = []
    if vif >= t.combined_vif and outlier_pct >= t.combined_outlier_pct:
        fired.append("combined")
    if vif >= t.strict_vif:
        fired.append("strict_vif")
    if outlier_pct >= t.strict_outlier_pct:
        fired.append("strict_outliers")
    return fired


def _format_contrast_clause(contrast: str, vif: float, outlier_pct: float,
                            rules: list[str]) -> str:
    """Single-contrast clause for the `reason` field, e.g.
    'response_time vif=18.09 (strict_vif)'.
    """
    parts: list[str] = [f"vif={vif:.2f}"]
    if outlier_pct > 0:
        parts.append(f"outlier={outlier_pct:.1f}%")
    return f"{contrast} {','.join(parts)} ({','.join(rules)})"


def _aggregate_to_scan_entries(
    rows: list[dict], thresholds: Thresholds,
) -> list[dict]:
    """Group rows by (subject, session, task, run); emit one exclusion entry per
    scan that has at least one contrast firing any rule."""
    by_scan: dict[tuple[str, str, str, str], list[dict]] = {}
    for row in rows:
        key = (row["subject"], row["session"], row["task"], row["run"])
        by_scan.setdefault(key, []).append(row)

    entries: list[dict] = []
    for (subject, session, task, run), scan_rows in sorted(by_scan.items()):
        flagged: list[tuple[str, float, float, list[str]]] = []
        for row in scan_rows:
            vif = _to_float_or_zero(row.get("vif"))
            pct = _to_float_or_zero(row.get("outlier_pct"))
            fired = _rules_fired(vif, pct, thresholds)
            if fired:
                flagged.append((row["contrast"], vif, pct, fired))
        if not flagged:
            continue
        clauses = [
            _format_contrast_clause(c, v, p, r) for c, v, p, r in flagged
        ]
        all_rules: set[str] = set()
        for _, _, _, r in flagged:
            all_rules.update(r)
        max_vif = max(v for _, v, _, _ in flagged)
        max_pct = max(p for _, _, p, _ in flagged)
        entries.append({
            "subject": subject,
            "session": session,
            "task": f"task-{task}",
            "run": f"run-{run}",
            "source": "lev1_outlier",
            "action": "exclude",
            "reason": "lev1_outlier: " + "; ".join(clauses),
            "metrics": {
                "max_vif": max_vif,
                "max_outlier_pct": max_pct,
                "n_flagged_contrasts": len(flagged),
                "rules_fired": sorted(all_rules),
            },
        })
    return entries


class Lev1OutlierGenerator:
    name = "lev1_outlier"
    description = (
        "Auto-exclude scans flagged by cohort lev1 QC. Rules: "
        "(vif>=combined-vif AND outlier_pct>=combined-outlier-pct) OR "
        "vif>=strict-vif OR outlier_pct>=strict-outlier-pct."
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--lev1-outliers-csv", type=Path, required=True,
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
        thresholds = Thresholds(
            combined_vif=args.combined_vif,
            combined_outlier_pct=args.combined_outlier_pct,
            strict_vif=args.strict_vif,
            strict_outlier_pct=args.strict_outlier_pct,
        )
        rows = _read_outliers_csv(args.lev1_outliers_csv)
        sample = _load_dataset_subjects(dataset_config)
        if sample is not None:
            before = len(rows)
            rows = [r for r in rows if r["subject"] in sample]
            dropped = before - len(rows)
            if dropped:
                print(
                    f"lev1_outlier: dropped {dropped}/{before} rows whose subject "
                    f"is not in dataset '{dataset_name}' ({len(sample)} subjects)."
                )
        return _aggregate_to_scan_entries(rows, thresholds)


register_generator(Lev1OutlierGenerator())
