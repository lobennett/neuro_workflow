"""RF-6 guard: the prevalence driver/figure scripts must share one cell list.

The 8 main (task, contrast) cells were previously hard-coded verbatim in three
scripts. They now import the single ``aggregate.MAIN_CELLS``; this test fails if
any script reintroduces a private copy (an identity check, not just equality).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `import scripts.X` resolve from the repo root (mirrors tests/scripts/conftest.py).
_ROOT = Path(__file__).resolve().parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from neuro_workflow.analysis.prevalence.aggregate import MAIN_CELLS

import scripts.prevalence_by_instance_run as by_instance_run
import scripts.prevalence_instance_panel as instance_panel
import scripts.prevalence_instance_trend as instance_trend


def test_scripts_share_the_single_main_cells_object():
    assert by_instance_run.MAIN_CELLS is MAIN_CELLS
    assert instance_panel.CELLS is MAIN_CELLS
    assert instance_trend.CELLS is MAIN_CELLS
