from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.qa.base import register_qa


def collect_fieldmap_identifiers(fmap_dir: Path) -> set[str]:
    """Return all B0FieldIdentifier values found in a session's fmap/ directory."""
    if not fmap_dir.is_dir():
        return set()
    identifiers: set[str] = set()
    for json_file in sorted(fmap_dir.glob("*.json")):
        try:
            data = json.loads(json_file.read_text())
            val = data.get("B0FieldIdentifier")
            if val is None:
                continue
            if isinstance(val, list):
                identifiers.update(val)
            else:
                identifiers.add(str(val))
        except Exception:
            pass
    return identifiers


def collect_func_b0_sources(func_dir: Path) -> list[tuple[str, set[str]]]:
    """Return (filename, {B0FieldSource values}) for func JSON sidecars that have B0FieldSource."""
    if not func_dir.is_dir():
        return []
    results = []
    for json_file in sorted(func_dir.glob("*_bold.json")):
        try:
            data = json.loads(json_file.read_text())
            val = data.get("B0FieldSource")
            if val is None:
                continue
            sources: set[str] = set(val) if isinstance(val, list) else {str(val)}
            results.append((json_file.name, sources))
        except Exception:
            pass
    return results


class FieldmapCheckQa:
    name = "fieldmap-check"
    description = "Verify every functional scan's B0FieldSource has a matching B0FieldIdentifier fieldmap in the same session"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        pass  # no extra args needed

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        bids_dir = Path(dataset_config["bids_dir"])

        sessions = sorted(bids_dir.glob("sub-*/ses-*"))
        if not sessions:
            # Try without session level
            sessions = sorted(bids_dir.glob("sub-*"))

        total_scans = 0
        missing_count = 0

        print(f"Checking B0FieldSource/B0FieldIdentifier matching for dataset '{dataset_name}'")
        print("=" * 70)

        for session_dir in sessions:
            func_dir = session_dir / "func"
            fmap_dir = session_dir / "fmap"

            func_sources = collect_func_b0_sources(func_dir)
            if not func_sources:
                continue

            fmap_identifiers = collect_fieldmap_identifiers(fmap_dir)
            total_scans += len(func_sources)

            for filename, sources in func_sources:
                missing = sources - fmap_identifiers
                if missing:
                    missing_count += 1
                    print(f"MISSING fieldmap: {session_dir.parent.name}/{session_dir.name}")
                    print(f"  Scan:    {filename}")
                    print(f"  B0FieldSource:     {sorted(sources)}")
                    print(f"  Session fieldmaps: {sorted(fmap_identifiers) or '(none)'}")
                    print(f"  Missing:           {sorted(missing)}")
                    print()

        print("=" * 70)
        print(f"Checked {total_scans} functional scans across {len(sessions)} sessions.")
        print(f"Result: {missing_count} scans with missing fieldmap B0FieldIdentifier.")


register_qa(FieldmapCheckQa())
