# File: tests/bidsify/test_bold_trimming.py
import json
import tempfile
from pathlib import Path
import nibabel as nib
import numpy as np
import pandas as pd
import pytest

from neuro_workflow.bidsify.bold_trimming import (
    trim_bold_nifti,
    trim_events_tsv,
)


def test_trim_bold_nifti_removes_dummy_volumes():
    """Test that dummy volumes are removed from BOLD NIfTI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock 4D NIfTI with 500 volumes (493 data + 7 dummies)
        data = np.random.rand(10, 10, 10, 500)
        img = nib.Nifti1Image(data, np.eye(4))
        bold_file = tmpdir / "test_bold.nii.gz"
        nib.save(img, bold_file)

        # Trim 7 dummies
        trim_bold_nifti(bold_file, dummy_scans=7, behavioral_cutoff_trs=None)

        # Verify output shape
        trimmed = nib.load(bold_file)
        assert trimmed.shape[3] == 493  # 500 - 7


def test_trim_bold_nifti_with_behavioral_cutoff():
    """Test BOLD trimming with behavioral cutoff."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock NIfTI with 500 volumes
        data = np.random.rand(10, 10, 10, 500)
        img = nib.Nifti1Image(data, np.eye(4))
        bold_file = tmpdir / "test_bold.nii.gz"
        nib.save(img, bold_file)

        # Trim 7 dummies + keep only 300 TRs (behavioral cutoff)
        trim_bold_nifti(bold_file, dummy_scans=7, behavioral_cutoff_trs=300)

        # Verify output shape: 300 TRs kept (after 7 dummies removed)
        trimmed = nib.load(bold_file)
        assert trimmed.shape[3] == 300


def test_trim_events_tsv_removes_events_during_dummies():
    """Test that events occurring during dummy scans are removed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create mock events TSV
        events_df = pd.DataFrame({
            'onset': [5.0, 10.5, 25.0, 40.0],
            'duration': [1.0, 1.0, 1.0, 1.0],
            'trial_type': ['go', 'go', 'go', 'go'],
        })
        events_file = tmpdir / "events.tsv"
        events_df.to_csv(events_file, sep='\t', index=False)

        # Trim (dummy_scans=7, tr=1.49 => adjustment=10.43 seconds)
        # Event at 5.0s would become -5.43s (during dummies, removed)
        # Event at 10.5s would become 0.07s (kept)
        trim_events_tsv(events_file, dummy_scans=7, tr=1.49, behavioral_cutoff_trs=None)

        # Verify onsets adjusted and early events removed
        trimmed = pd.read_csv(events_file, sep='\t')
        assert len(trimmed) == 3  # Event at 5.0s removed
        assert trimmed['onset'].min() >= 0  # No negative onsets
