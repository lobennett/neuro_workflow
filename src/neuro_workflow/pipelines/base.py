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
