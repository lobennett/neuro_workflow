"""Reproduction diff + Markdown report."""

from __future__ import annotations


def diff_sets(produced: set, reference: set) -> dict:
    return {
        "matched": produced & reference,
        "only_produced": produced - reference,
        "only_reference": reference - produced,
    }


def _passed(d: dict) -> bool:
    return not d["only_produced"] and not d["only_reference"]


def build_report(
    cohort: str, filenames: dict, exclusions: dict, lev2: dict, *, provenance: dict
) -> str:
    ok = all(_passed(d) for d in (filenames, exclusions, lev2))
    lines = [f"# Reproduction report — {cohort}: {'PASS' if ok else 'FAIL'}", ""]
    lines.append("## Provenance")
    for k, v in provenance.items():
        lines.append(f"- {k}: {v}")
    for name, d in (
        ("Filenames", filenames),
        ("Exclusion set", exclusions),
        ("Lev2-eligible set", lev2),
    ):
        lines += [
            "",
            f"## {name}: {'PASS' if _passed(d) else 'FAIL'}",
            f"- matched: {len(d['matched'])}",
            f"- only in produced ({len(d['only_produced'])}): "
            f"{sorted(d['only_produced'])[:20]}",
            f"- only in reference ({len(d['only_reference'])}): "
            f"{sorted(d['only_reference'])[:20]}",
        ]
    return "\n".join(lines) + "\n"
