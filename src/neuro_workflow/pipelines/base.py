from __future__ import annotations

import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Protocol, runtime_checkable

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

# Registry mapping pipeline name -> pipeline instance
_REGISTRY: dict[str, Pipeline] = {}


@runtime_checkable
class Pipeline(Protocol):
    name: str
    docker_uri: str | None
    template_name: str
    default_resources: dict

    def add_cli_args(self, parser: ArgumentParser) -> None: ...
    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict: ...


def register(pipeline: Pipeline) -> None:
    _REGISTRY[pipeline.name] = pipeline


def get_pipeline(name: str) -> Pipeline | None:
    return _REGISTRY.get(name)


def list_pipelines() -> dict[str, Pipeline]:
    return dict(_REGISTRY)


def resolve_pipeline_subjects(dataset_name: str, dataset_config: dict) -> list[str]:
    """Resolve a pipeline's subject list (bare IDs, e.g. ``s10``), fail-loud.

    Precedence:

    1. If ``dataset_name`` is a canonical sample in ``pipeline_config.json``
       (``discovery`` / ``validation`` / ``excluded``), return its committed
       roster. This is the source of truth and works WITHOUT the removed
       ``subjects_*.txt`` files.
    2. Otherwise (an ad-hoc operational dataset like ``discovery_smoke``),
       fall back to the registered ``subjects_file`` if it exists.

    Fail-loud: if neither resolves, raise ``ValueError``. There is NO silent
    empty/None path — a pipeline that can't enumerate subjects must surface it
    rather than render an empty SLURM array.
    """
    from neuro_workflow.core.config import is_known_sample, resolve_dataset_subjects

    if is_known_sample(dataset_name):
        return resolve_dataset_subjects(dataset_name)

    raw = dataset_config.get("subjects_file")
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / raw
        if path.is_file():
            return [
                line.strip()
                for line in path.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        missing = f" (registered subjects_file does not exist: {path})"
    else:
        missing = " (no subjects_file registered)"

    raise ValueError(
        f"cannot resolve subjects for dataset '{dataset_name}': it is not a "
        f"canonical sample in pipeline_config.json and{missing}."
    )


def write_subjects_file(subjects: list[str], dest_dir, filename: str = "subjects.txt"):
    """Write ``subjects`` (one bare ID per line) into ``dest_dir`` and return the path.

    Pipelines call this at build time so the rendered sbatch references a real
    file path, replacing the dependency on the now-removed registered
    ``subjects_*.txt``. ``dest_dir`` is created if needed.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / filename
    out.write_text("\n".join(subjects) + "\n")
    return out


def build_mail_line(dataset_config: dict) -> str:
    """Build SBATCH mail directives from dataset config."""
    if dataset_config.get("mail_user"):
        return f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
    return ""


def resolve_resources(args, defaults: dict) -> dict:
    """Resolve resource values: use args override if not None, else default."""
    return {
        key: getattr(args, key, None) if getattr(args, key, None) is not None else val
        for key, val in defaults.items()
    }


class ContainerPipeline:
    """Base for container (SIF/Docker) pipelines.

    Provides the scaffolding shared by the container-backed pipelines
    (fmriprep, freesurfer, qsiprep, happy, fsqc): a ``--version`` gate,
    resource resolution, image-path / log-dir construction, and the common
    subset of returned context keys.

    Subclasses declare ``name``, ``docker_uri``, ``template_name`` and
    ``default_resources`` and implement ``add_cli_args`` and ``build_context``,
    composing only the helpers that genuinely apply to them.
    """

    name: str
    docker_uri: str | None
    template_name: str
    default_resources: dict

    def _require_version(self, args: Namespace) -> None:
        """Exit(1) if ``--version`` is missing (version-keyed pipelines only)."""
        if not getattr(args, "version", None):
            print(f"Error: --version is required for {self.name} pipeline", file=sys.stderr)
            sys.exit(1)

    def _resolve(self, args: Namespace) -> dict:
        """Resolve resources against this pipeline's ``default_resources``."""
        return resolve_resources(args, self.default_resources)

    def _image_path(self, dataset_config: dict, version: str) -> str:
        """``<image_dir>/<name>_<version>.sif`` (the common .sif convention)."""
        return str(Path(dataset_config["image_dir"]) / f"{self.name}_{version}.sif")

    def _log_dir(self, dataset_config: dict, version: str) -> str:
        """``<bids_dir>/derivatives/<name>_<version>/logs`` (the common layout)."""
        return f"{dataset_config['bids_dir']}/derivatives/{self.name}_{version}/logs"

    def _base_context(
        self,
        dataset_name: str,
        dataset_config: dict,
        resources: dict,
        log_dir: str,
        image_path: str,
    ) -> dict:
        """The context keys present in every container pipeline's output."""
        return {
            "dataset_name": dataset_name,
            "time": resources["time"],
            "nthreads": resources["nthreads"],
            "mem_per_cpu_gb": resources["mem_per_cpu_gb"],
            "partition": dataset_config["partition"],
            "log_dir": log_dir,
            "mail_line": build_mail_line(dataset_config),
            "image_path": image_path,
        }


class LocalAnalysisPipeline:
    """Base for the local (non-container) analysis pipelines.

    Provides the scaffolding shared by ``lev1`` and ``lev2``: resource
    resolution against ``default_resources``, the
    ``<results_dir>/logs`` layout (created on disk, with a per-pipeline
    list-file written into it), the repo-root path, and the common subset
    of returned context keys (``dataset_name``, ``nthreads``, ``mem_gb``,
    ``time``, ``partition``, ``log_dir``, ``mail_line``, ``results_dir``,
    ``neuro_workflow_dir``).

    Subclasses declare ``name``, ``docker_uri`` (``None`` here),
    ``template_name`` and ``default_resources`` and implement
    ``add_cli_args`` and ``build_context``, composing these helpers and
    adding their own keys (lev1: tasks/fmriprep-dir/exclusions/space/...,
    lev2: lev1-dirs/contrasts/mask-threshold/...).
    """

    name: str
    docker_uri: str | None
    template_name: str
    default_resources: dict

    def _resolve(self, args: Namespace) -> dict:
        """Resolve resources against this pipeline's ``default_resources``."""
        return resolve_resources(args, self.default_resources)

    def _make_log_dir(self, results_dir: Path) -> Path:
        """``<results_dir>/logs``, created on disk (``parents=True``)."""
        log_dir = results_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def _write_list_file(self, log_dir: Path, filename: str, lines: list[str]) -> Path:
        """Write ``<log_dir>/<filename>`` with one entry per line (trailing newline)."""
        list_file = log_dir / filename
        list_file.write_text("\n".join(lines) + "\n")
        return list_file

    @staticmethod
    def _neuro_workflow_dir() -> str:
        """Absolute path to the repo root (``base.py`` is at ``pipelines/``)."""
        return str(Path(__file__).resolve().parents[3])

    def _base_context(
        self,
        dataset_name: str,
        dataset_config: dict,
        resources: dict,
        log_dir: Path,
        results_dir: Path,
    ) -> dict:
        """The context keys present in every local-analysis pipeline's output."""
        return {
            "dataset_name": dataset_name,
            "nthreads": resources["nthreads"],
            "mem_gb": resources["mem_gb"],
            "time": resources["time"],
            "partition": dataset_config["partition"],
            "log_dir": str(log_dir),
            "mail_line": build_mail_line(dataset_config),
            "results_dir": str(results_dir),
            "neuro_workflow_dir": self._neuro_workflow_dir(),
        }
