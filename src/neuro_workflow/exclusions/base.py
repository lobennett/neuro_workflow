from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
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


def load_dataset_subjects(dataset_config: dict) -> set[str] | None:
    """Return the dataset's subject IDs (with `sub-` prefix) from `subjects_file`,
    or None if the config has no resolvable subjects file. Bare IDs in the file
    (e.g. `s10`) are normalised to `sub-s10` to match BIDS-prefixed entity IDs.
    """
    raw = dataset_config.get("subjects_file")
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        # subjects_file is stored relative to the cwd at registration time.
        # Try cwd first; the user runs CLI from the repo root.
        path = Path.cwd() / raw
    if not path.is_file():
        return None
    subjects: set[str] = set()
    for line in path.read_text().splitlines():
        sid = line.strip()
        if not sid or sid.startswith("#"):
            continue
        subjects.add(sid if sid.startswith("sub-") else f"sub-{sid}")
    return subjects or None
