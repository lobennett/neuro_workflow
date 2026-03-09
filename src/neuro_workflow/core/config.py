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


def get_dataset(name):
    datasets = load_datasets()
    if name not in datasets:
        print(
            f"Error: dataset '{name}' not found. Run 'neuro-run show --list' to see registered datasets.",
            file=sys.stderr,
        )
        sys.exit(1)
    merged = dict(DEFAULTS)
    merged.update(datasets[name])
    return merged
