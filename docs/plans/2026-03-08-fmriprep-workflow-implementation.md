# fmriprep-workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a zero-dependency Python CLI package (`fmriprep-run`) that registers neuroimaging datasets and submits fMRIPrep SLURM array jobs from anywhere.

**Architecture:** A `src`-layout Python package with four modules: `config.py` (JSON config management), `image.py` (apptainer image pulling), `submit.py` (sbatch template rendering + submission), and `cli.py` (argparse entry point). A sbatch template file lives in `templates/`. Config is stored at `~/.fmriprep_workflow/datasets.json`.

**Tech Stack:** Python 3.13 (stdlib only), uv package manager, SLURM/sbatch, Apptainer/Singularity

**Design doc:** `docs/plans/2026-03-08-fmriprep-workflow-design.md`

---

### Task 1: Scaffold the package with uv

**Files:**
- Create: `fmriprep-workflow/pyproject.toml`
- Create: `fmriprep-workflow/src/fmriprep_workflow/__init__.py`

**Step 1: Initialize the project with uv**

```bash
cd /home/users/logben/freesurfer
module load uv
uv init --lib --package --python 3.13 fmriprep-workflow
```

This creates the directory structure with `pyproject.toml` and `src/fmriprep_workflow/`.

**Step 2: Edit pyproject.toml to add the CLI entry point**

Replace the generated `pyproject.toml` with:

```toml
[project]
name = "fmriprep-workflow"
version = "0.1.0"
description = "CLI for submitting fMRIPrep SLURM array jobs"
requires-python = ">=3.9"

[project.scripts]
fmriprep-run = "fmriprep_workflow.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 3: Set `__init__.py` to empty**

```python
```

**Step 4: Verify the scaffold**

```bash
cd /home/users/logben/freesurfer/fmriprep-workflow
uv pip install -e .
```

Expected: installs successfully, `fmriprep-run` is not yet callable (cli.py doesn't exist).

**Step 5: Commit**

```bash
cd /home/users/logben/freesurfer/fmriprep-workflow
git init
git add pyproject.toml src/
git commit -m "scaffold: init fmriprep-workflow package with uv"
```

---

### Task 2: Implement config.py — config directory and defaults

**Files:**
- Create: `fmriprep-workflow/src/fmriprep_workflow/config.py`
- Create: `fmriprep-workflow/tests/test_config.py`

**Step 1: Write the failing tests**

```python
# tests/test_config.py
import json
import os
from pathlib import Path
from fmriprep_workflow.config import (
    CONFIG_DIR,
    CONFIG_FILE,
    DEFAULTS,
    load_datasets,
    save_dataset,
    get_dataset,
)


def test_config_dir_is_in_home():
    assert str(CONFIG_DIR) == str(Path.home() / ".fmriprep_workflow")


def test_defaults_has_required_keys():
    expected_keys = {
        "partition", "nthreads", "mem_per_cpu_gb", "time",
        "image_dir", "templateflow_dir", "fs_license",
        "bids_filter_file", "mail_user",
    }
    assert set(DEFAULTS.keys()) == expected_keys


def test_load_datasets_returns_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", tmp_path / "datasets.json")
    assert load_datasets() == {}


def test_save_and_load_dataset(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {
        "bids_dir": "/data/bids",
        "subjects_file": "/data/subs.txt",
        "fmriprep_version": "24.1.0",
    })

    datasets = load_datasets()
    assert "test_ds" in datasets
    assert datasets["test_ds"]["bids_dir"] == "/data/bids"


def test_get_dataset_merges_defaults(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {
        "bids_dir": "/data/bids",
        "subjects_file": "/data/subs.txt",
        "fmriprep_version": "24.1.0",
    })

    ds = get_dataset("test_ds")
    # Should have defaults merged in
    assert ds["partition"] == "russpold"
    assert ds["nthreads"] == 8
    # Should have user values
    assert ds["bids_dir"] == "/data/bids"


def test_get_dataset_raises_on_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", tmp_path / "datasets.json")
    try:
        get_dataset("nonexistent")
        assert False, "Should have raised SystemExit"
    except SystemExit:
        pass


