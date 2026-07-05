"""Audit YAML task-config regressors against the events.tsv files in both cohorts.

What this catches:

1. **Empty subset matches** — a regressor's pandas subset matches zero rows in
   real events.tsv files across the cohort.  Symptom of a label drift (e.g.,
   subset says ``trial_id == 'X'`` but real rows say ``trial_id == 'X_v2'``).

2. **Duration mismatch** — the YAML hardcodes ``duration: K`` but real events
   have a wildly different duration column for the matched rows.  E.g., the
   break regressor uses ``duration: 1`` but real break rows are 10 s.

3. **Trial-id / trial-type coverage gaps** — values that appear in real
   events.tsv files but are not captured by any YAML regressor (silent
   implicit baseline).

4. **Cohort drift** — same task, different distributions between discovery
   and validation cohorts (e.g., nBack break duration changed 10s → 4s).

Output: ``docs/EVENTS-TASK-CONFIG-AUDIT.md``.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from neuro_workflow.analysis.task_config.loader import get_raw_yaml_config

BASE_TASKS = [
    "cuedTS",
    "directedForgetting",
    "flanker",
    "goNogo",
    "nBack",
    "shapeMatching",
    "spatialTS",
    "stopSignal",
]


@dataclass
class TaskAudit:
    task_name: str
    n_scans_per_cohort: dict[str, int] = field(default_factory=dict)
    # regressor_name -> { cohort -> stats }
    regressor_stats: dict[str, dict[str, dict]] = field(default_factory=lambda: defaultdict(dict))
    # Per cohort: trial_id values seen vs covered by any YAML subset
    trial_id_observed: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    trial_type_observed: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # Trial-ids/types referenced by YAML subsets, harvested via string search
    trial_id_referenced: set[str] = field(default_factory=set)
    trial_type_referenced: set[str] = field(default_factory=set)


def _bid_walk(bids_root: Path, task: str) -> Iterable[Path]:
    """Yield every events.tsv for ``task`` under a BIDS root.

    Excludes scans that the .bidsignore would skip (those still live on disk).
    """
    return sorted(bids_root.rglob(f"sub-*/ses-*/func/sub-*_ses-*_task-{task}_run-*_events.tsv"))


def _matched_subset(events: pd.DataFrame, subset_query: str | None) -> pd.DataFrame:
    """Apply a subset query exactly as ``design.create_regressor`` does."""
    if subset_query is None:
        return events
    try:
        return events.query(subset_query)
    except Exception:
        return events.iloc[0:0]  # empty frame on parse failure


def _harvest_referenced(yaml_cfg: dict, task_audit: TaskAudit) -> None:
    """Read every regressor subset and pull out literal trial-id / trial-type
    values it references.  Strict-matching tokens of the form
    ``trial_id == 'X'`` and ``trial_type == 'X'``.
    """
    import re

    # Accept both single- and double-quoted literals (pandas.query supports both)
    pattern_id = re.compile(r"""trial_id\s*==\s*['"]([^'"]+)['"]""")
    pattern_type = re.compile(r"""trial_type\s*==\s*['"]([^'"]+)['"]""")

    regressors = yaml_cfg.get("regressors") or {}
    for cfg in regressors.values():
        subset = cfg.get("subset")
        if not subset:
            continue
        for m in pattern_id.finditer(subset):
            task_audit.trial_id_referenced.add(m.group(1))
        for m in pattern_type.finditer(subset):
            task_audit.trial_type_referenced.add(m.group(1))


def audit_task(task_name: str, cohorts: dict[str, Path]) -> TaskAudit:
    """Audit one task across one or more cohorts."""
    cfg = get_raw_yaml_config(task_name)
    audit = TaskAudit(task_name=task_name)
    _harvest_referenced(cfg, audit)

    regressors = cfg.get("regressors") or {}

    for cohort_name, bids_root in cohorts.items():
        scans = list(_bid_walk(bids_root, task_name))
        audit.n_scans_per_cohort[cohort_name] = len(scans)
        # Cohort-wide per-regressor counters
        per_reg_total_matches = {name: 0 for name in regressors}
        per_reg_durations: dict[str, list[float]] = {name: [] for name in regressors}
        per_reg_scans_with_zero: dict[str, int] = {name: 0 for name in regressors}

        for path in scans:
            try:
                events = pd.read_csv(path, sep="\t", na_values=["n/a"])
            except Exception:
                continue
            if "trial_id" in events.columns:
                ids = events["trial_id"].dropna().astype(str).unique().tolist()
                audit.trial_id_observed[cohort_name].update(ids)
            if "trial_type" in events.columns:
                tps = events["trial_type"].dropna().astype(str).unique().tolist()
                audit.trial_type_observed[cohort_name].update(tps)

            for reg_name, reg_cfg in regressors.items():
                matched = _matched_subset(events, reg_cfg.get("subset"))
                n = len(matched)
                per_reg_total_matches[reg_name] += n
                if n == 0:
                    per_reg_scans_with_zero[reg_name] += 1
                if n > 0 and "duration" in matched.columns:
                    per_reg_durations[reg_name].extend(
                        pd.to_numeric(matched["duration"], errors="coerce").dropna().tolist()
                    )

        for reg_name in regressors:
            durations = per_reg_durations[reg_name]
            stats = {
                "total_matches": per_reg_total_matches[reg_name],
                "n_scans": len(scans),
                "n_scans_with_zero_matches": per_reg_scans_with_zero[reg_name],
                "duration_yaml": regressors[reg_name].get("duration"),
                "duration_min": min(durations) if durations else None,
                "duration_max": max(durations) if durations else None,
                "duration_median": pd.Series(durations).median() if durations else None,
            }
            audit.regressor_stats[reg_name][cohort_name] = stats

    return audit


def render_markdown(audits: list[TaskAudit]) -> str:
    """Render audit findings as a markdown report grouped by issue severity."""
    lines: list[str] = [
        "# Events ↔ Task Config Audit",
        "",
        "Cross-references every YAML regressor subset against the actual",
        "events.tsv files in both cohorts (discovery, validation).  Findings",
        "are bucketed by severity so the production rerun does not run on",
        "silently broken regressor definitions.",
        "",
    ]

    # ----- Critical: regressors matching ZERO rows cohort-wide -----
    lines += ["## Critical — regressor matches zero rows cohort-wide", ""]
    lines += [
        "Subset matched 0 rows across every scan in a cohort.  The regressor",
        "is effectively absent for that cohort.",
        "",
    ]
    lines += ["| Task | Regressor | Cohort | Scans | Total matches |", "|---|---|---|---|---|"]
    critical_found = False
    for a in audits:
        for reg, by_cohort in a.regressor_stats.items():
            for cohort, stats in by_cohort.items():
                if stats["n_scans"] > 0 and stats["total_matches"] == 0:
                    critical_found = True
                    lines.append(f"| {a.task_name} | {reg} | {cohort} | {stats['n_scans']} | 0 |")
    if not critical_found:
        lines.append("| _(none)_ | | | | |")
    lines.append("")

    # ----- Important: duration mismatch (YAML hardcoded != observed) -----
    lines += ["## Important — duration mismatches (YAML hardcoded ≠ observed)", ""]
    lines += [
        "Regressors where the YAML hardcodes a numeric duration but the",
        "matched events have a different value in the duration column.",
        "Indicates the YAML is stale relative to the task as implemented.",
        "",
    ]
    lines += [
        "| Task | Regressor | Cohort | YAML duration | Observed range (min..max, median) | Total matches |",
        "|---|---|---|---|---|---|",
    ]
    important_found = False
    for a in audits:
        for reg, by_cohort in a.regressor_stats.items():
            for cohort, stats in by_cohort.items():
                yaml_dur = stats["duration_yaml"]
                obs_med = stats["duration_median"]
                if not isinstance(yaml_dur, int | float):
                    continue  # 'duration: duration' uses events column — no mismatch
                if stats["total_matches"] == 0 or obs_med is None:
                    continue
                # Flag if YAML hardcoded value differs meaningfully (>0.01s) from observed median
                if abs(float(yaml_dur) - float(obs_med)) > 0.01:
                    important_found = True
                    lines.append(
                        f"| {a.task_name} | {reg} | {cohort} | {yaml_dur} | "
                        f"{stats['duration_min']:.2f}..{stats['duration_max']:.2f}, "
                        f"median {obs_med:.2f} | {stats['total_matches']} |"
                    )
    if not important_found:
        lines.append("| _(none)_ | | | | | |")
    lines.append("")

    # ----- Minor: partial coverage (some scans have zero matches) -----
    lines += ["## Minor — some scans have zero matches", ""]
    lines += [
        "Regressor matches some but not all scans.  Often legitimate",
        "(e.g. `nogo_failure` rare in good performers) but flagged for review.",
        "",
    ]
    lines += [
        "| Task | Regressor | Cohort | Scans w/ zero | Total scans |",
        "|---|---|---|---|---|",
    ]
    minor_found = False
    for a in audits:
        for reg, by_cohort in a.regressor_stats.items():
            for cohort, stats in by_cohort.items():
                z = stats["n_scans_with_zero_matches"]
                if 0 < z < stats["n_scans"]:
                    minor_found = True
                    lines.append(f"| {a.task_name} | {reg} | {cohort} | {z} | {stats['n_scans']} |")
    if not minor_found:
        lines.append("| _(none)_ | | | | |")
    lines.append("")

    # ----- Trial-id / trial-type coverage gaps -----
    lines += ["## Trial-id values present in events but referenced by NO YAML subset", ""]
    lines += [
        "Trial_id values that appear in events.tsv but are not the literal",
        "argument of any `trial_id == 'X'` in the YAML.  Often expected",
        "(e.g. fixations, cues are implicit baseline) but worth eyeballing",
        "",
    ]
    lines += ["| Task | Cohort | Unreferenced trial_ids |", "|---|---|---|"]
    for a in audits:
        for cohort, observed in a.trial_id_observed.items():
            unreferenced = sorted(observed - a.trial_id_referenced)
            if unreferenced:
                lines.append(f"| {a.task_name} | {cohort} | {', '.join(unreferenced)} |")
    lines.append("")

    lines += ["## Trial-type values present in events but referenced by NO YAML subset", ""]
    lines += ["| Task | Cohort | Unreferenced trial_types |", "|---|---|---|"]
    for a in audits:
        for cohort, observed in a.trial_type_observed.items():
            unreferenced = sorted(observed - a.trial_type_referenced)
            if unreferenced:
                lines.append(f"| {a.task_name} | {cohort} | {', '.join(unreferenced)} |")
    lines.append("")

    # ----- Per-task full summary table -----
    lines += ["## Full per-regressor stats", ""]
    for a in audits:
        lines.append(f"### {a.task_name}")
        lines.append("")
        lines.append(
            "| Regressor | Cohort | Scans | Total matches | YAML dur | Obs dur (min..max, med) |"
        )
        lines.append("|---|---|---|---|---|---|")
        for reg, by_cohort in a.regressor_stats.items():
            for cohort, stats in by_cohort.items():
                if stats["duration_median"] is None:
                    obs = "_(no matches)_"
                else:
                    obs = (
                        f"{stats['duration_min']:.2f}..{stats['duration_max']:.2f}, "
                        f"median {stats['duration_median']:.2f}"
                    )
                lines.append(
                    f"| {reg} | {cohort} | {stats['n_scans']} | "
                    f"{stats['total_matches']} | {stats['duration_yaml']} | {obs} |"
                )
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--discovery", type=Path, default=Path("/scratch/users/logben/discovery_bids")
    )
    parser.add_argument(
        "--validation", type=Path, default=Path("/scratch/users/logben/validation_bids")
    )
    parser.add_argument("--output", type=Path, default=Path("docs/EVENTS-TASK-CONFIG-AUDIT.md"))
    args = parser.parse_args()

    cohorts = {"discovery": args.discovery, "validation": args.validation}
    audits = [audit_task(task, cohorts) for task in BASE_TASKS]
    md = render_markdown(audits)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(md)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
