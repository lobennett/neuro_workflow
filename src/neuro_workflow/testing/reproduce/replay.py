"""Replay a Flywheel snapshot through the REAL bidsify -> trim -> events chain,
producing a stub BIDS tree (tiny valid NIfTIs)."""
from __future__ import annotations
import importlib.util as _ilu
from pathlib import Path

from neuro_workflow.bidsify.run import run_bidsify
from neuro_workflow.events.create import run_create_events
from neuro_workflow.testing.fake_flywheel import FlywheelCohortSpec, make_fake_flywheel


def _trim_dir(bids_dir: Path):
    trim_path = Path(__file__).resolve().parents[4] / "scripts" / "trim_bold.py"
    spec = _ilu.spec_from_file_location("trim_bold", str(trim_path))
    mod = _ilu.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.trim_bold_directory(bids_dir)


def replay_to_bids(spec: FlywheelCohortSpec, root: Path, *, sample_name: str,
                   behavioral_dir: Path, install_flywheel) -> Path:
    root = Path(root); bids = root / "bids"
    fake = make_fake_flywheel(spec)
    install_flywheel(fake)
    subjects = [s.label for s in spec.subjects]
    run_bidsify(sample_name, output_dir=bids, subjects=subjects, overwrite=True)
    _trim_dir(bids)
    # run_create_events walks behavioral_dir.glob("sub-*"); create the dir if it
    # doesn't exist so an empty behavioral_dir is a valid no-op rather than a
    # FileNotFoundError.
    behavioral_dir = Path(behavioral_dir)
    behavioral_dir.mkdir(parents=True, exist_ok=True)
    run_create_events(behavioral_dir=behavioral_dir, bids_dir=bids)
    return bids