def test_save_dataset_overwrites_existing(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    save_dataset("test_ds", {"bids_dir": "/old", "subjects_file": "/s.txt", "fmriprep_version": "1.0"})
    save_dataset("test_ds", {"bids_dir": "/new", "subjects_file": "/s.txt", "fmriprep_version": "2.0"})

    datasets = load_datasets()
    assert datasets["test_ds"]["bids_dir"] == "/new"
```

**Step 2: Run tests to verify they fail**

```bash
cd /home/users/logben/freesurfer/fmriprep-workflow
uv run pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'fmriprep_workflow.config'`

**Step 3: Write the implementation**

```python
# src/fmriprep_workflow/config.py
import json
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".fmriprep_workflow"
CONFIG_FILE = CONFIG_DIR / "datasets.json"

DEFAULTS = {
    "partition": "russpold",
    "nthreads": 8,
    "mem_per_cpu_gb": 8,
    "time": "5-00:00:00",
    "image_dir": "/home/groups/russpold/singularity_images",
    "templateflow_dir": "/home/groups/russpold/templateflow",
    "fs_license": "~/license.txt",
    "bids_filter_file": None,
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
        print(f"Error: dataset '{name}' not found. Run 'fmriprep-run show --list' to see registered datasets.", file=sys.stderr)
        sys.exit(1)
    merged = dict(DEFAULTS)
    merged.update(datasets[name])
    return merged
```

**Step 4: Run tests to verify they pass**

```bash
cd /home/users/logben/freesurfer/fmriprep-workflow
uv run pytest tests/test_config.py -v
```

Expected: all 7 tests PASS

**Step 5: Commit**

```bash
git add src/fmriprep_workflow/config.py tests/test_config.py
git commit -m "feat: add config module for dataset JSON management"
```

---

### Task 3: Implement image.py — apptainer image pull logic

**Files:**
- Create: `fmriprep-workflow/src/fmriprep_workflow/image.py`
- Create: `fmriprep-workflow/tests/test_image.py`

**Step 1: Write the failing tests**

```python
# tests/test_image.py
from pathlib import Path
from fmriprep_workflow.image import get_image_path, ensure_image


def test_get_image_path():
    path = get_image_path("/images", "24.1.0rc2")
    assert path == Path("/images/fmriprep_24.1.0rc2.sif")


def test_ensure_image_exists(tmp_path):
    sif = tmp_path / "fmriprep_24.1.0.sif"
    sif.touch()
    result = ensure_image(str(tmp_path), "24.1.0")
    assert result == sif
    # Should not raise or try to pull


def test_ensure_image_pulls_when_missing(tmp_path, monkeypatch):
    calls = []

    def mock_run(cmd, check):
        calls.append(cmd)
        # Simulate successful pull by creating the file
        (tmp_path / "fmriprep_1.0.0.sif").touch()

    monkeypatch.setattr("subprocess.run", mock_run)
    result = ensure_image(str(tmp_path), "1.0.0")
    assert result == tmp_path / "fmriprep_1.0.0.sif"
    assert len(calls) == 1
    assert "docker://nipreps/fmriprep:1.0.0" in calls[0]


def test_ensure_image_exits_on_pull_failure(tmp_path, monkeypatch):
    import subprocess

    def mock_run(cmd, check):
        raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr("subprocess.run", mock_run)
    try:
        ensure_image(str(tmp_path), "1.0.0")
        assert False, "Should have raised SystemExit"
    except SystemExit:
        pass
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_image.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# src/fmriprep_workflow/image.py
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
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_image.py -v
```

Expected: all 4 tests PASS

**Step 5: Commit**

```bash
git add src/fmriprep_workflow/image.py tests/test_image.py
git commit -m "feat: add image module for apptainer pull logic"
```

---

### Task 4: Create the sbatch template

**Files:**
- Create: `fmriprep-workflow/src/fmriprep_workflow/templates/fmriprep.sbatch`

**Step 1: Create the template directory**

```bash
mkdir -p /home/users/logben/freesurfer/fmriprep-workflow/src/fmriprep_workflow/templates
```

**Step 2: Write the template file**

```bash
#!/bin/bash
#SBATCH -J fmriprep_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_subjects}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

subject=$(sed "${{SLURM_ARRAY_TASK_ID}}q;d" {subjects_file})

FMRIPREP_IMG="{image_path}"
export APPTAINER_ENV_TEMPLATEFLOW_HOME="/templateflow"

apptainer run --cleanenv \
  -B {bids_dir}:/data \
  -B {templateflow_dir}:/templateflow \
  -B {work_dir}:/work \
  {config_bind_line} \
  "$FMRIPREP_IMG" \
  /data /data/derivatives/fmriprep_{fmriprep_version} participant \
  --participant-label "$subject" \
  -w /work \
  --nthreads {nthreads} \
  --mem_mb {mem_mb} \
  --output-spaces {output_spaces} \
  --fs-license-file {fs_license_container} \
  {bids_filter_arg} \
  {fmriprep_args} \
  --verbose

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
```

Note: `{mail_line}` is either `#SBATCH --mail-user={mail_user}\n#SBATCH --mail-type=ALL` or empty string. `{config_bind_line}` is either `-B {config_bind}:/config \` or empty. `{bids_filter_arg}` is either `--bids-filter-file /config/{filter_filename}` or empty. This avoids blank SBATCH lines when values are unset.

The derivs dir is `/data/derivatives/fmriprep_{version}` — using the container-internal bind path since `{bids_dir}` is mounted at `/data`.

**Step 3: Commit**

```bash
git add src/fmriprep_workflow/templates/
git commit -m "feat: add sbatch template for fmriprep jobs"
```

---

### Task 5: Implement submit.py — template rendering and sbatch submission

**Files:**
- Create: `fmriprep-workflow/src/fmriprep_workflow/submit.py`
- Create: `fmriprep-workflow/tests/test_submit.py`

**Step 1: Write the failing tests**

```python
# tests/test_submit.py
import os
from pathlib import Path
from fmriprep_workflow.submit import render_sbatch, count_subjects


def test_count_subjects(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\ns19\n")
    assert count_subjects(str(subs)) == 3


def test_count_subjects_ignores_blank_lines(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n\ns10\n\n")
    assert count_subjects(str(subs)) == 2


def test_render_sbatch_basic(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\ns10\n")

    config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "fmriprep_version": "24.1.0",
        "output_spaces": "MNI152NLin2009cAsym:res-2 fsnative",
        "fmriprep_args": "--no-submm-recon",
        "partition": "russpold",
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
        "image_dir": "/images",
        "templateflow_dir": "/home/groups/russpold/templateflow",
        "fs_license": "/home/user/license.txt",
        "bids_filter_file": None,
        "mail_user": None,
    }

    script = render_sbatch("test_ds", config)

    assert "#SBATCH -J fmriprep_test_ds" in script
    assert "#SBATCH --array=1-2" in script
    assert "--participant-label \"$subject\"" in script
    assert "/images/fmriprep_24.1.0.sif" in script
    assert "--no-submm-recon" in script
    assert "--output-spaces MNI152NLin2009cAsym:res-2 fsnative" in script
    # No mail line when mail_user is None
    assert "--mail-user" not in script


def test_render_sbatch_with_mail(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "fmriprep_version": "24.1.0",
        "output_spaces": "MNI152NLin2009cAsym:res-2",
        "fmriprep_args": "",
        "partition": "russpold",
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "fs_license": "/home/user/license.txt",
        "bids_filter_file": None,
        "mail_user": "user@stanford.edu",
    }

    script = render_sbatch("test_ds", config)
    assert "#SBATCH --mail-user=user@stanford.edu" in script
    assert "#SBATCH --mail-type=ALL" in script


def test_render_sbatch_with_bids_filter(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "fmriprep_version": "24.1.0",
        "output_spaces": "MNI152NLin2009cAsym:res-2",
        "fmriprep_args": "",
        "partition": "russpold",
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "fs_license": "/home/user/license.txt",
        "bids_filter_file": "/home/user/filter.json",
        "mail_user": None,
    }

    script = render_sbatch("test_ds", config)
    assert "-B /home/user:/config" in script
    assert "--bids-filter-file /config/filter.json" in script


def test_render_sbatch_mem_mb_is_90_percent(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")

    config = {
        "bids_dir": "/oak/data/bids",
        "subjects_file": str(subs),
        "fmriprep_version": "24.1.0",
        "output_spaces": "MNI152NLin2009cAsym:res-2",
        "fmriprep_args": "",
        "partition": "russpold",
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "5-00:00:00",
        "image_dir": "/images",
        "templateflow_dir": "/tf",
        "fs_license": "/home/user/license.txt",
        "bids_filter_file": None,
        "mail_user": None,
    }

    script = render_sbatch("test_ds", config)
    # 8 threads * 8 GB * 1000 * 0.9 = 57600
    assert "--mem_mb 57600" in script
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_submit.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# src/fmriprep_workflow/submit.py
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent / "templates" / "fmriprep.sbatch"


def count_subjects(subjects_file):
    with open(subjects_file) as f:
        return sum(1 for line in f if line.strip())


def render_sbatch(dataset_name, config):
    template = TEMPLATE_PATH.read_text()

    n_subjects = count_subjects(config["subjects_file"])
    nthreads = config["nthreads"]
    mem_per_cpu_gb = config["mem_per_cpu_gb"]
    mem_mb = int(nthreads * mem_per_cpu_gb * 1000 * 0.9)

    image_path = str(Path(config["image_dir"]) / f"fmriprep_{config['fmriprep_version']}.sif")
    fs_license = str(Path(config["fs_license"]).expanduser())

    scratch = os.environ.get("SCRATCH", "/tmp")
    work_dir = f"{scratch}/work/fmriprep_{dataset_name}_{config['fmriprep_version']}"
    log_dir = f"{config['bids_dir']}/derivatives/fmriprep_{config['fmriprep_version']}/logs"

    # Mail line
    if config.get("mail_user"):
        mail_line = f"#SBATCH --mail-user={config['mail_user']}\n#SBATCH --mail-type=ALL"
    else:
        mail_line = ""

    # BIDS filter
    if config.get("bids_filter_file"):
        filter_path = Path(config["bids_filter_file"])
        config_bind_line = f"-B {filter_path.parent}:/config \\"
        bids_filter_arg = f"--bids-filter-file /config/{filter_path.name}"
    else:
        config_bind_line = ""
        bids_filter_arg = ""

    return template.format(
        dataset_name=dataset_name,
        time=config["time"],
        n_subjects=n_subjects,
        nthreads=nthreads,
        mem_per_cpu_gb=mem_per_cpu_gb,
        partition=config["partition"],
        log_dir=log_dir,
        mail_line=mail_line,
        subjects_file=config["subjects_file"],
        image_path=image_path,
        bids_dir=config["bids_dir"],
        templateflow_dir=config["templateflow_dir"],
        work_dir=work_dir,
        config_bind_line=config_bind_line,
        fmriprep_version=config["fmriprep_version"],
        mem_mb=mem_mb,
        output_spaces=config.get("output_spaces", ""),
        fs_license_container=fs_license,
        bids_filter_arg=bids_filter_arg,
        fmriprep_args=config.get("fmriprep_args", ""),
    )


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

```bash
uv run pytest tests/test_submit.py -v
```

Expected: all 6 tests PASS

**Step 5: Commit**

```bash
git add src/fmriprep_workflow/submit.py tests/test_submit.py
git commit -m "feat: add submit module for sbatch rendering and submission"
```

---

### Task 6: Implement cli.py — argparse entry point

**Files:**
- Create: `fmriprep-workflow/src/fmriprep_workflow/cli.py`
- Create: `fmriprep-workflow/tests/test_cli.py`

**Step 1: Write the failing tests**

```python
# tests/test_cli.py
import json
import sys
from pathlib import Path
from fmriprep_workflow.cli import main


def test_add_dataset_creates_config(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    bids = tmp_path / "bids"
    bids.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "fmriprep-run", "add-dataset", "myds",
        "--bids-dir", str(bids),
        "--subjects-file", str(subs),
        "--fmriprep-version", "24.1.0",
    ])
    main()

    data = json.loads(config_file.read_text())
    assert "myds" in data
    assert data["myds"]["fmriprep_version"] == "24.1.0"


def test_add_dataset_with_optional_args(tmp_path, monkeypatch):
    config_file = tmp_path / "datasets.json"
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)

    subs = tmp_path / "subs.txt"
    subs.write_text("s03\n")
    bids = tmp_path / "bids"
    bids.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "fmriprep-run", "add-dataset", "myds",
        "--bids-dir", str(bids),
        "--subjects-file", str(subs),
        "--fmriprep-version", "24.1.0",
        "--output-spaces", "MNI152NLin2009cAsym:res-2 fsnative",
        "--fmriprep-args", "--no-submm-recon --cifti-output 91k",
        "--partition", "normal",
        "--nthreads", "4",
        "--mail-user", "test@stanford.edu",
    ])
    main()

    data = json.loads(config_file.read_text())
    ds = data["myds"]
    assert ds["output_spaces"] == "MNI152NLin2009cAsym:res-2 fsnative"
    assert ds["fmriprep_args"] == "--no-submm-recon --cifti-output 91k"
    assert ds["partition"] == "normal"
    assert ds["nthreads"] == 4
    assert ds["mail_user"] == "test@stanford.edu"


