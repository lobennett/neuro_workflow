import pytest
from pathlib import Path
from neuro_workflow.behavioral_archive.copy_utils import copy_file_with_retries


def test_copy_file_basic(tmp_path):
    """Copy file successfully."""
    src = tmp_path / "source.txt"
    src.write_text("content")
    dest = tmp_path / "dest" / "source.txt"

    copy_file_with_retries(src, dest, max_retries=1)

    assert dest.exists()
    assert dest.read_text() == "content"


def test_copy_file_creates_parents(tmp_path):
    """Create parent directories as needed."""
    src = tmp_path / "source.txt"
    src.write_text("content")
    dest = tmp_path / "a" / "b" / "c" / "source.txt"

    copy_file_with_retries(src, dest)

    assert dest.exists()
    assert dest.parent.exists()


def test_copy_file_skips_existing(tmp_path):
    """Skip if destination already exists."""
    src = tmp_path / "source.txt"
    src.write_text("new content")

    dest = tmp_path / "dest.txt"
    dest.write_text("old content")

    result = copy_file_with_retries(src, dest, skip_existing=True)

    assert result == "skipped"
    assert dest.read_text() == "old content"


def test_copy_file_raises_if_exists_and_no_skip(tmp_path):
    """Raise error if destination exists and skip=False."""
    src = tmp_path / "source.txt"
    src.write_text("new")

    dest = tmp_path / "dest.txt"
    dest.write_text("old")

    with pytest.raises(FileExistsError):
        copy_file_with_retries(src, dest, skip_existing=False)
