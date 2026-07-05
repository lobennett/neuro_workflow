from neuro_workflow.qa.base import get_qa_command, list_qa_commands, register_qa


class FakeQa:
    name = "fake-qa"
    description = "A fake QA command for testing"

    def add_cli_args(self, parser):
        parser.add_argument("--foo", default="bar")

    def run(self, dataset_name, dataset_config, args):
        pass


def test_register_and_get():
    cmd = FakeQa()
    register_qa(cmd)
    assert get_qa_command("fake-qa") is cmd


def test_get_unknown_returns_none():
    assert get_qa_command("nonexistent-qa") is None


def test_list_qa_commands():
    cmd = FakeQa()
    register_qa(cmd)
    commands = list_qa_commands()
    assert "fake-qa" in commands
    assert commands["fake-qa"] is cmd
