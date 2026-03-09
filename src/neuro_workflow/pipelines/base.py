from __future__ import annotations

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
