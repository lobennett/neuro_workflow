"""Behavioral exclusion generator (stub — future automated behavioral QA)."""
from __future__ import annotations

from argparse import ArgumentParser, Namespace

from neuro_workflow.exclusions.base import register_generator


class BehavioralGenerator:
    name = "behavioral"
    description = "Automated behavioral QA exclusions (not yet implemented)"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        pass

    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]:
        print(
            "behavioral generator not yet implemented — "
            "use 'neuro-run exclusions import' or overrides.json for manual behavioral exclusions"
        )
        return []


register_generator(BehavioralGenerator())
