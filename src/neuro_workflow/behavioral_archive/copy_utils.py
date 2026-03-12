"""File copy utilities with retry logic and permission handling."""

import logging
import shutil
import time
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)


def copy_file_with_retries(
    src: Path | str,
    dest: Path | str,
    max_retries: int = 3,
    skip_existing: bool = True,
) -> Literal["success", "skipped"]:
    """
    Copy file from src to dest with retry logic.

    Args:
        src: Source file path
        dest: Destination file path
        max_retries: Number of retry attempts
        skip_existing: If True, skip if dest exists; if False, raise error

    Returns:
        "success" if copied, "skipped" if destination exists and skip_existing=True

    Raises:
        FileExistsError: If dest exists and skip_existing=False
        Exception: On final retry failure
    """
    src = Path(src)
    dest = Path(dest)

    # Check if destination exists
    if dest.exists():
        if skip_existing:
            logger.debug(f"Skipping existing file: {dest}")
            return "skipped"
        else:
            raise FileExistsError(f"Destination already exists: {dest}")

    # Create parent directory
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Attempt copy with retries
    for attempt in range(max_retries):
        try:
            shutil.copy2(src, dest)
            logger.debug(f"Copied {src} -> {dest}")
            return "success"
        except Exception as exc:
            # Clean up partial file
            if dest.exists():
                try:
                    dest.unlink()
                except Exception:
                    pass

            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(
                    f"Copy failed for {src} (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {wait}s: {exc}"
                )
                time.sleep(wait)
            else:
                logger.error(f"Copy failed for {src} after {max_retries} attempts: {exc}")
                raise

    return "success"
