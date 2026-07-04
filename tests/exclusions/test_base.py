from neuro_workflow.exclusions.base import (
    get_generator,
    list_generators,
    register_generator,
)


class FakeGenerator:
    name = "fake"
    description = "A fake generator for testing"

    def add_cli_args(self, parser):
        pass

    def generate(self, dataset_name, dataset_config, args):
        return []


def test_register_and_get():
    gen = FakeGenerator()
    register_generator(gen)
    assert get_generator("fake") is gen


def test_get_unknown_returns_none():
    assert get_generator("nonexistent-gen") is None


def test_list_generators():
    gen = FakeGenerator()
    register_generator(gen)
    generators = list_generators()
    assert "fake" in generators