def test_show_list_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", tmp_path / "datasets.json")
    monkeypatch.setattr(sys, "argv", ["fmriprep-run", "show", "--list"])
    main()
    output = capsys.readouterr().out
    assert "No datasets registered" in output


def test_show_list_with_datasets(tmp_path, monkeypatch, capsys):
    config_file = tmp_path / "datasets.json"
    config_file.write_text(json.dumps({
        "discovery": {"bids_dir": "/oak/disc", "subjects_file": "/s.txt", "fmriprep_version": "24.1.0"},
    }))
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_DIR", tmp_path)
    monkeypatch.setattr("fmriprep_workflow.config.CONFIG_FILE", config_file)
    monkeypatch.setattr(sys, "argv", ["fmriprep-run", "show", "--list"])
    main()
    output = capsys.readouterr().out
    assert "discovery" in output
    assert "/oak/disc" in output
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

```python
# src/fmriprep_workflow/cli.py
import argparse
import sys
from pathlib import Path

from fmriprep_workflow.config import save_dataset, get_dataset, load_datasets
from fmriprep_workflow.image import ensure_image
from fmriprep_workflow.submit import render_sbatch, submit_sbatch


def cmd_add_dataset(args):
    dataset_config = {
        "bids_dir": args.bids_dir,
        "subjects_file": args.subjects_file,
        "fmriprep_version": args.fmriprep_version,
    }
    # Only include optional args if provided
    optional = {
        "output_spaces": args.output_spaces,
        "fmriprep_args": args.fmriprep_args,
        "partition": args.partition,
        "nthreads": args.nthreads,
        "mem_per_cpu_gb": args.mem_per_cpu_gb,
        "time": args.time,
        "image_dir": args.image_dir,
        "templateflow_dir": args.templateflow_dir,
        "fs_license": args.fs_license,
        "bids_filter_file": args.bids_filter_file,
        "mail_user": args.mail_user,
    }
    for key, value in optional.items():
        if value is not None:
            dataset_config[key] = value

    # Path existence warnings
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
            print("No datasets registered. Use 'fmriprep-run add-dataset' to add one.")
            return
        for name, ds in datasets.items():
            print(f"  {name}: {ds.get('bids_dir', '(no bids_dir)')}")
        return

    config = get_dataset(args.name)
    script = render_sbatch(args.name, config)
    print(script)


def cmd_submit(args):
    config = get_dataset(args.name)
    ensure_image(config["image_dir"], config["fmriprep_version"])
    script = render_sbatch(args.name, config)
    print("--- Generated sbatch script ---")
    print(script)
    print("--- Submitting ---")
    submit_sbatch(script)


def main():
    parser = argparse.ArgumentParser(prog="fmriprep-run", description="Submit fMRIPrep SLURM array jobs")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add-dataset
    add_p = subparsers.add_parser("add-dataset", help="Register a dataset")
    add_p.add_argument("name", help="Dataset name (e.g., discovery, validation)")
    add_p.add_argument("--bids-dir", required=True, help="Path to BIDS directory")
    add_p.add_argument("--subjects-file", required=True, help="Path to subjects text file")
    add_p.add_argument("--fmriprep-version", required=True, help="fMRIPrep version tag")
    add_p.add_argument("--output-spaces", help="fMRIPrep output spaces")
    add_p.add_argument("--fmriprep-args", help="Additional fMRIPrep arguments")
    add_p.add_argument("--partition", help="SLURM partition")
    add_p.add_argument("--nthreads", type=int, help="CPUs per task")
    add_p.add_argument("--mem-per-cpu-gb", type=int, help="Memory per CPU in GB")
    add_p.add_argument("--time", help="SLURM time limit")
    add_p.add_argument("--image-dir", help="Directory for SIF images")
    add_p.add_argument("--templateflow-dir", help="TemplateFlow directory")
    add_p.add_argument("--fs-license", help="FreeSurfer license file path")
    add_p.add_argument("--bids-filter-file", help="BIDS filter JSON file path")
    add_p.add_argument("--mail-user", help="Email for SLURM notifications")
    add_p.set_defaults(func=cmd_add_dataset)

    # show
    show_p = subparsers.add_parser("show", help="Preview sbatch script or list datasets")
    show_p.add_argument("name", nargs="?", help="Dataset name to preview")
    show_p.add_argument("--list", action="store_true", help="List all registered datasets")
    show_p.set_defaults(func=cmd_show)

    # submit
    sub_p = subparsers.add_parser("submit", help="Submit fMRIPrep job to SLURM")
    sub_p.add_argument("name", help="Dataset name to submit")
    sub_p.set_defaults(func=cmd_submit)

    args = parser.parse_args()
    args.func(args)
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_cli.py -v
```

