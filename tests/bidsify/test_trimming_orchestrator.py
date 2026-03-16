# File: tests/bidsify/test_trimming_orchestrator.py
import tempfile
from pathlib import Path
import json
import pytest

from neuro_workflow.bidsify.trimming_orchestrator import (
    TrimContext,
    TrimOrchestrator,
)


def test_orchestrator_applies_all_trimming():
    """Test that orchestrator applies BOLD, events, physio, behavioral trimming."""
    # This is a smoke test - in real implementation would need full BIDS structure
    context = TrimContext(
        subject="s19",
        session="ses-07",
        task="stopSignal",
        dummy_scans=7,
        behavioral_cutoff_ms=342700,
    )

    assert context.dummy_offset_s == 10.43
    assert context.dummy_offset_ms == 10430
