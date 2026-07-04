"""Jinja2 template rendering for QA HTML reports."""

from __future__ import annotations

from pathlib import Path

import jinja2

_TEMPLATE_DIR = Path(__file__).parent
_STATIC_DIR = _TEMPLATE_DIR / "static"

_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(_TEMPLATE_DIR),
    autoescape=jinja2.select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _read_static(name: str) -> str:
    return (_STATIC_DIR / name).read_text()


def render_cohort_html(*, rows, n_subjects, n_scans, n_flagged_scans, fmriprep_version) -> str:
    template = _env.get_template("cohort.html.j2")
    return template.render(
        rows=rows,
        n_subjects=n_subjects,
        n_scans=n_scans,
        n_flagged_scans=n_flagged_scans,
        fmriprep_version=fmriprep_version,
        datatables_css=_read_static("datatables.min.css"),
        datatables_js=_read_static("datatables.min.js"),
        style_css=_read_static("style.css"),
    )


def render_subject_html(
    *,
    subject,
    fs_metrics,
    scans,
    fmriprep_version,
    movies,
    decision_action,
    decision_reason,
    embed_svg,
) -> str:
    template = _env.get_template("subject.html.j2")
    return template.render(
        subject=subject,
        fs_metrics=fs_metrics,
        scans=scans,
        fmriprep_version=fmriprep_version,
        movies=movies,
        decision_action=decision_action,
        decision_reason=decision_reason,
        embed_svg=embed_svg,
        style_css=_read_static("style.css"),
    )
