"""A fake Flywheel client that lets ``bidsify`` run without the Flywheel service.

This closes the **Flywheel -> BIDS** boundary of the end-to-end pipeline
simulation. Where :mod:`neuro_workflow.testing.cohort` manufactures a synthetic
*BIDS* dataset (the input to the exclusions/lev1 simulation), this module
manufactures the stage UPSTREAM of it: a fake Flywheel project whose
acquisitions+files the *production* :func:`neuro_workflow.bidsify.run.run_bidsify`
downloads and renames into a real BIDS tree — with NO Flywheel SDK service, no
network, and no DICOM-conversion tooling.

Why this works: ``bidsify/run.py`` downloads NIfTIs *directly* (it does NOT run
dcm2niix / convert DICOM). It selects ``acq.files``, calls
``download_and_place(acq, file, dest)`` (which calls
``acq.download_file(name, dest)``), renames the result to a BIDS path, and
patches the JSON sidecars. So a fake client that serves synthetic acquisitions
whose ``download_file`` writes synthetic bytes (a tiny valid NIfTI for
``.nii.gz``; a minimal BIDS JSON sidecar; bval/bvec for dwi) is enough for the
real pipeline to produce a genuine BIDS dataset.

The fake objects implement EXACTLY the SDK surface the production code touches
(and nothing more):

================  ============================================================
Object            Attributes / methods bidsify uses
================  ============================================================
``flywheel``      ``Client()`` (the consumer monkeypatches this to return a
                  :class:`FakeFlywheelClient`)
client            ``.projects.find_first('label="..."')``
``Project``       ``.label``, ``.subjects()``
``Subject``       ``.label``, ``.sessions()``
``Session``       ``.label``, ``.timestamp``, ``.acquisitions()``,
                  ``.reload()``, ``.analyses``
``Acquisition``   ``.label``, ``.timestamp``, ``.id``, ``.reload()``,
                  ``.files``, ``.download_file(name, dest)``
``File``          ``.name``, ``.type``, ``.size``, ``.created`` (datetime)
``Analysis``      ``.gear_info``, ``.files``, ``.reload()``, ``.inputs``,
                  ``.created``, ``.download_file(name, dest)``
``AnalysisInput`` ``._parents`` (dict with ``"acquisition"`` key)
================  ============================================================

See ``flywheel_query.py`` (client/project/subject/session query + ordering),
``file_selector.py`` (which file ``.name`` / ``.type`` patterns get selected),
``bids_writer.download_and_place`` (how a downloaded file is written; in
particular it reads ``file.size`` and ``file.created.isoformat()``), and
``physio_query.py`` (the gephysio analysis surface).

Dependency-light: numpy / nibabel only (nibabel via the reused
:mod:`neuro_workflow.testing.synthetic` writers). All randomness is explicitly
seeded so output is deterministic. This is import-only test support; nothing in
production imports from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

__all__ = [
    "FakeFile",
    "FakeAcquisition",
    "FakeAnalysisInput",
    "FakeAnalysis",
    "FakeSession",
    "FakeSubject",
    "FakeProjects",
    "FakeProject",
    "FakeFlywheelClient",
    "FlywheelAcqSpec",
    "FlywheelSessionSpec",
    "FlywheelSubjectSpec",
    "FlywheelCohortSpec",
    "make_fake_flywheel",
]


# Base time for synthesizing ``created`` timestamps when a spec omits them.
_EPOCH = datetime(2021, 1, 1, tzinfo=UTC)


def _parse_ts(ts: Any) -> datetime | None:
    """Coerce a spec timestamp to a timezone-aware ``datetime`` (or None).

    Accepts an ISO-8601 string (the shape stored in Flywheel) or an existing
    ``datetime``. ``run.py`` sorts acquisitions/sessions by these and calls
    ``.isoformat()`` on session timestamps, so a real ``datetime`` is required.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    return datetime.fromisoformat(ts)


# --------------------------------------------------------------------------- #
# Synthetic file-content writers (what `download_file` produces).
# --------------------------------------------------------------------------- #
def _write_nifti(dest: Path, *, n_trs: int, n_voxels: int, seed: int) -> None:
    """Write a tiny, genuinely loadable 4D BOLD NIfTI (reuses synthetic.as_4d_nifti)."""
    import nibabel as nib
    import numpy as np

    from neuro_workflow.testing.synthetic import as_4d_nifti

    rng = np.random.default_rng(seed)
    ts = rng.normal(0.0, 1.0, size=max(n_trs, 1))
    img = as_4d_nifti(ts, n_voxels=n_voxels)
    nib.save(img, str(dest))


