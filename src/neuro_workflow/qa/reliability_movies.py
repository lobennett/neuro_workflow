"""Wrapper around bold-reliability-movies for cohort QA report integration.

Catches per-subject failures so one bad subject doesn't abort the cohort.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

try:
    from bold_reliability_movies import FmriprepFrameSource, make_videos
    from bold_reliability_movies.renderers import get_renderer
except ImportError:  # pragma: no cover
    FmriprepFrameSource = None  # type: ignore[assignment,misc]
    make_videos = None  # type: ignore[assignment]
    get_renderer = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


@dataclass
class MovieResult:
    path: Path | None
    error: str | None


def render_reliability_movies(
    fmriprep_dir: Path,
    output_movies_dir: Path,
    subjects: list[str],
) -> dict[str, MovieResult]:
    """Render one reliability movie per requested subject.

    Args:
        fmriprep_dir: fmriprep derivatives directory (input).
        output_movies_dir: where mp4 files are written.
        subjects: list of subject IDs (e.g., ["sub-s03"]) to render. Other
            subjects in the derivatives dir are ignored.

    Returns:
        Dict mapping subject ID -> MovieResult. On error, MovieResult.path
        is None and .error contains a short message.
    """
    output_movies_dir.mkdir(parents=True, exist_ok=True)
    requested = set(subjects)

    source = FmriprepFrameSource(fmriprep_dir, group_by="subject")
    all_groups = source.discover()
    groups = [g for g in all_groups if g.name in requested]

    results: dict[str, MovieResult] = {s: MovieResult(None, "not discovered by brm") for s in subjects}

    renderer = get_renderer("mosaic")

    for group in groups:
        sub_id = group.name
        try:
            summaries = make_videos(
                groups=[group],
                renderer=renderer,
                out_dir=output_movies_dir,
                fps=2,
                codec="libx264",
            )
            if summaries:
                s = summaries[0]
                err = getattr(s, "error", None)
                results[sub_id] = MovieResult(
                    path=Path(s.path) if not err and getattr(s, "path", None) else None,
                    error=str(err) if err else None,
                )
            else:
                results[sub_id] = MovieResult(None, "brm returned no summaries")
        except Exception as exc:  # noqa: BLE001
            log.exception("brm make_videos failed for %s", sub_id)
            results[sub_id] = MovieResult(None, str(exc))

    return results
