import json
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".neuro_workflow"
CONFIG_FILE = CONFIG_DIR / "datasets.json"

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