def _write_anat_nifti(dest: Path, *, seed: int) -> None:
    """Write a tiny loadable 3D anatomical NIfTI."""
    import nibabel as nib
    import numpy as np

    rng = np.random.default_rng(seed)
    data = rng.normal(0.0, 1.0, size=(6, 6, 6)).astype("float32")
    nib.save(nib.Nifti1Image(data, affine=np.eye(4)), str(dest))


def _write_json_sidecar(dest: Path, fields: dict[str, Any]) -> None:
    """Write a minimal BIDS JSON sidecar carrying the fields patching expects."""
    import json

    dest.write_text(json.dumps(fields, indent=2))


def _write_bval(dest: Path, *, n_dirs: int) -> None:
    """Write a minimal FSL bval row (a b0 plus ``n_dirs`` weighted volumes)."""
    vals = ["0"] + ["1000"] * n_dirs
    dest.write_text(" ".join(vals) + "\n")


def _write_bvec(dest: Path, *, n_dirs: int, seed: int) -> None:
    """Write a minimal FSL bvec (3 rows of unit-ish gradient directions)."""
    import numpy as np

    rng = np.random.default_rng(seed)
    n = n_dirs + 1
    g = rng.normal(0.0, 1.0, size=(3, n))
    g[:, 0] = 0.0  # b0 has no direction
    lines = [" ".join(f"{v:.6f}" for v in row) for row in g]
    dest.write_text("\n".join(lines) + "\n")


