import json
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".neuro_workflow"
CONFIG_FILE = CONFIG_DIR / "datasets.json"

# Canonical, committed source of truth for which subjects belong to each
# sample. Replaces the removed root subjects_*.txt files (PR1a). Lives at the
# repo root: config.py is at src/neuro_workflow/core/config.py, so the repo
# root is parents[3].
PIPELINE_CONFIG_FILE = Path(__file__).resolve().parents[3] / "config" / "pipeline_config.json"

DEFAULTS = {
    "partition": "russpold",
    "image_dir": "/home/groups/russpold/singularity_images",
    "templateflow_dir": "/home/groups/russpold/templateflow",
    "mail_user": None,
}


def load_datasets():
    if not CONFIG_FILE.exists():
        return {}
    with open(CONFIG_FILE) as f:
        return json.load(f)


def save_dataset(name, dataset_config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    datasets = load_datasets()
    if name in datasets:
        print(f"Warning: overwriting existing dataset '{name}'", file=sys.stderr)
    datasets[name] = dataset_config
    with open(CONFIG_FILE, "w") as f:
        json.dump(datasets, f, indent=2)


class DatasetNotFoundError(Exception):
    """Raised when a requested dataset is not registered in datasets.json.

    Raised by the library layer (get_dataset); the CLI boundary (cli.main)
    converts it to a stderr message + exit 1, keeping core importable/testable
    without coupling to process exit (RF-4).
    """


def get_dataset(name):
    datasets = load_datasets()
    if name not in datasets:
        raise DatasetNotFoundError(
            f"dataset '{name}' not found. "
            f"Run 'neuro-run show --list' to see registered datasets."
        )
    merged = dict(DEFAULTS)
    merged.update(datasets[name])
    return merged


def _load_samples() -> dict:
    """Load the `samples` block from config/pipeline_config.json (canonical)."""
    with open(PIPELINE_CONFIG_FILE) as f:
        return json.load(f).get("samples", {})


def resolve_dataset_subjects(dataset_name: str) -> list[str]:
    """Return the canonical subject IDs for ``dataset_name`` (bare, e.g. ``s10``).

    The authoritative source is ``config/pipeline_config.json`` -> ``samples``
    (committed, version-controlled). This replaces the removed root
    ``subjects_*.txt`` files. A sample may be either a list of IDs (discovery,
    validation) or a dict of ``{id: reason}`` (excluded); both yield the IDs in
    declaration order.

    Fail-loud: an unknown ``dataset_name`` raises ``ValueError`` listing the
    known samples. There is NO silent ``None``/empty return — a caller that
    can't resolve subjects must surface that, not silently skip filtering.
    """
    samples = _load_samples()
    if dataset_name not in samples:
        known = ", ".join(sorted(samples)) or "(none)"
        raise ValueError(
            f"unknown sample '{dataset_name}': not a key under `samples` in "
            f"{PIPELINE_CONFIG_FILE}. Known samples: {known}."
        )
    sample = samples[dataset_name]
    if isinstance(sample, dict):
        return list(sample.keys())
    return list(sample)


def is_known_sample(dataset_name: str) -> bool:
    """True if ``dataset_name`` is a canonical sample in pipeline_config.json."""
    return dataset_name in _load_samples()
