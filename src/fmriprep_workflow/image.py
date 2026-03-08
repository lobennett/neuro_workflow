import subprocess
import sys
from pathlib import Path


def get_image_path(image_dir, version):
    return Path(image_dir) / f"fmriprep_{version}.sif"


def ensure_image(image_dir, version):
    path = get_image_path(image_dir, version)
    if path.exists():
        print(f"Image found: {path}")
        return path

    print(f"Image not found at {path}, pulling...")
    cmd = [
        "apptainer", "pull",
        str(path),
        f"docker://nipreps/fmriprep:{version}",
    ]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        print(f"Error: failed to pull fmriprep:{version}", file=sys.stderr)
        sys.exit(1)

    return path