def _write_physio_csv(dest: Path, *, kind: str, n: int) -> None:
    """Write a minimal gephysio FltData / FltTrig CSV (no header).

    ``FltData`` rows are ``timestamp_ms,amplitude``; ``FltTrig`` rows are a lone
    ``timestamp_ms`` — the exact shapes ``physio.parse_flt_data`` /
    ``parse_flt_trig`` read.
    """
    import numpy as np

    rng = np.random.default_rng(0)
    if kind == "data":
        amps = rng.uniform(0.0, 1.0, size=n)
        lines = [f"{i * 10},{a:.4f}" for i, a in enumerate(amps)]
    else:  # trig
        lines = [str(i * 100) for i in range(max(1, n // 10))]
    dest.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# Fake SDK objects.
# --------------------------------------------------------------------------- #
@dataclass
class FakeFile:
    """A fake Flywheel acquisition/analysis file.

    Attributes mirror the SDK surface bidsify reads: ``name`` (BIDS-renamed
    from), ``type`` (Flywheel file-type classification — ``"nifti"`` /
    ``"source code"`` for JSON / ``"bval"`` / ``"bvec"`` / etc.; consumed by
    ``file_selector``), ``size`` (int; recorded by ``download_and_place``),
    ``created`` (``datetime``; ``download_and_place`` calls ``.isoformat()`` and
    ``file_selector`` uses it as a max-by sort key).

    ``_content`` describes how :meth:`write_to` materializes the file's bytes.
    """

    name: str
    type: str
    size: int = 1024
    created: datetime | None = None
    # How to synthesize this file's content on download. Shape:
    #   {"kind": "nifti"|"anat"|"json"|"bval"|"bvec"|"physio",
    #    plus kind-specific keys}
    _content: dict[str, Any] = field(default_factory=dict)

    def write_to(self, dest: Path) -> None:
        """Materialize this file's synthetic content at ``dest``."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        c = self._content
        kind = c.get("kind")
        if kind == "nifti":
            _write_nifti(
                dest,
                n_trs=c.get("n_trs", 10),
                n_voxels=c.get("n_voxels", 4),
                seed=c.get("seed", 0),
            )
        elif kind == "anat":
            _write_anat_nifti(dest, seed=c.get("seed", 0))
        elif kind == "json":
            _write_json_sidecar(dest, dict(c.get("fields", {})))
        elif kind == "bval":
            _write_bval(dest, n_dirs=c.get("n_dirs", 6))
        elif kind == "bvec":
            _write_bvec(dest, n_dirs=c.get("n_dirs", 6), seed=c.get("seed", 0))
        elif kind == "physio":
            _write_physio_csv(dest, kind=c.get("physio_kind", "data"), n=c.get("n", 100))
        else:  # pragma: no cover - defensive
            raise ValueError(f"unknown fake-file content kind: {kind!r}")


@dataclass
class FakeAcquisition:
    """A fake Flywheel acquisition.

    Surface used by bidsify: ``label`` (mapped via ``map_acquisition``),
    ``timestamp`` (str/datetime; ``run.py`` sorts on it for run-numbering),
    ``id`` (used as the physio acq-map key), ``reload()`` (returns self),
    ``files`` (list of :class:`FakeFile`), ``download_file(name, dest)``.
    """

    label: str
    timestamp: str | None = None
    id: str = ""
    files: list[FakeFile] = field(default_factory=list)

    def reload(self) -> FakeAcquisition:
        return self

    def download_file(self, name: str, dest: str) -> None:
        """Write the named file's synthetic content to ``dest`` (SDK download)."""
        for f in self.files:
            if f.name == name:
                f.write_to(Path(dest))
                return
        raise FileNotFoundError(f"acquisition {self.label!r} has no file named {name!r}")


@dataclass
class FakeAnalysisInput:
    """A fake analysis input record. Only ``_parents`` is read (physio_query)."""

    _parents: dict[str, Any] = field(default_factory=dict)


@dataclass
class FakeAnalysis:
    """A fake gephysio analysis.

    Surface used: ``gear_info`` (dict; ``.get("name")``), ``files`` (list),
    ``reload()``, ``inputs`` (list of :class:`FakeAnalysisInput` whose
    ``_parents["acquisition"]`` ties it to a source acquisition), ``created``
    (datetime), ``download_file(name, dest)``.
    """

    gear_info: dict[str, Any] = field(default_factory=dict)
    files: list[FakeFile] = field(default_factory=list)
    inputs: list[FakeAnalysisInput] = field(default_factory=list)
    created: datetime | None = None

    def reload(self) -> FakeAnalysis:
        return self

    def download_file(self, name: str, dest: str) -> None:
        for f in self.files:
            if f.name == name:
                f.write_to(Path(dest))
                return
        raise FileNotFoundError(f"analysis has no file named {name!r}")


@dataclass
class FakeSession:
    """A fake Flywheel session.

    Surface used: ``label``, ``timestamp`` (datetime; ``run.py`` calls
    ``.isoformat()`` and sorts on it), ``acquisitions()``, ``reload()``,
    ``analyses`` (list; ``physio_query`` reads it).
    """

    label: str
    timestamp: datetime | None = None
    _acquisitions: list[FakeAcquisition] = field(default_factory=list)
    analyses: list[FakeAnalysis] = field(default_factory=list)

    def acquisitions(self) -> list[FakeAcquisition]:
        return list(self._acquisitions)

    def reload(self) -> FakeSession:
        return self


@dataclass
class FakeSubject:
    """A fake Flywheel subject. Surface used: ``label``, ``sessions()``."""

    label: str
    _sessions: list[FakeSession] = field(default_factory=list)

    def sessions(self) -> list[FakeSession]:
        return list(self._sessions)


class FakeProject:
    """A fake Flywheel project. Surface used: ``label``, ``subjects()``."""

    def __init__(self, label: str, subjects: list[FakeSubject]) -> None:
        self.label = label
        self._subjects = subjects

    def subjects(self) -> list[FakeSubject]:
        return list(self._subjects)


class FakeProjects:
    """The fake ``client.projects`` finder. Surface used: ``find_first(query)``."""

    def __init__(self, projects: list[FakeProject]) -> None:
        self._projects = projects

    def find_first(self, query: str) -> FakeProject | None:
        """Resolve a ``label="..."`` query to a project (or None).

        Mirrors ``flywheel_query.query_project_subjects`` which calls
        ``projects.find_first(f'label="{project_label}"')``.
        """
        label = _extract_label(query)
        for p in self._projects:
            if p.label == label:
                return p
        return None


def _extract_label(query: str) -> str | None:
    """Pull the value out of a ``label="<value>"`` Flywheel query string."""
    marker = 'label="'
    if marker in query:
        rest = query.split(marker, 1)[1]
        return rest.split('"', 1)[0]
    return query


class FakeFlywheelClient:
    """Stand-in for ``flywheel.Client()``.

    Only ``.projects`` (a :class:`FakeProjects`) is exposed — the single
    attribute ``flywheel_query`` reaches through. Construct one via
    :func:`make_fake_flywheel`.
    """

    def __init__(self, projects: list[FakeProject]) -> None:
        self.projects = FakeProjects(projects)


# --------------------------------------------------------------------------- #
# Cohort spec describing the Flywheel SIDE of a cohort.
# --------------------------------------------------------------------------- #
@dataclass
class FlywheelAcqSpec:
    """One acquisition to manufacture on the fake Flywheel side.

    Args:
        label: Flywheel acquisition label. To be picked up by bidsify it should
            be a key in ``bidsify/config.py``'s ``ACQUISITION_MAP`` (e.g.
            ``"task-flanker_bold"``, ``"T1w MPRAGE PROMO"``, ``"fmap-fieldmap"``,
            ``"DTI_pe0_g105"``). Unknown labels are served too (so a test can
            prove run.py skips them) but yield no BIDS files.
        timestamp: ISO-8601 string (or datetime). ``run.py`` sorts acquisitions
            by this for duplicate-task run-numbering.
        echoes: For a func acquisition, the number of multi-echo BOLD files to
            produce (each as ``*_eN.nii.gz`` + ``*_eN.json``). ``0`` produces a
            BOLD acquisition with NO echo files (a protocol-mismatch case
            bidsify handles by skipping). Ignored for non-func modalities.
        n_trs: Timepoints in each synthesized BOLD NIfTI.
        with_physio: If True (func only), attach a gephysio analysis to the
            session for this acquisition so the physio branch is exercised.
        outcome: For a func acquisition, the intended end-to-end exclusion
            outcome the full-chain driver
            (:func:`neuro_workflow.testing.simulate.simulate_full_pipeline`)
            plants for the BIDS scan this acquisition becomes — one of
            ``"keep"`` / ``"exclude:behavioral"`` / ``"exclude:motion"`` /
            ``"exclude:collection"`` (the
            :data:`neuro_workflow.testing.cohort.VALID_OUTCOMES` vocabulary).
            Ignored by ``make_fake_flywheel`` itself (it only affects the
            downstream behavioral CSV / confounds / collection-glob the driver
            writes) and for non-func modalities.
        plant_contrast: For a ``keep`` func acquisition, whether the driver
            plants the known incongruent-congruent contrast into this scan's
            fMRIPrep BOLD (the lev1 recovery scan). Exactly one acquisition in a
            full-chain spec should set this.
    """

    label: str
    timestamp: str | None = None
    echoes: int = 3
    n_trs: int = 10
    with_physio: bool = False
    outcome: str = "keep"
    plant_contrast: bool = False


@dataclass
class FlywheelSessionSpec:
    """One session: a label, timestamp, and its acquisitions."""

    label: str
    timestamp: str | None = None
    acquisitions: list[FlywheelAcqSpec] = field(default_factory=list)


@dataclass
class FlywheelSubjectSpec:
    """One Flywheel subject (canonical OR an alias label)."""

    label: str
    sessions: list[FlywheelSessionSpec] = field(default_factory=list)


@dataclass
class FlywheelCohortSpec:
    """The whole Flywheel-side cohort: a project label + its subjects.

    This mirrors :class:`neuro_workflow.testing.cohort.CohortSpec` in spirit (a
    nested subjects -> sessions -> acquisitions tree) but describes the
    *Flywheel* side (acquisition labels + echo counts) rather than the BIDS
    side. The two stitch: a func acquisition labeled e.g. ``task-flanker_bold``
    here produces, after ``run_bidsify``, the
    ``sub-X_ses-Y_task-flanker_run-N_echo-M_bold.*`` files that the cohort/
    simulate downstream stages discover.
    """

    project: str = "r01network"
    subjects: list[FlywheelSubjectSpec] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Builder: spec -> fake object tree.
# --------------------------------------------------------------------------- #
# Default BOLD sidecar fields. ``run.py`` patches ``TaskName`` (and later
# ``B0FieldSource`` when a fieldmap is present); fmriprep/lev1 downstream read
# ``RepetitionTime``. We seed a minimal-but-realistic sidecar so the patched
# result is a valid BIDS JSON.
_BOLD_SIDECAR = {
    "RepetitionTime": 1.49,
    "EchoTime": 0.03,
    "Manufacturer": "GE",
    "MagneticFieldStrength": 3,
}
_ANAT_SIDECAR = {
    "RepetitionTime": 2.3,
    "Manufacturer": "GE",
    "MagneticFieldStrength": 3,
}
_FMAP_SIDECAR = {
    "Units": "Hz",
    "Manufacturer": "GE",
    "MagneticFieldStrength": 3,
}
_DWI_SIDECAR = {
    "RepetitionTime": 8.0,
    "Manufacturer": "GE",
    "MagneticFieldStrength": 3,
}


def _bold_files(acq_label: str, echoes: int, n_trs: int, seed: int) -> list[FakeFile]:
    """Build the multi-echo BOLD file list (``*_eN.nii.gz`` + ``*_eN.json``).

    Filenames carry the ``_eN`` echo marker that
    ``file_selector._echo_number`` parses. Each echo's NIfTI gets a distinct
    seed so the echoes carry distinct signal.
    """
    files: list[FakeFile] = []
    for echo in range(1, echoes + 1):
        base = f"{acq_label}_e{echo}"
        files.append(
            FakeFile(
                name=f"{base}.nii.gz",
                type="nifti",
                size=2048 + echo,
                created=_EPOCH + timedelta(seconds=echo),
                _content={"kind": "nifti", "n_trs": n_trs, "seed": seed + echo},
            )
        )
        files.append(
            FakeFile(
                name=f"{base}.json",
                type="source code",
                size=256 + echo,
                created=_EPOCH + timedelta(seconds=echo),
                _content={"kind": "json", "fields": dict(_BOLD_SIDECAR)},
            )
        )
    return files


def _anat_files(acq_label: str, seed: int) -> list[FakeFile]:
    base = acq_label.replace(" ", "_")
    return [
        FakeFile(
            name=f"{base}.nii.gz",
            type="nifti",
            size=4096,
            created=_EPOCH,
            _content={"kind": "anat", "seed": seed},
        ),
        FakeFile(
            name=f"{base}.json",
            type="source code",
            size=256,
            created=_EPOCH,
            _content={"kind": "json", "fields": dict(_ANAT_SIDECAR)},
        ),
    ]


def _fmap_files(seed: int) -> list[FakeFile]:
    """Fieldmap + magnitude pair. ``file_selector`` keys the fieldmap on the
    ``_fieldmap`` substring in the NIfTI/JSON name; the other NIfTI is treated
    as magnitude."""
    return [
        FakeFile(
            name="acq_fieldmap.nii.gz",
            type="nifti",
            size=4096,
            created=_EPOCH,
            _content={"kind": "anat", "seed": seed},
        ),
        FakeFile(
            name="acq_fieldmap.json",
            type="source code",
            size=256,
            created=_EPOCH,
            _content={"kind": "json", "fields": dict(_FMAP_SIDECAR)},
        ),
        FakeFile(
            name="acq_magnitude.nii.gz",
            type="nifti",
            size=4096,
            created=_EPOCH,
            _content={"kind": "anat", "seed": seed + 1},
        ),
    ]


def _dwi_files(acq_label: str, seed: int) -> list[FakeFile]:
    base = acq_label
    n_dirs = 6
    return [
        FakeFile(
            name=f"{base}.nii.gz",
            type="nifti",
            size=8192,
            created=_EPOCH,
            _content={"kind": "nifti", "n_trs": n_dirs + 1, "seed": seed},
        ),
        FakeFile(
            name=f"{base}.json",
            type="source code",
            size=256,
            created=_EPOCH,
            _content={"kind": "json", "fields": dict(_DWI_SIDECAR)},
        ),
        FakeFile(
            name=f"{base}.bval",
            type="bval",
            size=64,
            created=_EPOCH,
            _content={"kind": "bval", "n_dirs": n_dirs},
        ),
        FakeFile(
            name=f"{base}.bvec",
            type="bvec",
            size=128,
            created=_EPOCH,
            _content={"kind": "bvec", "n_dirs": n_dirs, "seed": seed},
        ),
    ]


# Acquisition-label classification, kept in lock-step with bidsify/config.py's
# ACQUISITION_MAP modality. We import the production mapper so the fake never
# drifts from the real label set.
def _modality_for(label: str) -> str | None:
    from neuro_workflow.bidsify.config import map_acquisition

    mapping = map_acquisition(label)
    return mapping["modality"] if mapping else None


def _files_for_acquisition(spec: FlywheelAcqSpec, seed: int) -> list[FakeFile]:
    """Build the synthetic file list appropriate to this acquisition's modality."""
    modality = _modality_for(spec.label)
    if modality == "func":
        return _bold_files(spec.label, spec.echoes, spec.n_trs, seed)
    if modality == "anat":
        return _anat_files(spec.label, seed)
    if modality == "fmap":
        return _fmap_files(seed)
    if modality == "dwi":
        return _dwi_files(spec.label, seed)
    # Unknown / skip label: serve no files (run.py logs & skips the acquisition).
    return []


def make_fake_flywheel(spec: FlywheelCohortSpec) -> FakeFlywheelClient:
    """Turn a :class:`FlywheelCohortSpec` into a :class:`FakeFlywheelClient`.

    Builds the project -> subject -> session -> acquisition -> file tree the
    production ``run_bidsify`` walks. Acquisition files are synthesized per
    modality (multi-echo BOLD / T1w-T2w anat / fieldmap+magnitude / dwi with
    bval+bvec), each ``download_file`` writing a real loadable NIfTI / a JSON
    sidecar / bval / bvec.

    Alias + override semantics are NOT applied here — they live in the
    production ``flywheel_query.collect_subject_sessions`` (driven by
    ``config/pipeline_config.json``). This builder simply serves whatever FW
    subject labels the spec declares (e.g. both ``s19`` and its alias
    ``s19-2``), and ``run_bidsify`` merges/excludes them via the real config, so
    a test exercises the genuine alias/override code path.

    Args:
        spec: The Flywheel-side cohort description.

    Returns:
        A :class:`FakeFlywheelClient` whose single project is ``spec.project``.
    """
    acq_counter = 0
    seed_counter = 0
    subjects: list[FakeSubject] = []

    for subj_spec in spec.subjects:
        sessions: list[FakeSession] = []
        for sess_spec in subj_spec.sessions:
            acqs: list[FakeAcquisition] = []
            analyses: list[FakeAnalysis] = []
            for acq_spec in sess_spec.acquisitions:
                acq_counter += 1
                seed_counter += 1
                acq_id = f"acq_{acq_counter}"
                files = _files_for_acquisition(acq_spec, seed_counter)
                acq = FakeAcquisition(
                    label=acq_spec.label,
                    timestamp=acq_spec.timestamp,
                    id=acq_id,
                    files=files,
                )
                acqs.append(acq)

                if acq_spec.with_physio and _modality_for(acq_spec.label) == "func":
                    analyses.append(_make_physio_analysis(acq_id))

            sessions.append(
                FakeSession(
                    label=sess_spec.label,
                    timestamp=_parse_ts(sess_spec.timestamp),
                    _acquisitions=acqs,
                    analyses=analyses,
                )
            )
        subjects.append(FakeSubject(label=subj_spec.label, _sessions=sessions))

    project = FakeProject(spec.project, subjects)
    return FakeFlywheelClient([project])


def _make_physio_analysis(acq_id: str) -> FakeAnalysis:
    """Build a gephysio analysis tied to ``acq_id`` with cardiac+resp CSVs.

    Files match ``physio._CHANNEL_CONFIG`` names (``PPG_FltData.csv`` /
    ``PPG_FltTrig.csv`` / ``RESP_FltData.csv`` / ``RESP_FltTrig.csv``).
    ``gear_info["name"] == "gephysio"`` and a single input whose
    ``_parents["acquisition"]`` is ``acq_id`` are what ``physio_query`` keys on.
    """
    csv = lambda name, kind: FakeFile(  # noqa: E731
        name=name,
        type="tabular data",
        size=512,
        created=_EPOCH,
        _content={"kind": "physio", "physio_kind": kind, "n": 100},
    )
    return FakeAnalysis(
        gear_info={"name": "gephysio"},
        files=[
            csv("PPG_FltData.csv", "data"),
            csv("PPG_FltTrig.csv", "trig"),
            csv("RESP_FltData.csv", "data"),
            csv("RESP_FltTrig.csv", "trig"),
        ],
        inputs=[FakeAnalysisInput(_parents={"acquisition": acq_id})],
        created=_EPOCH,
    )
