"""Wrapper around bold-reliability-movies for cohort QA report integration.

Invokes the `brm` CLI as a subprocess so brm can run in its own Python 3.12
environment (installed via `uv tool install bold-reliability-movies`). The
project venv is Python 3.13, where brm's scipy<1.15 constraint can't resolve.

Important: brm's built-in fmriprep discovery globs every `*_desc-preproc_bold.nii.gz`
under each session, which sweeps in T1w/MNI/native variants of the same scan.
Those have different array shapes, so brm rejects the group at its shape-check
step. Workaround: we pre-filter to native-space preproc only and feed brm a
manifest via `brm list`.
"""
from __future__ import annotations

import csv
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_BRM_CMD = "brm"
_NATIVE_PREPROC_RE = re.compile(
    r"^(?P<sub>sub-[A-Za-z0-9]+)_"
    r"(?P<ses>ses-[A-Za-z0-9]+)_"
    r"task-(?P<task>[A-Za-z0-9]+)_"
    r"run-(?P<run>\d+)_"
    r"desc-preproc_bold\.nii\.gz$"  # no `_space-` token → native space
)


@dataclass
class MovieResult:
    path: Path | None
    error: str | None


def _discover_native_preproc(fmriprep_dir: Path, subject: str) -> list[tuple[Path, str, int]]:
    """Find native-space preproc BOLDs for one subject.

    Returns a list of (path, label, sort_key) tuples in canonical scan order.
    The label is human-readable ('ses-01 task-rest run-1'); sort_key is an
    integer for ordering frames within the movie.
    """
    out: list[tuple[Path, str, int]] = []
    sub_dir = fmriprep_dir / subject
    if not sub_dir.is_dir():
        return out
    for path in sub_dir.glob("ses-*/func/*_desc-preproc_bold.nii.gz"):
        m = _NATIVE_PREPROC_RE.match(path.name)
        if not m:
            continue
        ses = m.group("ses")
        task = m.group("task")
        run = m.group("run")
        # ses-01 < ses-02 < ... — extract numeric for ordering
        ses_num_match = re.search(r"\d+", ses)
        ses_num = int(ses_num_match.group()) if ses_num_match else 0
        sort_key = ses_num * 1000 + int(run)
        label = f"{ses} task-{task} run-{run}"
        out.append((path, label, sort_key))
    out.sort(key=lambda t: t[2])
    return out


def _write_manifest(rows: list[tuple[Path, str, int]], group: str, manifest: Path) -> None:
    with manifest.open("w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["path", "label", "group", "sort_key"])
        for path, label, sort_key in rows:
            writer.writerow([str(path), label, group, sort_key])


def _run_brm_for_subject(
    fmriprep_dir: Path,
    output_movies_dir: Path,
    subject: str,
) -> MovieResult:
    """Render one reliability movie for a single subject via the brm CLI."""
    rows = _discover_native_preproc(fmriprep_dir, subject)
    if not rows:
        return MovieResult(None, "no native-space preproc BOLDs found")

    expected_path = output_movies_dir / f"{subject}.mp4"

    with tempfile.NamedTemporaryFile(
        "w", suffix=".tsv", prefix=f"brm_{subject}_", delete=False
    ) as tf:
        manifest_path = Path(tf.name)
    try:
        _write_manifest(rows, group=subject, manifest=manifest_path)
        cmd = [
            _BRM_CMD, "list", str(manifest_path),
            "--out", str(output_movies_dir),
            "--renderer", "mosaic",
            "--no-cache",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return MovieResult(None, "brm CLI not found on PATH")
    finally:
        manifest_path.unlink(missing_ok=True)

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
