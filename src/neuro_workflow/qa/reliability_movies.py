"""Wrapper around bold-reliability-movies for cohort QA report integration.

Invokes the `brm` CLI as a subprocess so brm can run in its own Python 3.12
environment (installed via `uv tool install bold-reliability-movies`). The
project venv is Python 3.13, where brm's scipy<1.15 constraint can't resolve.

Renders one movie per (space, res) combination found in the derivatives so
each space gets its own header in the QA report. We bypass brm's bids
discovery (which sweeps in mismatched-shape variants together) and feed
brm a manifest TSV per (subject, space) group via `brm list`.
"""
from __future__ import annotations

import csv
import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

_BRM_CMD = "brm"
_PREPROC_RE = re.compile(
    r"^(?P<sub>sub-[A-Za-z0-9]+)_"
    r"(?P<ses>ses-[A-Za-z0-9]+)_"
    r"task-(?P<task>[A-Za-z0-9]+)_"
    r"run-(?P<run>\d+)_"
    r"(?:space-(?P<space>[A-Za-z0-9]+)_"
    r"(?:res-(?P<res>[A-Za-z0-9]+)_)?)?"
    r"desc-preproc_bold\.nii\.gz$"
)


@dataclass(frozen=True, order=True)
class SpaceKey:
    """One (space, res) combination — one movie's worth of frames."""
    space: str            # "T1w", "MNI152NLin2009cAsym", or "" for native
    res: str = ""         # "1", "2", or "" if not present in filename

    @property
    def label(self) -> str:
        if not self.space:
            return "native"
        if self.res:
            return f"{self.space} (res-{self.res})"
        return self.space

    @property
    def slug(self) -> str:
        """Used in output filename and manifest group name."""
        if not self.space:
            return "native"
        if self.res:
            return f"space-{self.space}_res-{self.res}"
        return f"space-{self.space}"


@dataclass
class MovieResult:
    space_label: str
    path: Path | None
    error: str | None


@dataclass
class _Frame:
    path: Path
    ses: str
    task: str
    run: int

    @property
    def ses_num(self) -> int:
        m = re.search(r"\d+", self.ses)
        return int(m.group()) if m else 0

    @property
    def sort_key(self) -> int:
        return self.ses_num * 1000 + self.run

    @property
    def label(self) -> str:
        return f"{self.ses} task-{self.task} run-{self.run}"


def _discover_by_space(
    fmriprep_dir: Path, subject: str, *, include_native: bool
) -> dict[SpaceKey, list[_Frame]]:
    """Find preproc BOLDs for one subject, grouped by SpaceKey."""
    groups: dict[SpaceKey, list[_Frame]] = {}
    sub_dir = fmriprep_dir / subject
    if not sub_dir.is_dir():
        return groups
    for path in sub_dir.glob("ses-*/func/*_desc-preproc_bold.nii.gz"):
        m = _PREPROC_RE.match(path.name)
        if not m:
            continue
        space = m.group("space") or ""
        if not space and not include_native:
            continue
        key = SpaceKey(space=space, res=m.group("res") or "")
        frame = _Frame(
            path=path,
            ses=m.group("ses"),
            task=m.group("task"),
            run=int(m.group("run")),
        )
        groups.setdefault(key, []).append(frame)
    for frames in groups.values():
        frames.sort(key=lambda f: f.sort_key)
    return groups


def _write_manifest(frames: list[_Frame], group: str, manifest: Path) -> None:
    with manifest.open("w", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["path", "label", "group", "sort_key"])
        for fr in frames:
            writer.writerow([str(fr.path), fr.label, group, fr.sort_key])


def _run_brm_for_group(
    output_movies_dir: Path,
    subject: str,
    space: SpaceKey,
    frames: list[_Frame],
) -> MovieResult:
    """Render one movie for a single (subject, space) group via brm."""
    group_name = f"{subject}_{space.slug}"
    expected_path = output_movies_dir / f"{group_name}.mp4"

    with tempfile.NamedTemporaryFile(
        "w", suffix=".tsv", prefix=f"brm_{group_name}_", delete=False
    ) as tf:
        manifest_path = Path(tf.name)
    try:
        _write_manifest(frames, group=group_name, manifest=manifest_path)
        cmd = [
            _BRM_CMD, "list", str(manifest_path),
            "--out", str(output_movies_dir),
            "--renderer", "mosaic",
            "--no-cache",
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            return MovieResult(space.label, None, "brm CLI not found on PATH")
    finally:
        manifest_path.unlink(missing_ok=True)

    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = " | ".join(msg[-3:]) if msg else f"exit {proc.returncode}"
        return MovieResult(space.label, None, f"brm failed: {tail}")

    if not expected_path.is_file():
        return MovieResult(
            space.label, None, "brm exited 0 but produced no output file"
        )

    return MovieResult(space.label, expected_path, None)


def render_reliability_movies(
    fmriprep_dir: Path,
    output_movies_dir: Path,
    subjects: list[str],
    *,
    include_native: bool = False,
) -> dict[str, list[MovieResult]]:
    """Render one movie per (subject, space) combination.

    Args:
        fmriprep_dir: fmriprep derivatives directory (input).
        output_movies_dir: where mp4 files are written.
        subjects: list of subject IDs (e.g., ["sub-s03"]) to render.
        include_native: also render the no-`_space-` (native) variant.

    Returns:
        Dict mapping subject ID -> list of MovieResult, one per space found.
        Ordered by SpaceKey (alphabetical by space then res).
    """
    output_movies_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, list[MovieResult]] = {}
    for sub in subjects:
        try:
            groups = _discover_by_space(fmriprep_dir, sub, include_native=include_native)
        except Exception as exc:  # noqa: BLE001
            log.exception("brm discovery raised for %s", sub)
            results[sub] = [MovieResult("(discovery)", None, str(exc))]
            continue
        if not groups:
            results[sub] = [MovieResult("(none)", None, "no preproc BOLDs found")]
            continue
        per_subject: list[MovieResult] = []
        for space in sorted(groups):
            try:
                per_subject.append(
                    _run_brm_for_group(output_movies_dir, sub, space, groups[space])
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("brm wrapper raised for %s %s", sub, space.label)
                per_subject.append(MovieResult(space.label, None, str(exc)))
        results[sub] = per_subject
    return results
