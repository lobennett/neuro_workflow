#!/usr/bin/env python3
"""One-time: capture a Flywheel project inventory to data/repro/fw_inventory_<cohort>.json.

Usage
-----
    uv run python scripts/capture_fw_inventory.py discovery
    uv run python scripts/capture_fw_inventory.py validation
    uv run python scripts/capture_fw_inventory.py discovery --out /tmp/inv.json
    uv run python scripts/capture_fw_inventory.py discovery --project russpold/r01network

The script requires the ``flywheel-sdk`` to be importable (it is NOT a package
dependency — install it in your personal environment before running).  The
``fw_project_to_inventory`` transform itself has no SDK import and is unit-tested
on duck-typed fakes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from neuro_workflow.testing.reproduce.snapshot import fw_project_to_inventory


def _load_pipeline_config() -> dict:
    """Load config/pipeline_config.json relative to this script's repo root."""
    here = Path(__file__).resolve().parent
    cfg_path = here.parent / "config" / "pipeline_config.json"
    return json.loads(cfg_path.read_text())


def _project_from_config(fw) -> object:
    """Resolve the Flywheel project from config/pipeline_config.json.

    pipeline_config.json stores the project label under ``flywheel.project``
    (e.g. ``"r01network"``).  The real SDK lookup uses ``fw.lookup("<group>/<project>")``
    but the project_label alone is also resolvable via ``fw.projects.find_first``.

    Production ``bidsify/run.py`` uses ``query_project_subjects(fw, project_label)``
    which calls ``fw.projects.find_first(f'label="{project_label}"')``.  We mirror
    that here: look up by label so the call is consistent with how bidsify resolves it.
    """
    config = _load_pipeline_config()
    project_label: str = config["flywheel"]["project"]
    project = fw.projects.find_first(f'label="{project_label}"')
    if project is None:
        raise ValueError(
            f"Flywheel project '{project_label}' not found. "
            "Check your API key and group membership."
        )
    return project


def main() -> None:
    p = argparse.ArgumentParser(
        description="Capture a one-time Flywheel project inventory snapshot."
    )
    p.add_argument(
        "cohort",
        choices=["discovery", "validation"],
        help="Which cohort label to embed in the output filename.",
    )
    p.add_argument(
        "--project",
        default=None,
        help=(
            "Flywheel lookup string passed to fw.lookup(), e.g. 'russpold/r01network'. "
            "Defaults to the project label in config/pipeline_config.json resolved "
            "via fw.projects.find_first."
        ),
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help=(
            "Output path for the inventory JSON. "
            "Defaults to data/repro/fw_inventory_<cohort>.json."
        ),
    )
    a = p.parse_args()

    import flywheel  # noqa: PLC0415 -- SDK required at runtime, not at import

    fw = flywheel.Client()
    if a.project:
        proj = fw.lookup(a.project)
    else:
        proj = _project_from_config(fw)

    inv = fw_project_to_inventory(proj)

    out = a.out or Path("data/repro") / f"fw_inventory_{a.cohort}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inv, indent=2, default=str))
    print(f"wrote {out}  ({len(inv['subjects'])} subjects)")


if __name__ == "__main__":
    main()