Expected: all 4 tests PASS

**Step 5: Commit**

```bash
git add src/fmriprep_workflow/cli.py tests/test_cli.py
git commit -m "feat: add CLI with add-dataset, show, and submit commands"
```

---

### Task 7: Install and end-to-end smoke test

**Files:**
- No new files — integration test of the installed package

**Step 1: Reinstall the package**

```bash
cd /home/users/logben/freesurfer/fmriprep-workflow
module load uv
uv pip install -e .
```

Expected: successful install

**Step 2: Verify CLI is accessible from anywhere**

```bash
cd /tmp
fmriprep-run --help
```

Expected: shows usage with `add-dataset`, `show`, `submit` subcommands

**Step 3: Register the discovery dataset**

```bash
fmriprep-run add-dataset discovery \
  --bids-dir /oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402 \
  --subjects-file /home/users/logben/freesurfer/subs_discovery.txt \
  --fmriprep-version 24.1.0rc2 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos --medial-surface-nan --project-goodvoxels" \
  --mail-user logben@stanford.edu
```

Expected: `Dataset 'discovery' saved.`

**Step 4: Preview the generated script**

```bash
fmriprep-run show discovery
```

Expected: a complete sbatch script with `--array=1-5` (5 subjects), correct paths, correct flags. Review manually.

