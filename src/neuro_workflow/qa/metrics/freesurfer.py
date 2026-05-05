"""FreeSurfer surface QC metrics extracted from recon-all output."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


_EULER_RE = re.compile(r"orig\.nofix\s+lheno\s*=\s*(-?\d+)\s*,\s*rheno\s*=\s*(-?\d+)")
_ELAPSED_RE = re.compile(r"recon-all-run-time-hours\s+([\d.]+)")
_ASEG_RE = re.compile(r"#\s*Measure\s+(\w+),.*?,\s*([\d.]+),\s*mm")


Status = Literal["OK", "FAILED", "INCOMPLETE", "MISSING"]


@dataclass
class FreeSurferMetrics:
    status: Status
    elapsed_hours: float | None
    euler_lh: int | None
    euler_rh: int | None
    euler_mean: float | None
    holes_lh: int | None
    holes_rh: int | None
    holes_mean: float | None
    brain_vol: float | None
    gm_vol: float | None
    wm_vol: float | None
    csf_vol: float | None
    etiv: float | None


def parse_euler_from_log(recon_all_log: Path) -> tuple[int, int] | None:
    """Return (lh_euler, rh_euler) parsed from recon-all.log, or None if not found."""
    if not recon_all_log.is_file():
        return None
    for line in recon_all_log.read_text().splitlines():
        m = _EULER_RE.search(line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def parse_recon_all_status(status_log: Path) -> Status:
    """Return OK / FAILED / INCOMPLETE based on recon-all-status.log content."""
    if not status_log.is_file():
        return "INCOMPLETE"
    text = status_log.read_text()
    if "finished without error" in text:
        return "OK"
    if "exited with ERRORS" in text or "ERROR" in text:
        return "FAILED"
    return "INCOMPLETE"


def parse_aseg_stats(aseg_stats: Path) -> dict[str, float]:
    """Parse aseg.stats Measure lines into a dict of named volumes."""
    if not aseg_stats.is_file():
        return {}
    text = aseg_stats.read_text()
    label_to_key = {
        "BrainSeg": "brain_vol",
        "TotalGray": "gm_vol",
        "CerebralWhiteMatter": "wm_vol",
        "CSF": "csf_vol",
        "EstimatedTotalIntraCranialVol": "etiv",
    }
    out: dict[str, float] = {}
    for line in text.splitlines():
        m = _ASEG_RE.search(line)
        if m:
            label, val = m.group(1), m.group(2)
            if label in label_to_key:
                out[label_to_key[label]] = float(val)
    return out


def _parse_elapsed(recon_all_log: Path) -> float | None:
    if not recon_all_log.is_file():
        return None
    for line in recon_all_log.read_text().splitlines():
        m = _ELAPSED_RE.search(line)
        if m:
            return float(m.group(1))
    return None


def compute_freesurfer(fs_subject_dir: Path) -> FreeSurferMetrics:
    """Compute FreeSurfer QC metrics from a recon-all subject directory."""
    if not fs_subject_dir.is_dir():
        return FreeSurferMetrics(
            status="MISSING",
            elapsed_hours=None,
            euler_lh=None, euler_rh=None, euler_mean=None,
            holes_lh=None, holes_rh=None, holes_mean=None,
            brain_vol=None, gm_vol=None, wm_vol=None, csf_vol=None, etiv=None,
        )

    status = parse_recon_all_status(fs_subject_dir / "scripts" / "recon-all-status.log")
    elapsed = _parse_elapsed(fs_subject_dir / "scripts" / "recon-all.log")
    euler = parse_euler_from_log(fs_subject_dir / "scripts" / "recon-all.log")
    aseg = parse_aseg_stats(fs_subject_dir / "stats" / "aseg.stats")

    if euler is None:
        euler_lh = euler_rh = euler_mean = None
        holes_lh = holes_rh = holes_mean = None
    else:
        euler_lh, euler_rh = euler
        euler_mean = (euler_lh + euler_rh) / 2.0
        holes_lh = (2 - euler_lh) // 2
        holes_rh = (2 - euler_rh) // 2
        holes_mean = (holes_lh + holes_rh) / 2.0

    return FreeSurferMetrics(
        status=status,
        elapsed_hours=elapsed,
        euler_lh=euler_lh,
        euler_rh=euler_rh,
        euler_mean=euler_mean,
        holes_lh=holes_lh,
        holes_rh=holes_rh,
        holes_mean=holes_mean,
        brain_vol=aseg.get("brain_vol"),
        gm_vol=aseg.get("gm_vol"),
        wm_vol=aseg.get("wm_vol"),
        csf_vol=aseg.get("csf_vol"),
        etiv=aseg.get("etiv"),
    )
