"""Wrapper around bold-reliability-movies for cohort QA report integration.

Invokes the `brm` CLI as a subprocess so brm can run in its own Python 3.12
environment (installed via `uv tool install bold-reliability-movies`). The
project venv is Python 3.13, where brm's scipy<1.15 constraint can't resolve.
"""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_BRM_CMD = "brm"  # must be on PATH (uv tool install puts it in ~/.local/bin)


@dataclass
class MovieResult:
    path: Path | None
    error: str | None


def _strip_sub_prefix(subject: str) -> str:
    return subject[4:] if subject.startswith("sub-") else subject


def _run_brm_for_subject(
    fmriprep_dir: Path,
    output_movies_dir: Path,
    subject: str,
) -> MovieResult:
    """Render one reliability movie for a single subject via the brm CLI."""
    expected_path = output_movies_dir / f"{subject}.mp4"
    cmd = [
        _BRM_CMD, "bids", str(fmriprep_dir),
        "--out", str(output_movies_dir),
        "--filter", f"sub={_strip_sub_prefix(subject)}",
        "--group-by", "subject",
        "--no-cache",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return MovieResult(None, "brm CLI not found on PATH")

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = " | ".join(msg[-3:]) if msg else f"exit {proc.returncode}"
        return MovieResult(None, f"brm failed: {tail}")

    if not expected_path.is_file():
        return MovieResult(None, "brm exited 0 but produced no output file")

    return MovieResult(expected_path, None)


def render_reliability_movies(
    fmriprep_dir: Path,
    output_movies_dir: Path,
    subjects: list[str],
) -> dict[str, MovieResult]:
    """Render one reliability movie per requested subject.

    Args:
        fmriprep_dir: fmriprep derivatives directory (input).
        output_movies_dir: where mp4 files are written.
        subjects: list of subject IDs (e.g., ["sub-s03"]) to render.

    Returns:
        Dict mapping subject ID -> MovieResult. On error, MovieResult.path
        is None and .error contains a short message.
    """
    output_movies_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, MovieResult] = {}
    for sub in subjects:
        try:
            results[sub] = _run_brm_for_subject(fmriprep_dir, output_movies_dir, sub)
        except Exception as exc:  # noqa: BLE001
            log.exception("brm wrapper raised for %s", sub)
            results[sub] = MovieResult(None, str(exc))
    return results