**Step 5: Register the validation dataset**

```bash
fmriprep-run add-dataset validation \
  --bids-dir /oak/stanford/groups/russpold/data/network_grant/validation_BIDS \
  --subjects-file /home/users/logben/freesurfer/subs_validation.txt \
  --fmriprep-version 24.1.0rc2 \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsaverage6 fsnative func anat" \
  --fmriprep-args "--no-submm-recon --skip-bids-validation --cifti-output 91k --me-output-echos --medial-surface-nan --project-goodvoxels" \
  --mail-user logben@stanford.edu
```

**Step 6: List datasets**

```bash
fmriprep-run show --list
```

Expected: lists both `discovery` and `validation` with their BIDS dirs.

**Step 7: Verify config file**

```bash
cat ~/.fmriprep_workflow/datasets.json
```

Expected: well-formatted JSON with both datasets.

**Step 8: Run all tests**

```bash
cd /home/users/logben/freesurfer/fmriprep-workflow
uv run pytest tests/ -v
```

Expected: all tests pass

**Step 9: Commit**

```bash
git add -A
git commit -m "chore: verify end-to-end workflow"
```

---

## Task Summary

| Task | What it builds | Tests |
|------|---------------|-------|
| 1 | Package scaffold with uv + pyproject.toml | manual install check |
| 2 | `config.py` — JSON config management | 7 tests |
| 3 | `image.py` — apptainer pull logic | 4 tests |
| 4 | sbatch template file | none (template only) |
| 5 | `submit.py` — template rendering + submission | 6 tests |
| 6 | `cli.py` — argparse entry point | 4 tests |
| 7 | End-to-end smoke test | manual CLI walkthrough |
