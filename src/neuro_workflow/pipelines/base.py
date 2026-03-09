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
    docker_uri: str
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
