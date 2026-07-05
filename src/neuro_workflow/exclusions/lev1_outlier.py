"""Lev1 outlier exclusion generator.

Reads cohort QC's lev1_outliers.csv (produced by neuro_workflow.qa.lev1_outliers)
and applies three OR'd auto-exclude rules PER CONTRAST:

    combined:        vif >= combined_vif AND outlier_pct >= combined_outlier_pct
    strict_vif:      vif >= strict_vif
    strict_outliers: outlier_pct >= strict_outlier_pct

Per-contrast emission: each (subject, session, run, contrast) that fires a rule
gets its own ``action='exclude-contrast'`` entry carrying a ``contrast`` field.
Unlike scan-level exclusions these do NOT remove the BOLD (no .bidsignore glob,
no lev1 run-skip); they drop only that contrast's fixed-effects contribution via
the per-contrast ``belowMinRuns`` floor (see fixed_effects.py + the design doc).

The VIF rules (combined, strict_vif) are SKIPPED for ``exempt_contrasts``
(task-baseline, response_time) — structurally high-VIF, not quality signals; the
outlier-only rule still applies to them.
"""

from __future__ import annotations

import csv
from argparse import ArgumentParser, Namespace
from dataclasses import dataclass
from pathlib import Path

from neuro_workflow.core.thresholds import lev1_outlier as _lev1_thresholds
from neuro_workflow.exclusions.base import load_dataset_subjects, register_generator

_LEV1 = _lev1_thresholds()


@dataclass(frozen=True)
class Thresholds:
    """Auto-exclude thresholds. Defaults sourced from config/thresholds.yaml."""

    combined_vif: float = _LEV1["combined_vif"]
    combined_outlier_pct: float = _LEV1["combined_outlier_pct"]
    strict_vif: float = _LEV1["strict_vif"]
    strict_outlier_pct: float = _LEV1["strict_outlier_pct"]


# Contrasts exempt from the VIF rules (structurally high-VIF, not quality signals).
# The outlier-only rule still applies to them. Sourced from config/thresholds.yaml.
_EXEMPT_CONTRASTS = frozenset(_LEV1.get("exempt_contrasts", ["task-baseline", "response_time"]))


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


def _rules_fired(
    vif: float, outlier_pct: float, t: Thresholds, *, vif_exempt: bool = False
) -> list[str]:
    """Return the names of all rules that fire for this (vif, outlier_pct) pair.

    ``vif_exempt`` skips the two VIF-based rules (``combined``, ``strict_vif``)
    for structurally high-VIF contrasts (task-baseline / response_time); the
    outlier-only rule still applies.
    """
    fired: list[str] = []
    if not vif_exempt:
        if vif >= t.combined_vif and outlier_pct >= t.combined_outlier_pct:
            fired.append("combined")
        if vif >= t.strict_vif:
            fired.append("strict_vif")
    if outlier_pct >= t.strict_outlier_pct:
        fired.append("strict_outliers")
    return fired


def _format_contrast_clause(contrast: str, vif: float, outlier_pct: float, rules: list[str]) -> str:
    """Single-contrast clause for the `reason` field, e.g.
    'response_time vif=18.09 (strict_vif)'.
    """
    parts: list[str] = [f"vif={vif:.2f}"]
    if outlier_pct > 0:
        parts.append(f"outlier={outlier_pct:.1f}%")
    return f"{contrast} {','.join(parts)} ({','.join(rules)})"


def _emit_contrast_entries(
    rows: list[dict],
    thresholds: Thresholds,
    exempt: frozenset[str] = _EXEMPT_CONTRASTS,
) -> list[dict]:
    """Emit one PER-CONTRAST exclusion entry for each (subject, session, run,
    contrast) firing a rule.

    VIF rules are skipped for contrasts in ``exempt`` (structurally high-VIF).
    Entries use ``action='exclude-contrast'`` and carry a ``contrast`` field;
    they drop only that contrast's fixed-effects contribution (via the per-contrast
    ``belowMinRuns`` floor), NOT the whole scan — see the design doc.
    """
    entries: list[dict] = []
    for row in rows:
        contrast = row["contrast"]
        vif = _to_float_or_zero(row.get("vif"))
        pct = _to_float_or_zero(row.get("outlier_pct"))
        fired = _rules_fired(vif, pct, thresholds, vif_exempt=(contrast in exempt))
        if not fired:
            continue
        entries.append(
            {
                "subject": row["subject"],
                "session": row["session"],
                "task": f"task-{row['task']}",
                "run": f"run-{row['run']}",
                "contrast": contrast,
                "source": "lev1_outlier",
                "action": "exclude-contrast",
                "reason": "lev1_outlier: " + _format_contrast_clause(contrast, vif, pct, fired),
                "metrics": {
                    "vif": vif,
                    "outlier_pct": pct,
                    "rules_fired": fired,
                },
            }
        )
    return sorted(
        entries,
        key=lambda e: (e["subject"], e["session"], e["task"], e["run"], e["contrast"]),
    )


class Lev1OutlierGenerator:
    name = "lev1_outlier"
    description = (
        "Auto-exclude scans flagged by cohort lev1 QC. Rules: "
        "(vif>=combined-vif AND outlier_pct>=combined-outlier-pct) OR "
        "vif>=strict-vif OR outlier_pct>=strict-outlier-pct."
    )

    def add_cli_args(self, parser: ArgumentParser) -> None:
        # Not argparse-required: every generator's args land on the same shared
        # subparser, so a global required=True breaks unrelated `generate motion`
        # / `generate behavioral` invocations. The runtime guard in generate()
        # raises the clear FileNotFoundError when this source is selected.
        parser.add_argument(
            "--lev1-outliers-csv",
            type=Path,
            help="Path to cohort QC's lev1_outliers.csv (required when source=lev1_outlier).",
        )
        parser.add_argument("--combined-vif", type=float, default=_LEV1["combined_vif"])
        parser.add_argument(
            "--combined-outlier-pct", type=float, default=_LEV1["combined_outlier_pct"]
        )
        parser.add_argument("--strict-vif", type=float, default=_LEV1["strict_vif"])
        parser.add_argument("--strict-outlier-pct", type=float, default=_LEV1["strict_outlier_pct"])

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
        if args.lev1_outliers_csv is None:
            raise FileNotFoundError("lev1_outlier generator requires --lev1-outliers-csv")
        rows = _read_outliers_csv(args.lev1_outliers_csv)
        # Canonical roster from pipeline_config.json `samples` (fail-loud on an
        # unknown dataset). Drops cross-sample rows from a pooled QC CSV.
        sample = load_dataset_subjects(dataset_name)
        before = len(rows)
        rows = [r for r in rows if r["subject"] in sample]
        dropped = before - len(rows)
        if dropped:
            print(
                f"lev1_outlier: dropped {dropped}/{before} rows whose subject "
                f"is not in dataset '{dataset_name}' ({len(sample)} subjects)."
            )
        return _emit_contrast_entries(rows, thresholds)


register_generator(Lev1OutlierGenerator())
