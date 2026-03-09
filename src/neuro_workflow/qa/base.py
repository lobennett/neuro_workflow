from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import Protocol, runtime_checkable

_REGISTRY: dict[str, QaCommand] = {}


@runtime_checkable
class QaCommand(Protocol):
    name: str
    description: str

    def add_cli_args(self, parser: ArgumentParser) -> None: ...
    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None: ...


def register_qa(command: QaCommand) -> None:
    _REGISTRY[command.name] = command


def get_qa_command(name: str) -> QaCommand | None:
    return _REGISTRY.get(name)


def list_qa_commands() -> dict[str, QaCommand]:
    return dict(_REGISTRY)
