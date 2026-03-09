from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import Protocol, runtime_checkable

_REGISTRY: dict[str, ExclusionGenerator] = {}


@runtime_checkable
class ExclusionGenerator(Protocol):
    name: str
    description: str

    def add_cli_args(self, parser: ArgumentParser) -> None: ...
    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]: ...


def register_generator(generator: ExclusionGenerator) -> None:
    _REGISTRY[generator.name] = generator


def get_generator(name: str) -> ExclusionGenerator | None:
    return _REGISTRY.get(name)


def list_generators() -> dict[str, ExclusionGenerator]:
    return dict(_REGISTRY)
