# Phase 1: Rename + Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rename `fmriprep_workflow` to `neuro_workflow` with a `core/` + `pipelines/` architecture, changing CLI from `fmriprep-run` to `neuro-run` with `submit fmriprep` syntax.

**Architecture:** Move shared infrastructure (config, SLURM submission, image management) into `neuro_workflow/core/`. Extract fMRIPrep-specific logic (template context building, CLI args, resource defaults) into `neuro_workflow/pipelines/fmriprep.py`. A `Pipeline` protocol in `base.py` defines the contract. The CLI auto-discovers registered pipelines.

**Tech Stack:** Python 3.9+ stdlib only, pytest, uv (load with `ml uv`), hatchling build backend.

**Test runner:** `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/ -v`

---

### Task 1: Create directory structure and update pyproject.toml

**Files:**
- Create: `src/neuro_workflow/__init__.py`
- Create: `src/neuro_workflow/core/__init__.py`
- Create: `src/neuro_workflow/pipelines/__init__.py`
- Modify: `pyproject.toml`
- Delete: `src/fmriprep_workflow/__init__.py` (after migration complete)

**Step 1: Create new package directories**

```bash
mkdir -p src/neuro_workflow/core src/neuro_workflow/pipelines src/neuro_workflow/templates
touch src/neuro_workflow/__init__.py src/neuro_workflow/core/__init__.py src/neuro_workflow/pipelines/__init__.py
```

**Step 2: Copy the sbatch template to new location**

Copy `src/fmriprep_workflow/templates/fmriprep.sbatch` to `src/neuro_workflow/templates/fmriprep.sbatch` (identical content).

**Step 3: Update pyproject.toml**

```toml
[project]
name = "neuro-workflow"
version = "0.2.0"
description = "CLI for submitting neuroimaging SLURM array jobs"
requires-python = ">=3.9"

[project.scripts]
neuro-run = "neuro_workflow.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pytest>=8.4.2",
]
```

**Step 4: Run uv sync to install new package**

Run: `ml uv && unset VIRTUAL_ENV && uv sync`
Expected: resolves and installs `neuro-workflow`

**Step 5: Commit**

```bash
git add src/neuro_workflow/ pyproject.toml
git commit -m "chore: scaffold neuro_workflow package structure"
```

---

### Task 2: Create core/config.py with dataset-only config

The config module changes from the old version:
- Config dir: `~/.neuro_workflow` (was `~/.fmriprep_workflow`)
- DEFAULTS: only dataset-level defaults (partition, image_dir, templateflow_dir, mail_user). Pipeline-specific defaults (nthreads, mem_per_cpu_gb, time, fs_license, bids_filter_file) move to the pipeline.

**Files:**
- Create: `src/neuro_workflow/core/config.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_config.py`

**Step 1: Write the failing tests**

Create `tests/core/__init__.py` (empty) and `tests/core/test_config.py`:

```python
import json
from pathlib import Path
from neuro_workflow.core.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULTS,
    load_datasets,
    save_dataset,
    get_dataset,
)


def test_config_dir_is_in_home():
    assert str(CONFIG_DIR) == str(Path.home() / ".neuro_workflow")


def test_defaults_has_expected_keys():
    expected_keys = {"partition", "image_dir", "templateflow_dir", "mail_user"}
    assert set(DEFAULTS.keys()) == expected_keys


def test_load_datasets_returns_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", tmp_path / "datasets.json")
    assert load_datasets() == {}


def test_save_and_load_dataset(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {"bids_dir": "/data/bids", "subjects_file": "/data/subs.txt"})

    datasets = load_datasets()
    assert "test_ds" in datasets
    assert datasets["test_ds"]["bids_dir"] == "/data/bids"


def test_get_dataset_merges_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {"bids_dir": "/data/bids", "subjects_file": "/data/subs.txt"})

    ds = get_dataset("test_ds")
    assert ds["partition"] == "russpold"
    assert ds["image_dir"] == "/home/groups/russpold/singularity_images"
    assert ds["bids_dir"] == "/data/bids"


def test_get_dataset_exits_on_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", tmp_path / "datasets.json")
    try:
        get_dataset("nonexistent")
        assert False, "Should have raised SystemExit"
    except SystemExit:
        pass


def test_save_dataset_overwrites_existing(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {"bids_dir": "/old", "subjects_file": "/s.txt"})
    save_dataset("test_ds", {"bids_dir": "/new", "subjects_file": "/s.txt"})

    datasets = load_datasets()
    assert datasets["test_ds"]["bids_dir"] == "/new"
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/core/test_config.py -v`
Expected: FAIL (ImportError — module doesn't exist yet)

**Step 3: Write the implementation**

Create `src/neuro_workflow/core/config.py`:

```python
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
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/core/test_config.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add src/neuro_workflow/core/config.py tests/core/
git commit -m "feat: add core/config.py with dataset-only defaults"
```

---

### Task 3: Create core/image.py (generalized for any pipeline)

Generalize image management to accept a pipeline name and Docker URI instead of hardcoding fMRIPrep.

**Files:**
- Create: `src/neuro_workflow/core/image.py`
- Create: `tests/core/test_image.py`

**Step 1: Write the failing tests**

Create `tests/core/test_image.py`:

```python
from pathlib import Path
from neuro_workflow.core.image import get_image_path, ensure_image


def test_get_image_path():
    path = get_image_path("/images", "fmriprep", "24.1.0rc2")
    assert path == Path("/images/fmriprep_24.1.0rc2.sif")


def test_get_image_path_different_pipeline():
    path = get_image_path("/images", "mriqc", "24.1.0")
    assert path == Path("/images/mriqc_24.1.0.sif")


def test_ensure_image_exists(tmp_path):
    sif = tmp_path / "fmriprep_24.1.0.sif"
    sif.touch()
    result = ensure_image(str(tmp_path), "fmriprep", "24.1.0", "docker://nipreps/fmriprep")
    assert result == sif


def test_ensure_image_pulls_when_missing(tmp_path, monkeypatch):
    calls = []

    def mock_run(cmd, check):
        calls.append(cmd)
        (tmp_path / "mriqc_1.0.0.sif").touch()

    monkeypatch.setattr("subprocess.run", mock_run)
    result = ensure_image(str(tmp_path), "mriqc", "1.0.0", "docker://nipreps/mriqc")
    assert result == tmp_path / "mriqc_1.0.0.sif"
    assert len(calls) == 1
    assert "docker://nipreps/mriqc:1.0.0" in calls[0]


def test_ensure_image_exits_on_pull_failure(tmp_path, monkeypatch):
    import subprocess

    def mock_run(cmd, check):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr("subprocess.run", mock_run)
    try:
        ensure_image(str(tmp_path), "fmriprep", "1.0.0", "docker://nipreps/fmriprep")
        assert False, "Should have raised SystemExit"
    except SystemExit:
        pass
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/core/test_image.py -v`
Expected: FAIL (ImportError)

**Step 3: Write the implementation**

Create `src/neuro_workflow/core/image.py`:

```python
import subprocess
import sys
from pathlib import Path


def get_image_path(image_dir, pipeline_name, version):
    return Path(image_dir) / f"{pipeline_name}_{version}.sif"


def ensure_image(image_dir, pipeline_name, version, docker_uri):
    path = get_image_path(image_dir, pipeline_name, version)
    if path.exists():
        print(f"Image found: {path}")
        return path

    print(f"Image not found at {path}, pulling...")
    cmd = ["apptainer", "pull", str(path), f"{docker_uri}:{version}"]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        print(f"Error: failed to pull {docker_uri}:{version}", file=sys.stderr)
        sys.exit(1)

    return path
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/core/test_image.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/neuro_workflow/core/image.py tests/core/test_image.py
git commit -m "feat: add core/image.py with pipeline-generic image management"
```

---

### Task 4: Create core/slurm.py (generic template rendering + submission)

Extract the generic parts of submit.py: counting subjects, rendering any template from a context dict, and submitting via sbatch.

**Files:**
- Create: `src/neuro_workflow/core/slurm.py`
- Create: `tests/core/test_slurm.py`

**Step 1: Write the failing tests**

Create `tests/core/test_slurm.py`:

```python
from pathlib import Path
from neuro_workflow.core.slurm import count_subjects, load_subjects, render_template


def test_count_subjects(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\ns19\n")
    assert count_subjects(str(subs)) == 3


def test_count_subjects_ignores_blank_lines(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n\ns10\n\n")
    assert count_subjects(str(subs)) == 2


def test_load_subjects(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n\ns19\n")
    assert load_subjects(str(subs)) == ["s03", "s10", "s19"]


def test_render_template(tmp_path):
    template = tmp_path / "test.sbatch"
    template.write_text("#!/bin/bash\n#SBATCH -J {job_name}\necho {greeting}")
    result = render_template(template, {"job_name": "test_job", "greeting": "hello"})
    assert "test_job" in result
    assert "hello" in result


def test_render_template_from_string():
    """render_template accepts a Path object."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sbatch", delete=False) as f:
        f.write("#!/bin/bash\n#SBATCH -J {name}\n")
        f.flush()
        result = render_template(Path(f.name), {"name": "mytest"})
    assert "#SBATCH -J mytest" in result
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/core/test_slurm.py -v`
Expected: FAIL (ImportError)

**Step 3: Write the implementation**

Create `src/neuro_workflow/core/slurm.py`:

```python
import subprocess
import sys
import tempfile
from pathlib import Path


def count_subjects(subjects_file):
    with open(subjects_file) as f:
        return sum(1 for line in f if line.strip())


def load_subjects(subjects_file):
    with open(subjects_file) as f:
        return [line.strip() for line in f if line.strip()]


def render_template(template_path, context):
    template = Path(template_path).read_text()
    return template.format(**context)


def submit_sbatch(script_content):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sbatch", delete=False) as f:
        f.write(script_content)
        f.flush()
        print(f"Sbatch script written to: {f.name}")
        result = subprocess.run(["sbatch", f.name], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error submitting job: {result.stderr}", file=sys.stderr)
            sys.exit(1)
        print(result.stdout.strip())
        return result.stdout.strip()
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/core/test_slurm.py -v`
Expected: 5 passed

**Step 5: Commit**

```bash
git add src/neuro_workflow/core/slurm.py tests/core/test_slurm.py
git commit -m "feat: add core/slurm.py with generic template rendering and submission"
```

---

### Task 5: Create pipelines/base.py (Pipeline protocol)

Define the protocol that all pipeline plugins must follow.

**Files:**
- Create: `src/neuro_workflow/pipelines/base.py`
- Create: `tests/pipelines/__init__.py`
- Create: `tests/pipelines/test_base.py`

**Step 1: Write the failing tests**

Create `tests/pipelines/__init__.py` (empty) and `tests/pipelines/test_base.py`:

```python
from neuro_workflow.pipelines.base import Pipeline, TEMPLATE_DIR, get_pipeline, list_pipelines


def test_template_dir_exists():
    assert TEMPLATE_DIR.is_dir()


def test_pipeline_protocol_has_required_attributes():
    """Verify the protocol defines the expected interface."""
    import inspect
    members = {name for name, _ in inspect.getmembers(Pipeline)}
    assert "name" in members
    assert "docker_uri" in members
    assert "template_name" in members
    assert "default_resources" in members
    assert "add_cli_args" in members
    assert "build_context" in members


def test_get_pipeline_returns_none_for_unknown():
    result = get_pipeline("nonexistent_pipeline_xyz")
    assert result is None


def test_list_pipelines_returns_dict():
    result = list_pipelines()
    assert isinstance(result, dict)
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_base.py -v`
Expected: FAIL (ImportError)

**Step 3: Write the implementation**

Create `src/neuro_workflow/pipelines/base.py`:

```python
from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Protocol, runtime_checkable

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

# Registry mapping pipeline name -> pipeline instance
_REGISTRY: dict[str, Pipeline] = {}


@runtime_checkable
class Pipeline(Protocol):
    name: str
    docker_uri: str
    template_name: str
    default_resources: dict

    def add_cli_args(self, parser: ArgumentParser) -> None: ...
    def build_context(self, dataset_config: dict, args: Namespace) -> dict: ...


def register(pipeline: Pipeline) -> None:
    _REGISTRY[pipeline.name] = pipeline


def get_pipeline(name: str) -> Pipeline | None:
    return _REGISTRY.get(name)


def list_pipelines() -> dict[str, Pipeline]:
    return dict(_REGISTRY)
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_base.py -v`
Expected: 4 passed

**Step 5: Commit**

```bash
git add src/neuro_workflow/pipelines/base.py tests/pipelines/
git commit -m "feat: add pipelines/base.py with Pipeline protocol and registry"
```

---

### Task 6: Create pipelines/fmriprep.py

Extract all fMRIPrep-specific logic: resource defaults, CLI args, template context building. This is the largest task — it replaces the old `submit.py`'s `render_sbatch()` and the fMRIPrep-specific parts of `cli.py`.

**Files:**
- Create: `src/neuro_workflow/pipelines/fmriprep.py`
- Create: `tests/pipelines/test_fmriprep.py`

**Step 1: Write the failing tests**

Create `tests/pipelines/test_fmriprep.py`:

```python
import os
from argparse import Namespace
from pathlib import Path
from neuro_workflow.pipelines.fmriprep import FmriprepPipeline
from neuro_workflow.pipelines.base import get_pipeline, TEMPLATE_DIR
from neuro_workflow.core.slurm import render_template


def test_fmriprep_pipeline_is_registered():
    pipeline = get_pipeline("fmriprep")
    assert pipeline is not None
    assert pipeline.name == "fmriprep"


def test_fmriprep_has_correct_docker_uri():
    p = FmriprepPipeline()
    assert p.docker_uri == "docker://nipreps/fmriprep"


def test_fmriprep_default_resources():
    p = FmriprepPipeline()
    assert p.default_resources["nthreads"] == 8
    assert p.default_resources["mem_per_cpu_gb"] == 8
    assert p.default_resources["time"] == "5-00:00:00"


def test_fmriprep_template_exists():
    p = FmriprepPipeline()
    assert (TEMPLATE_DIR / p.template_name).exists()


def test_fmriprep_build_context_basic(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/home/groups/russpold/templateflow",
        "mail_user": None,
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2 fsnative",
        fmriprep_args="--no-submm-recon",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)

    assert ctx["dataset_name"] == "test_ds"
    assert ctx["n_subjects"] == 2
    assert ctx["nthreads"] == 8  # from default_resources
    assert ctx["mem_mb"] == 57600  # 8 * 8 * 1000 * 0.9
    assert ctx["fmriprep_version"] == "24.1.0"
    assert ctx["output_spaces"] == "MNI152NLin2009cAsym:res-2 fsnative"
    assert ctx["image_path"] == "/images/fmriprep_24.1.0.sif"
    assert ctx["mail_line"] == ""


def test_fmriprep_build_context_with_mail(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": "user@stanford.edu",
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert "#SBATCH --mail-user=user@stanford.edu" in ctx["mail_line"]
    assert "#SBATCH --mail-type=ALL" in ctx["mail_line"]


def test_fmriprep_build_context_with_bids_filter(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file="/home/user/filter.json",
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert "-B /home/user:/config" in ctx["config_bind_line"]
    assert ctx["bids_filter_arg"] == "--bids-filter-file /config/filter.json"


def test_fmriprep_build_context_override_resources(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "mail_user": None,
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=4,
        mem_per_cpu_gb=16,
        time="2-00:00:00",
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["nthreads"] == 4
    assert ctx["mem_per_cpu_gb"] == 16
    assert ctx["time"] == "2-00:00:00"
    assert ctx["mem_mb"] == int(4 * 16 * 1000 * 0.9)


def test_fmriprep_render_full_template(tmp_path):
    """Integration test: build context + render template produces valid script."""
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")

    p = FmriprepPipeline()
    dataset_config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/home/groups/russpold/templateflow",
        "mail_user": None,
    }
    args = Namespace(
        version="24.1.0",
        output_spaces="MNI152NLin2009cAsym:res-2 fsnative",
        fmriprep_args="--no-submm-recon",
        fs_license="/home/user/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "#SBATCH -J fmriprep_test_ds" in script
    assert "#SBATCH --array=1-2" in script
    assert "--participant-label \"$subject\"" in script
    assert "/images/fmriprep_24.1.0.sif" in script
    assert "--no-submm-recon" in script
    assert "--output-spaces MNI152NLin2009cAsym:res-2 fsnative" in script
    assert "--mail-user" not in script
    assert "--mem_mb 57600" in script
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_fmriprep.py -v`
Expected: FAIL (ImportError)

**Step 3: Write the implementation**

Create `src/neuro_workflow/pipelines/fmriprep.py`:

```python
import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import count_subjects
from neuro_workflow.pipelines.base import register


class FmriprepPipeline:
    name = "fmriprep"
    docker_uri = "docker://nipreps/fmriprep"
    template_name = "fmriprep.sbatch"
    default_resources = {
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", required=True, help="fMRIPrep version tag (e.g. 25.2.4)")
        parser.add_argument("--output-spaces", default="", help="fMRIPrep output spaces")
        parser.add_argument("--fmriprep-args", default="", help="Additional fMRIPrep arguments")
        parser.add_argument("--fs-license", default="~/license.txt", help="FreeSurfer license file")
        parser.add_argument("--bids-filter-file", default=None, help="BIDS filter JSON file path")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 8)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 8)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 5-00:00:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
        mem_per_cpu_gb = args.mem_per_cpu_gb if args.mem_per_cpu_gb is not None else self.default_resources["mem_per_cpu_gb"]
        time = args.time if args.time is not None else self.default_resources["time"]

        n_subjects = count_subjects(dataset_config["subjects_file"])
        mem_mb = int(nthreads * mem_per_cpu_gb * 1000 * 0.9)

        image_path = str(Path(dataset_config["image_dir"]) / f"fmriprep_{args.version}.sif")
        fs_license = str(Path(args.fs_license).expanduser())

        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/fmriprep_{dataset_name}_{args.version}"
        log_dir = f"{dataset_config['bids_dir']}/derivatives/fmriprep_{args.version}/logs"

        if dataset_config.get("mail_user"):
            mail_line = f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
        else:
            mail_line = ""

        if args.bids_filter_file:
            filter_path = Path(args.bids_filter_file)
            config_bind_line = f"-B {filter_path.parent}:/config \\"
            bids_filter_arg = f"--bids-filter-file /config/{filter_path.name}"
        else:
            config_bind_line = ""
            bids_filter_arg = ""

        return {
            "dataset_name": dataset_name,
            "time": time,
            "n_subjects": n_subjects,
            "nthreads": nthreads,
            "mem_per_cpu_gb": mem_per_cpu_gb,
            "partition": dataset_config["partition"],
            "log_dir": log_dir,
            "mail_line": mail_line,
            "subjects_file": dataset_config["subjects_file"],
            "image_path": image_path,
            "bids_dir": dataset_config["bids_dir"],
            "templateflow_dir": dataset_config["templateflow_dir"],
            "work_dir": work_dir,
            "config_bind_line": config_bind_line,
            "fmriprep_version": args.version,
            "mem_mb": mem_mb,
            "output_spaces": args.output_spaces,
            "fs_license_container": fs_license,
            "bids_filter_arg": bids_filter_arg,
            "fmriprep_args": args.fmriprep_args,
        }


# Auto-register when module is imported
register(FmriprepPipeline())
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_fmriprep.py -v`
Expected: 9 passed

**Step 5: Commit**

```bash
git add src/neuro_workflow/pipelines/fmriprep.py tests/pipelines/test_fmriprep.py
git commit -m "feat: add pipelines/fmriprep.py with FmriprepPipeline"
```

---

### Task 7: Create the new CLI (neuro-run)

The new CLI uses the pipeline registry for `submit` and `show` commands. `add-dataset` becomes pipeline-agnostic (no fmriprep-specific args).

**Files:**
- Create: `src/neuro_workflow/cli.py`
- Create: `tests/test_cli.py` (new version)

**Step 1: Write the failing tests**

Create `tests/test_new_cli.py` (temporary name to avoid conflicting with old tests):

```python
import json
import sys
from pathlib import Path
from neuro_workflow.cli import main


def test_add_dataset_creates_config(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    bids = tmp_path / "bids"
    bids.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "neuro-run", "add-dataset", "myds",
        "--bids-dir", str(bids),
        "--subjects-file", str(subs),
    ])
    main()

    data = json.loads(config_file.read_text())
    assert "myds" in data
    assert data["myds"]["bids_dir"] == str(bids)
    assert data["myds"]["subjects_file"] == str(subs)
    # Should NOT have fmriprep-specific fields
    assert "fmriprep_version" not in data["myds"]


def test_add_dataset_with_optional_args(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    bids = tmp_path / "bids"
    bids.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "neuro-run", "add-dataset", "myds",
        "--bids-dir", str(bids),
        "--subjects-file", str(subs),
        "--partition", "normal",
        "--mail-user", "test@stanford.edu",
    ])
    main()

    data = json.loads(config_file.read_text())
    ds = data["myds"]
    assert ds["partition"] == "normal"
    assert ds["mail_user"] == "test@stanford.edu"


def test_show_list_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", tmp_path / "datasets.json")
    monkeypatch.setattr(sys, "argv", ["neuro-run", "show", "--list"])
    main()
    output = capsys.readouterr().out
    assert "No datasets registered" in output


def test_show_list_with_datasets(tmp_path, monkeypatch, capsys):
    config_file = tmp_path / "datasets.json"
    config_file.write_text(json.dumps({
        "discovery": {"bids_dir": "/oak/disc", "subjects_file": "/s.txt"},
    }))
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)
    monkeypatch.setattr(sys, "argv", ["neuro-run", "show", "--list"])
    main()
    output = capsys.readouterr().out
    assert "discovery" in output
    assert "/oak/disc" in output


def test_show_renders_fmriprep_script(tmp_path, monkeypatch, capsys):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")

    config_file = tmp_path / "datasets.json"
    config_file.write_text(json.dumps({
        "test_ds": {
            "bids_dir": "/oak/data/bids",
            "subjects_file": str(subs),
        },
    }))
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    monkeypatch.setattr(sys, "argv", [
        "neuro-run", "show", "fmriprep", "test_ds",
        "--version", "24.1.0",
        "--output-spaces", "MNI152NLin2009cAsym:res-2",
        "--fs-license", "/home/user/license.txt",
    ])
    main()
    output = capsys.readouterr().out
    assert "#SBATCH -J fmriprep_test_ds" in output
    assert "#SBATCH --array=1-2" in output


def test_submit_renders_and_calls_sbatch(tmp_path, monkeypatch, capsys):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    sif = tmp_path / "images" / "fmriprep_24.1.0.sif"
    sif.parent.mkdir()
    sif.touch()

    config_file = tmp_path / "datasets.json"
    config_file.write_text(json.dumps({
        "test_ds": {
            "bids_dir": "/oak/data/bids",
            "subjects_file": str(subs),
            "image_dir": str(sif.parent),
        },
    }))
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("neuro_workflow.core.config.CONFIG_FILE", config_file)

    # Mock submit_sbatch to avoid actually calling sbatch
    submitted = []
    monkeypatch.setattr("neuro_workflow.cli.submit_sbatch", lambda script: submitted.append(script) or "Submitted batch job 12345")

    monkeypatch.setattr(sys, "argv", [
        "neuro-run", "submit", "fmriprep", "test_ds",
        "--version", "24.1.0",
        "--output-spaces", "MNI152NLin2009cAsym:res-2",
        "--fs-license", "/home/user/license.txt",
    ])
    main()
    assert len(submitted) == 1
    assert "#SBATCH -J fmriprep_test_ds" in submitted[0]
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/test_new_cli.py -v`
Expected: FAIL (ImportError)

**Step 3: Write the implementation**

Create `src/neuro_workflow/cli.py`:

```python
import argparse
import sys
from pathlib import Path

from neuro_workflow.core.config import save_dataset, get_dataset, load_datasets
from neuro_workflow.core.image import ensure_image
from neuro_workflow.core.slurm import render_template, submit_sbatch
from neuro_workflow.pipelines.base import get_pipeline, list_pipelines, TEMPLATE_DIR

# Import pipeline modules to trigger auto-registration
import neuro_workflow.pipelines.fmriprep  # noqa: F401


def cmd_add_dataset(args):
    dataset_config = {
        "bids_dir": args.bids_dir,
        "subjects_file": args.subjects_file,
    }
    optional = {
        "partition": args.partition,
        "mail_user": args.mail_user,
        "image_dir": args.image_dir,
        "templateflow_dir": args.templateflow_dir,
    }
    for key, value in optional.items():
        if value is not None:
            dataset_config[key] = value

    for path_key in ("bids_dir", "subjects_file"):
        p = Path(dataset_config[path_key])
        if not p.exists():
            print(f"Warning: {path_key} path does not exist: {p}", file=sys.stderr)

    save_dataset(args.name, dataset_config)
    print(f"Dataset '{args.name}' saved.")


def cmd_show(args):
    if args.list:
        datasets = load_datasets()
        if not datasets:
            print("No datasets registered. Use 'neuro-run add-dataset' to add one.")
            return
        for name, ds in datasets.items():
            print(f"  {name}: {ds.get('bids_dir', '(no bids_dir)')}")
        return

    pipeline = get_pipeline(args.pipeline)
    if pipeline is None:
        print(f"Error: unknown pipeline '{args.pipeline}'. Available: {', '.join(list_pipelines())}", file=sys.stderr)
        sys.exit(1)

    config = get_dataset(args.dataset)
    ctx = pipeline.build_context(args.dataset, config, args)
    template_path = TEMPLATE_DIR / pipeline.template_name
    script = render_template(template_path, ctx)
    print(script)


def cmd_submit(args):
    pipeline = get_pipeline(args.pipeline)
    if pipeline is None:
        print(f"Error: unknown pipeline '{args.pipeline}'. Available: {', '.join(list_pipelines())}", file=sys.stderr)
        sys.exit(1)

    config = get_dataset(args.dataset)
    ensure_image(config["image_dir"], pipeline.name, args.version, pipeline.docker_uri)

    ctx = pipeline.build_context(args.dataset, config, args)
    template_path = TEMPLATE_DIR / pipeline.template_name
    script = render_template(template_path, ctx)

    print("--- Generated sbatch script ---")
    print(script)
    print("--- Submitting ---")
    submit_sbatch(script)


def main():
    parser = argparse.ArgumentParser(prog="neuro-run", description="Submit neuroimaging SLURM array jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add-dataset (pipeline-agnostic)
    add_p = subparsers.add_parser("add-dataset", help="Register a dataset")
    add_p.add_argument("name", help="Dataset name (e.g., discovery, validation)")
    add_p.add_argument("--bids-dir", required=True, help="Path to BIDS directory")
    add_p.add_argument("--subjects-file", required=True, help="Path to subjects text file")
    add_p.add_argument("--partition", help="SLURM partition")
    add_p.add_argument("--mail-user", help="Email for SLURM notifications")
    add_p.add_argument("--image-dir", help="Directory for SIF images")
    add_p.add_argument("--templateflow-dir", help="TemplateFlow directory")
    add_p.set_defaults(func=cmd_add_dataset)

    # show
    show_p = subparsers.add_parser("show", help="Preview sbatch script or list datasets")
    show_p.add_argument("--list", action="store_true", help="List all registered datasets")
    show_p.add_argument("pipeline", nargs="?", help="Pipeline name (e.g. fmriprep)")
    show_p.add_argument("dataset", nargs="?", help="Dataset name to preview")
    # Add pipeline-specific args to show
    for pipeline in list_pipelines().values():
        pipeline.add_cli_args(show_p)
    show_p.set_defaults(func=cmd_show)

    # submit
    sub_p = subparsers.add_parser("submit", help="Submit a pipeline job to SLURM")
    sub_p.add_argument("pipeline", help="Pipeline name (e.g. fmriprep, mriqc)")
    sub_p.add_argument("dataset", help="Dataset name to submit")
    # Add pipeline-specific args to submit
    for pipeline in list_pipelines().values():
        pipeline.add_cli_args(sub_p)
    sub_p.set_defaults(func=cmd_submit)

    args = parser.parse_args()
    args.func(args)
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/test_new_cli.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add src/neuro_workflow/cli.py tests/test_new_cli.py
git commit -m "feat: add new CLI with 'neuro-run submit fmriprep' syntax"
```

---

### Task 8: Run all new tests together and clean up

Verify all new tests pass together, then remove the old `fmriprep_workflow` package and old tests.

**Files:**
- Delete: `src/fmriprep_workflow/` (entire directory)
- Delete: `tests/test_config.py` (old)
- Delete: `tests/test_image.py` (old)
- Delete: `tests/test_submit.py` (old)
- Delete: `tests/test_cli.py` (old)
- Rename: `tests/test_new_cli.py` → `tests/test_cli.py`

**Step 1: Run all new tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/core/ tests/pipelines/ tests/test_new_cli.py -v`
Expected: 23 passed (7 config + 5 image + 5 slurm + 4 base + 9 fmriprep + 6 cli = 36... let me recount: 7 + 5 + 5 + 4 + 9 + 6 = 36)

**Step 2: Remove old package and old tests**

```bash
rm -rf src/fmriprep_workflow/
rm tests/test_config.py tests/test_image.py tests/test_submit.py tests/test_cli.py
mv tests/test_new_cli.py tests/test_cli.py
```

**Step 3: uv sync to pick up the removal**

Run: `ml uv && unset VIRTUAL_ENV && uv sync`

**Step 4: Run all tests to verify nothing is broken**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/ -v`
Expected: 36 passed, 0 failed

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove old fmriprep_workflow package, finalize neuro_workflow restructure"
```

---

### Task 9: Update README.md

Update the README to reflect the new package name, CLI commands, and structure.

**Files:**
- Modify: `README.md`

**Step 1: Rewrite README.md**

Update all references:
- Package name: `neuro-workflow`
- CLI command: `neuro-run`
- `add-dataset` no longer takes `--fmriprep-version` (pipeline-agnostic)
- `submit` syntax: `neuro-run submit fmriprep <dataset> --version <ver>`
- `show` syntax: `neuro-run show fmriprep <dataset> --version <ver>`
- Package structure reflects `core/`, `pipelines/`, `templates/`

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README for neuro-workflow restructure"
```

---

### Task 10: Final verification

**Step 1: Run full test suite one last time**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/ -v`
Expected: All tests pass

**Step 2: Verify CLI entry point works**

Run: `ml uv && unset VIRTUAL_ENV && uv run neuro-run --help`
Expected: Shows `neuro-run` help with `add-dataset`, `show`, `submit` subcommands

Run: `ml uv && unset VIRTUAL_ENV && uv run neuro-run submit --help`
Expected: Shows `submit` help with `pipeline` and `dataset` positional args plus pipeline-specific flags
