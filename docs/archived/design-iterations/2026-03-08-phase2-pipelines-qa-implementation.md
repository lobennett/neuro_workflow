# Phase 2: New Pipelines + QA Scripts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 4 container pipelines (qsiprep, fsqc, freesurfer, happy), 5 QA scripts (neg-events, breaks, global-signal, outlier-report, reliability), and an exclusions management module to neuro-workflow.

**Architecture:** Pipelines follow the existing `Pipeline` protocol pattern (see `fmriprep.py`). QA scripts follow a new `QaCommand` protocol with its own registry. Exclusion generators follow an `ExclusionGenerator` protocol with source-based compilation. All are auto-registered on import and wired into the CLI.

**Tech Stack:** Python 3.9+ stdlib (core), pytest, uv (`ml uv && unset VIRTUAL_ENV && uv run python -m pytest`), optional QA extras (nilearn, nibabel, matplotlib, pandas, numpy, img2pdf).

---

## Task 1: QA Base Protocol and Registry

**Files:**
- Create: `src/neuro_workflow/qa/__init__.py`
- Create: `src/neuro_workflow/qa/base.py`
- Test: `tests/qa/test_base.py`

**Step 1: Write the failing tests**

Create `tests/qa/__init__.py` (empty) and `tests/qa/test_base.py`:

```python
from argparse import Namespace
from neuro_workflow.qa.base import register_qa, get_qa_command, list_qa_commands


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
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_base.py -v`
Expected: FAIL (import error)

**Step 3: Write minimal implementation**

Create `src/neuro_workflow/qa/__init__.py` (empty file).

Create `src/neuro_workflow/qa/base.py`:

```python
from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import Protocol, runtime_checkable

_REGISTRY: dict[str, QaCommand] = {}


@runtime_checkable
class QaCommand(Protocol):
    name: str
    description: str

    def add_cli_args(self, parser: ArgumentParser) -> None: ...
    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None: ...


def register_qa(command: QaCommand) -> None:
    _REGISTRY[command.name] = command


def get_qa_command(name: str) -> QaCommand | None:
    return _REGISTRY.get(name)


def list_qa_commands() -> dict[str, QaCommand]:
    return dict(_REGISTRY)
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_base.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/qa/__init__.py src/neuro_workflow/qa/base.py tests/qa/__init__.py tests/qa/test_base.py
git commit -m "feat: add QaCommand protocol and registry (qa/base.py)"
```

---

## Task 2: QSIPrep Pipeline

**Files:**
- Create: `src/neuro_workflow/templates/qsiprep.sbatch`
- Create: `src/neuro_workflow/pipelines/qsiprep.py`
- Test: `tests/pipelines/test_qsiprep.py`

**Step 1: Write the failing tests**

Create `tests/pipelines/test_qsiprep.py`:

```python
import os
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from neuro_workflow.pipelines.qsiprep import QsiprepPipeline


def make_args(**overrides):
    defaults = {
        "version": "1.1.1",
        "output_resolution": 1.5,
        "qsiprep_args": "",
        "fs_license": "~/license.txt",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s01\ns02\ns03\n")
    return {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "templateflow_dir": "/templateflow",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = QsiprepPipeline()
    assert p.name == "qsiprep"
    assert p.docker_uri == "docker://pennlinc/qsiprep"
    assert p.template_name == "qsiprep.sbatch"


def test_default_resources():
    p = QsiprepPipeline()
    assert p.default_resources["nthreads"] == 8
    assert p.default_resources["mem_per_cpu_gb"] == 8
    assert p.default_resources["time"] == "24:00:00"


def test_build_context_basic(tmp_path):
    p = QsiprepPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("personal", config, args)
    assert ctx["dataset_name"] == "personal"
    assert ctx["n_subjects"] == 3
    assert ctx["nthreads"] == 8
    assert ctx["output_resolution"] == 1.5
    assert ctx["image_path"] == "/images/qsiprep_1.1.1.sif"
    assert ctx["qsiprep_version"] == "1.1.1"


def test_build_context_version_required(tmp_path):
    import sys
    p = QsiprepPipeline()
    config = make_config(tmp_path)
    args = make_args(version=None)
    with patch.object(sys, "exit", side_effect=SystemExit) as mock_exit:
        try:
            p.build_context("personal", config, args)
        except SystemExit:
            pass
    mock_exit.assert_called_once_with(1)


def test_build_context_custom_resources(tmp_path):
    p = QsiprepPipeline()
    config = make_config(tmp_path)
    args = make_args(nthreads=4, mem_per_cpu_gb=4, time="12:00:00")
    ctx = p.build_context("personal", config, args)
    assert ctx["nthreads"] == 4
    assert ctx["mem_per_cpu_gb"] == 4
    assert ctx["time"] == "12:00:00"


def test_build_context_mail_line(tmp_path):
    p = QsiprepPipeline()
    config = make_config(tmp_path)
    config["mail_user"] = "user@example.com"
    args = make_args()
    ctx = p.build_context("personal", config, args)
    assert "user@example.com" in ctx["mail_line"]


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = QsiprepPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("personal", config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)
    assert "qsiprep" in script
    assert "--output-resolution 1.5" in script
    assert "apptainer run" in script
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_qsiprep.py -v`
Expected: FAIL (import error)

**Step 3: Write the sbatch template**

Create `src/neuro_workflow/templates/qsiprep.sbatch`:

```bash
#!/bin/bash
#SBATCH -J qsiprep_{dataset_name}
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

QSIPREP_IMG="{image_path}"

mkdir -p "{work_dir}"

apptainer run --cleanenv \
  -B {bids_dir}:/data \
  -B {work_dir}:/work \
  -B {fs_license}:/opt/freesurfer/license.txt \
  "$QSIPREP_IMG" \
  /data /data/derivatives/qsiprep_{qsiprep_version} participant \
  --participant-label "$subject" \
  -w /work \
  --nthreads {nthreads} \
  --mem-mb {mem_mb} \
  --output-resolution {output_resolution} \
  {qsiprep_args}

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
```

**Step 4: Write the pipeline module**

Create `src/neuro_workflow/pipelines/qsiprep.py`:

```python
import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import count_subjects
from neuro_workflow.pipelines.base import register


class QsiprepPipeline:
    name = "qsiprep"
    docker_uri = "docker://pennlinc/qsiprep"
    template_name = "qsiprep.sbatch"
    default_resources = {
        "nthreads": 8,
        "mem_per_cpu_gb": 8,
        "time": "24:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="QSIPrep version tag (e.g. 1.1.1)")
        parser.add_argument("--output-resolution", type=float, default=1.5, help="Output resolution in mm (default: 1.5)")
        parser.add_argument("--qsiprep-args", default="", help="Additional QSIPrep arguments")
        parser.add_argument("--fs-license", default="~/license.txt", help="FreeSurfer license file")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 8)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 8)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 24:00:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for qsiprep pipeline", file=sys.stderr)
            sys.exit(1)

        nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
        mem_per_cpu_gb = args.mem_per_cpu_gb if args.mem_per_cpu_gb is not None else self.default_resources["mem_per_cpu_gb"]
        time = args.time if args.time is not None else self.default_resources["time"]

        n_subjects = count_subjects(dataset_config["subjects_file"])
        mem_mb = int(nthreads * mem_per_cpu_gb * 1000 * 0.9)

        image_path = str(Path(dataset_config["image_dir"]) / f"qsiprep_{args.version}.sif")
        fs_license = str(Path(args.fs_license).expanduser())

        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/qsiprep_{dataset_name}_{args.version}"
        log_dir = f"{dataset_config['bids_dir']}/derivatives/qsiprep_{args.version}/logs"

        if dataset_config.get("mail_user"):
            mail_line = f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
        else:
            mail_line = ""

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
            "work_dir": work_dir,
            "fs_license": fs_license,
            "qsiprep_version": args.version,
            "mem_mb": mem_mb,
            "output_resolution": args.output_resolution,
            "qsiprep_args": args.qsiprep_args,
        }


register(QsiprepPipeline())
```

**Step 5: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_qsiprep.py -v`
Expected: 7 PASS

**Step 6: Commit**

```bash
git add src/neuro_workflow/pipelines/qsiprep.py src/neuro_workflow/templates/qsiprep.sbatch tests/pipelines/test_qsiprep.py
git commit -m "feat: add qsiprep pipeline"
```

---

## Task 3: FSQC Pipeline

**Files:**
- Create: `src/neuro_workflow/templates/fsqc.sbatch`
- Create: `src/neuro_workflow/pipelines/fsqc.py`
- Test: `tests/pipelines/test_fsqc.py`

**Step 1: Write the failing tests**

Create `tests/pipelines/test_fsqc.py`:

```python
import sys
from argparse import Namespace
from unittest.mock import patch

from neuro_workflow.pipelines.fsqc import FsqcPipeline


def make_args(**overrides):
    defaults = {
        "version": "2.1.4",
        "freesurfer_dir": "/data/derivatives/freesurfer",
        "fsqc_args": "",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s01\ns02\n")
    return {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = FsqcPipeline()
    assert p.name == "fsqc"
    assert p.docker_uri == "docker://deepmi/fsqc"
    assert p.template_name == "fsqc.sbatch"


def test_default_resources():
    p = FsqcPipeline()
    assert p.default_resources["nthreads"] == 4
    assert p.default_resources["mem_per_cpu_gb"] == 8
    assert p.default_resources["time"] == "2-00:00:00"


def test_build_context_basic(tmp_path):
    p = FsqcPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("validation", config, args)
    assert ctx["dataset_name"] == "validation"
    assert ctx["freesurfer_dir"] == "/data/derivatives/freesurfer"
    assert ctx["image_path"] == "/images/fsqc_2.1.4.sif"
    # fsqc runs as single job, not array — subjects_list is built from file
    assert "sub-s01 sub-s02" == ctx["subjects_list"]


def test_build_context_version_required(tmp_path):
    p = FsqcPipeline()
    config = make_config(tmp_path)
    args = make_args(version=None)
    with patch.object(sys, "exit", side_effect=SystemExit):
        try:
            p.build_context("validation", config, args)
        except SystemExit:
            pass


def test_build_context_freesurfer_dir_required(tmp_path):
    p = FsqcPipeline()
    config = make_config(tmp_path)
    args = make_args(freesurfer_dir=None)
    with patch.object(sys, "exit", side_effect=SystemExit):
        try:
            p.build_context("validation", config, args)
        except SystemExit:
            pass


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = FsqcPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("validation", config, args)
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)
    assert "xvfb-run" in script
    assert "fsqc" in script
    assert "--subjects sub-s01 sub-s02" in script
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_fsqc.py -v`
Expected: FAIL (import error)

**Step 3: Write the sbatch template**

Create `src/neuro_workflow/templates/fsqc.sbatch`:

```bash
#!/bin/bash
#SBATCH -J fsqc_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%j.out
#SBATCH -e {log_dir}/%x-%j.err
{mail_line}

export SINGULARITYENV_DISPLAY=""
export SINGULARITYENV_LIBGL_ALWAYS_INDIRECT=1
export SINGULARITYENV_MESA_GL_VERSION_OVERRIDE=3.3

FSQC_IMG="{image_path}"

mkdir -p "{output_dir}"

singularity exec \
  --cleanenv \
  --writable-tmpfs \
  -B {freesurfer_dir}:/data \
  -B {output_dir}:/out \
  "$FSQC_IMG" \
  xvfb-run -a -s "-screen 0 1024x768x24 -ac +extension GLX +render -noreset" \
  /app/fsqc/run_fsqc \
  --subjects_dir /data \
  --output_dir /out \
  --subjects {subjects_list} \
  --screenshots-html \
  --surfaces-html \
  --skullstrip-html \
  --fornix-html \
  --outlier \
  {fsqc_args}

exitcode=$?
echo "FSQC finished with exit code $exitcode"
exit $exitcode
```

**Step 4: Write the pipeline module**

Create `src/neuro_workflow/pipelines/fsqc.py`:

```python
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import load_subjects
from neuro_workflow.pipelines.base import register


class FsqcPipeline:
    name = "fsqc"
    docker_uri = "docker://deepmi/fsqc"
    template_name = "fsqc.sbatch"
    default_resources = {
        "nthreads": 4,
        "mem_per_cpu_gb": 8,
        "time": "2-00:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="FSQC version tag (e.g. 2.1.4)")
        parser.add_argument("--freesurfer-dir", default=None, help="Path to FreeSurfer derivatives directory")
        parser.add_argument("--fsqc-args", default="", help="Additional FSQC arguments")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 4)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 8)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 2-00:00:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for fsqc pipeline", file=sys.stderr)
            sys.exit(1)
        if not getattr(args, "freesurfer_dir", None):
            print("Error: --freesurfer-dir is required for fsqc pipeline", file=sys.stderr)
            sys.exit(1)

        nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
        mem_per_cpu_gb = args.mem_per_cpu_gb if args.mem_per_cpu_gb is not None else self.default_resources["mem_per_cpu_gb"]
        time = args.time if args.time is not None else self.default_resources["time"]

        image_path = str(Path(dataset_config["image_dir"]) / f"fsqc_{args.version}.sif")

        # Build subjects list with sub- prefix
        subjects = load_subjects(dataset_config["subjects_file"])
        subjects_list = " ".join(
            f"sub-{s}" if not s.startswith("sub-") else s for s in subjects
        )

        output_dir = f"{dataset_config['bids_dir']}/derivatives/fsqc"
        log_dir = f"{output_dir}/logs"

        if dataset_config.get("mail_user"):
            mail_line = f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
        else:
            mail_line = ""

        return {
            "dataset_name": dataset_name,
            "time": time,
            "nthreads": nthreads,
            "mem_per_cpu_gb": mem_per_cpu_gb,
            "partition": dataset_config["partition"],
            "log_dir": log_dir,
            "mail_line": mail_line,
            "image_path": image_path,
            "freesurfer_dir": args.freesurfer_dir,
            "output_dir": output_dir,
            "subjects_list": subjects_list,
            "fsqc_args": args.fsqc_args,
        }


register(FsqcPipeline())
```

**Step 5: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_fsqc.py -v`
Expected: 6 PASS

**Step 6: Commit**

```bash
git add src/neuro_workflow/pipelines/fsqc.py src/neuro_workflow/templates/fsqc.sbatch tests/pipelines/test_fsqc.py
git commit -m "feat: add fsqc pipeline"
```

---

## Task 4: FreeSurfer Pipeline (Deprecated)

**Files:**
- Create: `src/neuro_workflow/templates/freesurfer.sbatch`
- Create: `src/neuro_workflow/pipelines/freesurfer.py`
- Test: `tests/pipelines/test_freesurfer.py`

**Step 1: Write the failing tests**

Create `tests/pipelines/test_freesurfer.py`:

```python
import sys
from argparse import Namespace
from unittest.mock import patch

from neuro_workflow.pipelines.freesurfer import FreesurferPipeline


def make_csv(tmp_path):
    """Create a CSV subjects file: subject_id,ses_t1,run_t1,ses_t2,run_t2"""
    csv = tmp_path / "subs_fs.csv"
    csv.write_text("s03,ses-01,1,ses-01,1\ns04,ses-02,1,,\n")
    return str(csv)


def make_args(tmp_path, **overrides):
    defaults = {
        "version": "8.1.0",
        "subjects_file": make_csv(tmp_path),
        "fs_license": "~/license.txt",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    return {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(tmp_path / "subs.txt"),  # default, overridden by --subjects-file
        "partition": "russpold",
        "image_dir": "/images",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = FreesurferPipeline()
    assert p.name == "freesurfer"
    assert p.template_name == "freesurfer.sbatch"


def test_default_resources():
    p = FreesurferPipeline()
    assert p.default_resources["nthreads"] == 4
    assert p.default_resources["mem_per_cpu_gb"] == 16
    assert p.default_resources["time"] == "4-00:00:00"


def test_build_context_basic(tmp_path):
    p = FreesurferPipeline()
    config = make_config(tmp_path)
    args = make_args(tmp_path)
    ctx = p.build_context("discovery", config, args)
    assert ctx["dataset_name"] == "discovery"
    assert ctx["n_subjects"] == 2
    assert ctx["image_path"] == "/images/freesurfer_8.1.0.sif"
    assert ctx["fs_subjects_file"] == args.subjects_file


def test_build_context_version_required(tmp_path):
    p = FreesurferPipeline()
    config = make_config(tmp_path)
    args = make_args(tmp_path, version=None)
    with patch.object(sys, "exit", side_effect=SystemExit):
        try:
            p.build_context("discovery", config, args)
        except SystemExit:
            pass


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = FreesurferPipeline()
    config = make_config(tmp_path)
    args = make_args(tmp_path)
    ctx = p.build_context("discovery", config, args)
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)
    assert "recon-all" in script
    assert "freesurfer_8.1.0" in script
    assert "SLURM_ARRAY_TASK_ID" in script
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_freesurfer.py -v`
Expected: FAIL (import error)

**Step 3: Write the sbatch template**

Create `src/neuro_workflow/templates/freesurfer.sbatch`:

```bash
#!/bin/bash
#SBATCH -J freesurfer_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_subjects}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

SINGULARITY_IMG="{image_path}"
export FS_LICENSE="{fs_license}"

# Read subject info from CSV: subject_id,ses_t1,run_t1,ses_t2,run_t2
line=$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" {fs_subjects_file})
IFS=',' read -r subject_id ses_t1 run_t1 ses_t2 run_t2 <<< "$line"
subject="sub-${{subject_id}}"

t1w_path="{bids_dir}/${{subject}}/${{ses_t1}}/anat/${{subject}}_${{ses_t1}}_run-${{run_t1}}_T1w.nii.gz"

DERIVS_DIR="{bids_dir}/derivatives/freesurfer_{freesurfer_version}"
mkdir -p "$DERIVS_DIR"

if [ -n "$ses_t2" ]; then
    t2w_path="{bids_dir}/${{subject}}/${{ses_t2}}/anat/${{subject}}_${{ses_t2}}_run-${{run_t2}}_T2w.nii.gz"
    singularity exec --bind {bids_dir}:{bids_dir},${{FS_LICENSE}}:${{FS_LICENSE}} \
        "$SINGULARITY_IMG" recon-all \
        -i "$t1w_path" \
        -T2 "$t2w_path" \
        -s "$subject" \
        -sd "$DERIVS_DIR" \
        -all
else
    singularity exec --bind {bids_dir}:{bids_dir},${{FS_LICENSE}}:${{FS_LICENSE}} \
        "$SINGULARITY_IMG" recon-all \
        -i "$t1w_path" \
        -s "$subject" \
        -sd "$DERIVS_DIR" \
        -all
fi

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
```

**Step 4: Write the pipeline module**

Create `src/neuro_workflow/pipelines/freesurfer.py`:

```python
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.pipelines.base import register


class FreesurferPipeline:
    name = "freesurfer"
    docker_uri = ""  # local SIF, no pull
    template_name = "freesurfer.sbatch"
    default_resources = {
        "nthreads": 4,
        "mem_per_cpu_gb": 16,
        "time": "4-00:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="FreeSurfer version tag (e.g. 8.1.0)")
        parser.add_argument("--subjects-file", default=None, help="CSV file: subject_id,ses_t1,run_t1,ses_t2,run_t2")
        parser.add_argument("--fs-license", default="~/license.txt", help="FreeSurfer license file")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 4)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 16)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 4-00:00:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for freesurfer pipeline", file=sys.stderr)
            sys.exit(1)

        nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
        mem_per_cpu_gb = args.mem_per_cpu_gb if args.mem_per_cpu_gb is not None else self.default_resources["mem_per_cpu_gb"]
        time = args.time if args.time is not None else self.default_resources["time"]

        # Use --subjects-file if provided, otherwise fall back to dataset subjects_file
        fs_subjects_file = getattr(args, "subjects_file", None) or dataset_config["subjects_file"]

        # Count lines in the CSV to determine array size
        n_subjects = sum(1 for line in open(fs_subjects_file) if line.strip())

        image_path = str(Path(dataset_config["image_dir"]) / f"freesurfer_{args.version}.sif")
        fs_license = str(Path(args.fs_license).expanduser())
        log_dir = f"{dataset_config['bids_dir']}/derivatives/freesurfer_{args.version}/logs"

        if dataset_config.get("mail_user"):
            mail_line = f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
        else:
            mail_line = ""

        return {
            "dataset_name": dataset_name,
            "time": time,
            "n_subjects": n_subjects,
            "nthreads": nthreads,
            "mem_per_cpu_gb": mem_per_cpu_gb,
            "partition": dataset_config["partition"],
            "log_dir": log_dir,
            "mail_line": mail_line,
            "image_path": image_path,
            "bids_dir": dataset_config["bids_dir"],
            "fs_license": fs_license,
            "fs_subjects_file": fs_subjects_file,
            "freesurfer_version": args.version,
        }


register(FreesurferPipeline())
```

**Step 5: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_freesurfer.py -v`
Expected: 5 PASS

**Step 6: Commit**

```bash
git add src/neuro_workflow/pipelines/freesurfer.py src/neuro_workflow/templates/freesurfer.sbatch tests/pipelines/test_freesurfer.py
git commit -m "feat: add freesurfer pipeline (deprecated)"
```

---

## Task 5: Happy Pipeline

The happy pipeline is unique: it arrays over scans (not subjects), requires auto-discovery of BOLD+physio pairs, and writes a scan list file.

**Files:**
- Create: `src/neuro_workflow/templates/happy.sbatch`
- Create: `src/neuro_workflow/pipelines/happy.py`
- Test: `tests/pipelines/test_happy.py`

**Step 1: Write the failing tests**

Create `tests/pipelines/test_happy.py`:

```python
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from neuro_workflow.pipelines.happy import HappyPipeline


def make_bids_tree(tmp_path):
    """Create a minimal BIDS tree with BOLD + physio pairs for happy discovery."""
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)

    # Create a BOLD echo file
    (func / "sub-s01_ses-01_task-rest_run-1_echo-2_bold.nii.gz").touch()
    (func / "sub-s01_ses-01_task-rest_run-1_echo-2_bold.json").touch()

    # Create physio files
    (func / "sub-s01_ses-01_task-rest_run-1_recording-cardiac_physio.tsv.gz").touch()
    (func / "sub-s01_ses-01_task-rest_run-1_recording-cardiac_physio.json").touch()

    return str(bids)


def make_args(**overrides):
    defaults = {
        "version": "3.1.8",
        "happy_args": "",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    bids_dir = make_bids_tree(tmp_path)
    subs = tmp_path / "subs.txt"
    subs.write_text("s01\n")
    return {
        "bids_dir": bids_dir,
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = HappyPipeline()
    assert p.name == "happy"
    assert p.docker_uri == "docker://fredericklab/rapidtide"
    assert p.template_name == "happy.sbatch"


def test_default_resources():
    p = HappyPipeline()
    assert p.default_resources["nthreads"] == 4
    assert p.default_resources["mem_per_cpu_gb"] == 2
    assert p.default_resources["time"] == "00:10:00"


def test_build_context_discovers_scans(tmp_path):
    p = HappyPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("discovery", config, args)
    assert ctx["n_scans"] == 1
    # scan_list_file should have been written
    scan_list = Path(ctx["scan_list_file"])
    assert scan_list.exists()
    lines = scan_list.read_text().strip().split("\n")
    assert len(lines) == 1
    assert "sub-s01_ses-01_task-rest_run-1_echo-2_bold.nii.gz" in lines[0]


def test_build_context_version_required(tmp_path):
    p = HappyPipeline()
    config = make_config(tmp_path)
    args = make_args(version=None)
    with patch.object(sys, "exit", side_effect=SystemExit):
        try:
            p.build_context("discovery", config, args)
        except SystemExit:
            pass


def test_build_context_no_scans_found(tmp_path):
    """Empty BIDS dir should cause exit."""
    p = HappyPipeline()
    bids = tmp_path / "empty_bids"
    bids.mkdir()
    subs = tmp_path / "subs.txt"
    subs.write_text("s01\n")
    config = {
        "bids_dir": str(bids),
        "subjects_file": str(subs),
        "partition": "russpold",
        "image_dir": "/images",
        "mail_user": None,
    }
    args = make_args()
    with patch.object(sys, "exit", side_effect=SystemExit):
        try:
            p.build_context("discovery", config, args)
        except SystemExit:
            pass


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = HappyPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("discovery", config, args)
    script = render_template(TEMPLATE_DIR / p.template_name, ctx)
    assert "happy" in script.lower()
    assert "SLURM_ARRAY_TASK_ID" in script
    assert "--cardiacfile" in script
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_happy.py -v`
Expected: FAIL (import error)

**Step 3: Write the sbatch template**

Create `src/neuro_workflow/templates/happy.sbatch`:

```bash
#!/bin/bash
#SBATCH -J happy_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_scans}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

set -euo pipefail

LIST_FILE="{scan_list_file}"
LINE="$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" "$LIST_FILE")"

if [ -z "$LINE" ]; then
    echo "ERROR: No data at line ${{SLURM_ARRAY_TASK_ID}} in ${{LIST_FILE}}" >&2
    exit 1
fi

read -r BOLD_FILE BOLD_JSON PHYS_TSV PHYS_JSON OUT_FILE <<< "$LINE"
OUT_PREFIX="${{OUT_FILE%.nii.gz}}"

# Skip if output exists
if compgen -G "${{OUT_PREFIX}}_"* > /dev/null 2>&1; then
    echo "SKIPPED: Output already exists for ${{BOLD_FILE}}"
    exit 0
fi

mkdir -p "$(dirname "$OUT_PREFIX")"

CONTAINER="{image_path}"

singularity exec "$CONTAINER" happy \
    --cardiacfile "${{PHYS_TSV}}:cardiac" \
    --temporalregression \
    {happy_args} \
    "$BOLD_FILE" \
    "$BOLD_JSON" \
    "$OUT_PREFIX"

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} finished with exit code $exitcode"
exit $exitcode
```

**Step 4: Write the pipeline module**

Create `src/neuro_workflow/pipelines/happy.py`:

```python
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.pipelines.base import register


def _discover_scans(bids_dir: str) -> list[dict]:
    """Discover BOLD echo + physio file pairs in a BIDS directory.

    Returns a list of dicts with keys: bold, bold_json, phys_tsv, phys_json, output.
    """
    bids = Path(bids_dir)
    scans = []

    for nifti in sorted(bids.glob("sub-s*/ses-*/func/*_task-rest_*_echo-*_bold.nii.gz")):
        func_dir = nifti.parent
        bold_json = nifti.with_suffix("").with_suffix(".json")  # strip .nii.gz, add .json

        # Derive the run-level prefix (before _echo-)
        base = nifti.name.split("_echo-")[0]
        phys_tsv = func_dir / f"{base}_recording-cardiac_physio.tsv.gz"
        phys_json = func_dir / f"{base}_recording-cardiac_physio.json"

        if not bold_json.exists() or not phys_tsv.exists() or not phys_json.exists():
            continue

        # Build output path mirroring BIDS structure under derivatives/happy
        rel = nifti.relative_to(bids)
        output = Path(bids_dir) / "derivatives" / "happy" / rel

        scans.append({
            "bold": str(nifti),
            "bold_json": str(bold_json),
            "phys_tsv": str(phys_tsv),
            "phys_json": str(phys_json),
            "output": str(output),
        })

    return scans


class HappyPipeline:
    name = "happy"
    docker_uri = "docker://fredericklab/rapidtide"
    template_name = "happy.sbatch"
    default_resources = {
        "nthreads": 4,
        "mem_per_cpu_gb": 2,
        "time": "00:10:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="Rapidtide version tag (e.g. 3.1.8)")
        parser.add_argument("--happy-args", default="", help="Additional happy arguments")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 4)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 2)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 00:10:00)")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for happy pipeline", file=sys.stderr)
            sys.exit(1)

        nthreads = args.nthreads if args.nthreads is not None else self.default_resources["nthreads"]
        mem_per_cpu_gb = args.mem_per_cpu_gb if args.mem_per_cpu_gb is not None else self.default_resources["mem_per_cpu_gb"]
        time = args.time if args.time is not None else self.default_resources["time"]

        bids_dir = dataset_config["bids_dir"]
        scans = _discover_scans(bids_dir)

        if not scans:
            print("Error: no BOLD+physio scan pairs found in BIDS directory", file=sys.stderr)
            sys.exit(1)

        # Write scan list
        deriv_dir = Path(bids_dir) / "derivatives" / "happy"
        deriv_dir.mkdir(parents=True, exist_ok=True)
        scan_list_file = deriv_dir / "scan_list.txt"
        with open(scan_list_file, "w") as f:
            for s in scans:
                f.write(f"{s['bold']} {s['bold_json']} {s['phys_tsv']} {s['phys_json']} {s['output']}\n")

        image_path = str(Path(dataset_config["image_dir"]) / f"rapidtide_{args.version}")
        log_dir = str(deriv_dir / "logs")

        if dataset_config.get("mail_user"):
            mail_line = f"#SBATCH --mail-user={dataset_config['mail_user']}\n#SBATCH --mail-type=ALL"
        else:
            mail_line = ""

        return {
            "dataset_name": dataset_name,
            "time": time,
            "n_scans": len(scans),
            "nthreads": nthreads,
            "mem_per_cpu_gb": mem_per_cpu_gb,
            "partition": dataset_config["partition"],
            "log_dir": log_dir,
            "mail_line": mail_line,
            "scan_list_file": str(scan_list_file),
            "image_path": image_path,
            "happy_args": args.happy_args,
        }


register(HappyPipeline())
```

**Step 5: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/pipelines/test_happy.py -v`
Expected: 6 PASS

**Step 6: Commit**

```bash
git add src/neuro_workflow/pipelines/happy.py src/neuro_workflow/templates/happy.sbatch tests/pipelines/test_happy.py
git commit -m "feat: add happy pipeline with auto-scan discovery"
```

---

## Task 6: Register New Pipelines in CLI + Add QA Subcommand

**Files:**
- Modify: `src/neuro_workflow/cli.py`
- Test: `tests/test_cli.py` (add new tests)

**Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_qa_subcommand_no_args(capsys):
    """qa subcommand without required args should fail."""
    import sys
    from unittest.mock import patch
    with patch("sys.argv", ["neuro-run", "qa"]):
        with pytest.raises(SystemExit):
            main()


def test_qa_unknown_command(capsys):
    """qa with unknown command should print error."""
    import sys
    from unittest.mock import patch
    with patch("sys.argv", ["neuro-run", "qa", "nonexistent", "discovery"]):
        with pytest.raises(SystemExit):
            main()
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/test_cli.py -v`
Expected: new tests FAIL

**Step 3: Update cli.py**

Modify `src/neuro_workflow/cli.py` to import new pipelines and add QA subcommand:

```python
import argparse
import sys
from pathlib import Path

from neuro_workflow.core.config import save_dataset, get_dataset, load_datasets
from neuro_workflow.core.image import ensure_image
from neuro_workflow.core.slurm import render_template, submit_sbatch
from neuro_workflow.pipelines.base import get_pipeline, list_pipelines, TEMPLATE_DIR
from neuro_workflow.qa.base import get_qa_command, list_qa_commands

# Import pipeline modules to trigger auto-registration
import neuro_workflow.pipelines.fmriprep  # noqa: F401
import neuro_workflow.pipelines.qsiprep  # noqa: F401
import neuro_workflow.pipelines.fsqc  # noqa: F401
import neuro_workflow.pipelines.freesurfer  # noqa: F401
import neuro_workflow.pipelines.happy  # noqa: F401


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


def cmd_qa(args):
    command = get_qa_command(args.qa_command)
    if command is None:
        available = ", ".join(list_qa_commands()) or "(none registered)"
        print(f"Error: unknown QA command '{args.qa_command}'. Available: {available}", file=sys.stderr)
        sys.exit(1)

    config = get_dataset(args.dataset)
    command.run(args.dataset, config, args)


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
    for pipeline in list_pipelines().values():
        pipeline.add_cli_args(show_p)
    show_p.set_defaults(func=cmd_show)

    # submit
    sub_p = subparsers.add_parser("submit", help="Submit a pipeline job to SLURM")
    sub_p.add_argument("pipeline", help="Pipeline name (e.g. fmriprep, qsiprep)")
    sub_p.add_argument("dataset", help="Dataset name to submit")
    for pipeline in list_pipelines().values():
        pipeline.add_cli_args(sub_p)
    sub_p.set_defaults(func=cmd_submit)

    # qa
    qa_p = subparsers.add_parser("qa", help="Run QA analysis scripts")
    qa_p.add_argument("qa_command", help="QA command name")
    qa_p.add_argument("dataset", help="Dataset name")
    for qa_cmd in list_qa_commands().values():
        qa_cmd.add_cli_args(qa_p)
    qa_p.set_defaults(func=cmd_qa)

    args = parser.parse_args()
    args.func(args)
```

**Step 4: Run all tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/ -v`
Expected: all tests PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/cli.py tests/test_cli.py
git commit -m "feat: register new pipelines and add qa subcommand to CLI"
```

---

## Task 7: neg-events QA Script

**Files:**
- Create: `src/neuro_workflow/qa/neg_events.py`
- Test: `tests/qa/test_neg_events.py`

**Step 1: Write the failing tests**

Create `tests/qa/test_neg_events.py`:

```python
from argparse import ArgumentParser, Namespace
from pathlib import Path
from io import StringIO

from neuro_workflow.qa.neg_events import NegEventsQa, find_monotonic_point


def test_find_monotonic_point_monotonic():
    import pandas as pd
    s = pd.Series([1.0, 2.0, 3.0])
    assert find_monotonic_point(s) == 0


def test_find_monotonic_point_non_monotonic():
    import pandas as pd
    s = pd.Series([5.0, 1.0, 2.0, 3.0])
    assert find_monotonic_point(s) == 1


def test_find_monotonic_point_never_monotonic():
    import pandas as pd
    s = pd.Series([3.0, 1.0, 3.0, 1.0])
    assert find_monotonic_point(s) is None


def test_qa_attributes():
    qa = NegEventsQa()
    assert qa.name == "neg-events"
    assert qa.description


def test_run_reports_non_monotonic(tmp_path, capsys):
    """Create event files and verify run() reports non-monotonic ones."""
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)

    # Monotonic file
    (func / "sub-s01_ses-01_task-rest_events.tsv").write_text(
        "onset\tduration\n1.0\t1.0\n2.0\t1.0\n3.0\t1.0\n"
    )

    # Non-monotonic file
    (func / "sub-s01_ses-01_task-flanker_events.tsv").write_text(
        "onset\tduration\n5.0\t1.0\n1.0\t1.0\n2.0\t1.0\n"
    )

    config = {"bids_dir": str(bids)}
    args = Namespace()
    qa = NegEventsQa()
    qa.run("discovery", config, args)

    captured = capsys.readouterr()
    assert "flanker" in captured.out
    assert "1" in captured.out  # trim index
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_neg_events.py -v`
Expected: FAIL (import error)

**Step 3: Write the implementation**

Create `src/neuro_workflow/qa/neg_events.py`:

```python
from __future__ import annotations

from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa


def find_monotonic_point(onset_series) -> Optional[int]:
    """Find the index where the onset series becomes monotonically increasing."""
    for i in range(len(onset_series)):
        if onset_series.iloc[i:].is_monotonic_increasing:
            return i
    return None


class NegEventsQa:
    name = "neg-events"
    description = "Report event files with non-monotonically increasing onsets"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        pass  # no extra args needed

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if pd is None:
            print("Error: 'pandas' required for 'neg-events'. Install with: uv pip install -e \".[qa]\"")
            return

        bids_dir = Path(dataset_config["bids_dir"])
        all_files = list(bids_dir.glob("sub-*/ses-*/func/*event*.tsv"))

        print(f"Found {len(all_files)} event files total")
        print("\nNon-monotonic event files and their trim points:")
        print("=" * 60)

        count = 0
        for file_path in sorted(all_files):
            try:
                df = pd.read_csv(file_path, sep="\t")
                if "onset" not in df.columns:
                    print(f"WARNING: {file_path.name} - no 'onset' column found")
                    continue
                if not df["onset"].is_monotonic_increasing:
                    monotonic_index = find_monotonic_point(df["onset"])
                    count += 1
                    print(f"{file_path.name}")
                    print(f"  Path: {file_path}")
                    print(f"  Trim index: {monotonic_index}")
                    print(f"  Total rows: {len(df)}")
                    if monotonic_index is not None:
                        print(f"  Rows to keep: {len(df) - monotonic_index}")
                    print()
            except Exception as e:
                print(f"ERROR reading {file_path.name}: {e}")

        print(f"\nSummary: {count} files with non-monotonic onsets")


register_qa(NegEventsQa())
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_neg_events.py -v`
Expected: 5 PASS

**Step 5: Update CLI import**

Add to `src/neuro_workflow/cli.py` imports:

```python
import neuro_workflow.qa.neg_events  # noqa: F401
```

**Step 6: Commit**

```bash
git add src/neuro_workflow/qa/neg_events.py tests/qa/test_neg_events.py src/neuro_workflow/cli.py
git commit -m "feat: add neg-events QA command"
```

---

## Task 8: breaks QA Script

**Files:**
- Create: `src/neuro_workflow/qa/breaks.py`
- Test: `tests/qa/test_breaks.py`

**Step 1: Write the failing tests**

Create `tests/qa/test_breaks.py`:

```python
import json
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.qa.breaks import (
    BreaksQa,
    extract_task_name_from_filename,
    analyze_stimulus_for_performance_feedback,
)


def test_extract_task_name():
    assert extract_task_name_from_filename("stop_signal__fmri_rest.csv") == "stopSignal"
    assert extract_task_name_from_filename("flanker__fmri.csv") == "flanker"


def test_analyze_stimulus_feedback():
    indicators, has_feedback = analyze_stimulus_for_performance_feedback(
        "Your accuracy was 85%"
    )
    assert has_feedback is True
    assert "accuracy" in indicators


def test_analyze_stimulus_no_feedback():
    indicators, has_feedback = analyze_stimulus_for_performance_feedback(
        "Press any key to continue"
    )
    assert has_feedback is False
    assert indicators == []


def test_analyze_stimulus_nan():
    import math
    indicators, has_feedback = analyze_stimulus_for_performance_feedback(float("nan"))
    assert has_feedback is False


def test_qa_attributes():
    qa = BreaksQa()
    assert qa.name == "breaks"
    assert qa.description


def test_run_produces_json(tmp_path):
    """Create a minimal behavioral file and verify JSON output."""
    beh_dir = tmp_path / "behavioral"
    sub_dir = beh_dir / "s01" / "ses-01"
    sub_dir.mkdir(parents=True)
    csv_file = sub_dir / "stop_signal__fmri.csv"
    csv_file.write_text(
        "trial_id,stimulus\n"
        "test_trial,fixation\n"
        "test_feedback,Your accuracy was 85%\n"
    )

    output_dir = tmp_path / "output"
    config = {"bids_dir": str(tmp_path / "bids")}
    args = Namespace(behavioral_dir=str(beh_dir), output_dir=str(output_dir))
    qa = BreaksQa()
    qa.run("discovery", config, args)

    master = output_dir / "break_analysis_master.json"
    assert master.exists()
    data = json.loads(master.read_text())
    assert "break_feedback_analysis" in data
    assert len(data["break_feedback_analysis"]) >= 1
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_breaks.py -v`
Expected: FAIL

**Step 3: Write the implementation**

Create `src/neuro_workflow/qa/breaks.py`:

Port the logic from `custom_scripts/run_breaks.py` into the QaCommand pattern. Keep all constants (FEEDBACK_TRIAL_IDS, PERFORMANCE_FEEDBACK_STRINGS, TASK_NAME_MAPPING) and helper functions, but parameterize paths via CLI args.

```python
from __future__ import annotations

import json
import logging
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa

logger = logging.getLogger(__name__)

FEEDBACK_TRIAL_IDS = frozenset([
    "test_feedback", "feedback_block",
    "practice-no-stop-feedback", "practice-stop-feedback",
])

PERFORMANCE_FEEDBACK_STRINGS = frozenset([
    "accuracy", "responding", "slowly", "Remember:", "simply",
])

TASK_NAME_MAPPING = {
    'stop_signal': 'stopSignal',
    'stop_signal_with_flanker': 'stopSignalWFlanker',
    'spatial_switching': 'spatialTS',
    'spatial_task_switching': 'spatialTS',
    'cued_task_switching': 'cuedTS',
    'n_back': 'nBack',
    'directed_forgetting': 'directedForgetting',
    'flanker': 'flanker',
    'go_nogo': 'goNogo',
    'shape_matching': 'shapeMatching',
    'stop_signal_with_directed_forgetting': 'stopSignalWDirectedForgetting',
    'directed_forgetting_with_flanker': 'directedForgettingWFlanker',
    'cued_switching': 'cuedTS',
    'directed_forgetting_with_cued_task_switching': 'directedForgettingWCuedTS',
    'cued_task_switching_with_directed_forgetting': 'directedForgettingWCuedTS',
    'spatial_task_switching_with_cued_task_switching': 'spatialTSWCuedTS',
    'flanker_with_shape_matching': 'flankerWShapeMatching',
    'cued_task_switching_with_flanker': 'cuedTSWFlanker',
    'spatial_task_switching_with_shape_matching': 'spatialTSWShapeMatching',
    'shape_matching_with_spatial_task_switching': 'spatialTSWShapeMatching',
    'n_back_with_shape_matching': 'nBackWShapeMatching',
    'n_back_with_spatial_task_switching': 'nBackWSpatialTS',
    'flanker_with_cued_task_switching': 'cuedTSWFlanker',
    'shape_matching_with_cued_task_switching': 'shapeMatchingWCuedTS',
}


def extract_task_name_from_filename(filename: str) -> Optional[str]:
    base_name = filename.split("__fmri")[0] if "__fmri" in filename else filename.rsplit('.', 1)[0]
    if "_single_task_network" in base_name:
        base_name = base_name.split("_single_task_network")[0]
    elif "task-" in base_name:
        for part in base_name.split('_'):
            if part.startswith("task-"):
                base_name = part.replace("task-", "").replace("-", "_")
                break
    return TASK_NAME_MAPPING.get(base_name, base_name)


def analyze_stimulus_for_performance_feedback(stimulus: Union[str, float, None]) -> tuple:
    if not isinstance(stimulus, str) or (isinstance(stimulus, float) and str(stimulus) == "nan"):
        return [], False
    try:
        if pd is not None and pd.isna(stimulus):
            return [], False
    except (TypeError, ValueError):
        pass
    if not isinstance(stimulus, str):
        return [], False
    indicators = [ind for ind in PERFORMANCE_FEEDBACK_STRINGS if ind.lower() in stimulus.lower()]
    return indicators, len(indicators) > 0


def _extract_feedback_data(file_path: Path) -> List[Dict[str, Any]]:
    subject = file_path.parent.parent.name
    session = file_path.parent.name
    filename = file_path.name

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return []

    if not {'trial_id', 'stimulus'}.issubset(df.columns):
        return []

    test_mask = df['trial_id'] == 'test_trial'
    if test_mask.any():
        start_idx = test_mask.idxmax()
        df = df.iloc[df.index.get_loc(start_idx):]

    feedback_rows = df[df['trial_id'].isin(FEEDBACK_TRIAL_IDS)]
    if feedback_rows.empty:
        return []

    task_name = extract_task_name_from_filename(filename)

    # Dynamic block numbering
    block_counters: Dict[str, int] = {}
    block_numbers: Dict[int, int] = {}
    for idx, row in feedback_rows.iterrows():
        tid = row['trial_id']
        block_counters[tid] = block_counters.get(tid, 0) + 1
        block_numbers[idx] = block_counters[tid]

    results = []
    for idx, row in feedback_rows.iterrows():
        indicators, has_feedback = analyze_stimulus_for_performance_feedback(row['stimulus'])
        sub_prefix = subject if subject.startswith('sub-') else f"sub-{subject}"
        results.append({
            "subject": sub_prefix,
            "session": session,
            "filename": filename,
            "task_name": task_name,
            "row_index": int(idx),
            "trial_id": row['trial_id'],
            "block_number": block_numbers.get(idx),
            "stimulus_content": str(row['stimulus']) if pd.notna(row['stimulus']) else "",
            "performance_indicators": indicators,
            "has_performance_feedback": has_feedback,
        })
    return results


class BreaksQa:
    name = "breaks"
    description = "Analyze behavioral data for breaks with performance feedback"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--behavioral-dir", required=False, help="Path to behavioral data directory")
        parser.add_argument("--output-dir", default="data", help="Output directory for JSON results")

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if pd is None:
            print("Error: 'pandas' required for 'breaks'. Install with: uv pip install -e \".[qa]\"")
            return

        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        beh_dir = Path(getattr(args, "behavioral_dir", None) or "")
        if not beh_dir.is_dir():
            print(f"Error: behavioral directory not found: {beh_dir}")
            return

        files = list(beh_dir.glob("s*/ses-*/*.csv"))
        if not files:
            print(f"No behavioral files found in {beh_dir}")
            return

        logger.info(f"Processing {len(files)} behavioral files...")
        all_results: List[Dict[str, Any]] = []
        for fp in files:
            all_results.extend(_extract_feedback_data(fp))

        if not all_results:
            print("No feedback data extracted")
            return

        output_dir = Path(getattr(args, "output_dir", "data"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Summary stats
        total_files = len({(r['subject'], r['session'], r['filename']) for r in all_results})
        perf_count = sum(r['has_performance_feedback'] for r in all_results)

        summary = {
            "total_files_processed": total_files,
            "total_feedback_rows": len(all_results),
            "rows_with_performance_feedback": perf_count,
        }

        master = {"break_feedback_analysis": all_results, "summary": summary}
        with open(output_dir / "break_analysis_master.json", "w") as f:
            json.dump(master, f, indent=2)

        perf_results = [r for r in all_results if r['has_performance_feedback']]
        filtered = {"break_with_performance_feedback": perf_results, "summary": summary}
        with open(output_dir / "break_analysis_with_performance_feedback.json", "w") as f:
            json.dump(filtered, f, indent=2)

        print(f"Saved results to {output_dir}")


register_qa(BreaksQa())
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_breaks.py -v`
Expected: 6 PASS

**Step 5: Update CLI import**

Add to `src/neuro_workflow/cli.py`:

```python
import neuro_workflow.qa.breaks  # noqa: F401
```

**Step 6: Commit**

```bash
git add src/neuro_workflow/qa/breaks.py tests/qa/test_breaks.py src/neuro_workflow/cli.py
git commit -m "feat: add breaks QA command"
```

---

## Task 9: global-signal QA Script

**Files:**
- Create: `src/neuro_workflow/qa/global_signal.py`
- Test: `tests/qa/test_global_signal.py`

**Step 1: Write the failing tests**

Create `tests/qa/test_global_signal.py`:

```python
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch, MagicMock
import numpy as np

from neuro_workflow.qa.global_signal import GlobalSignalQa, parse_bids_meta


def test_parse_bids_meta(tmp_path):
    p = tmp_path / "sub-s03_ses-01_task-rest_echo-2_bold.nii.gz"
    p.touch()
    meta = parse_bids_meta(p)
    assert meta["sub_val"] == 3
    assert meta["sub_str"] == "sub-s03"
    assert meta["ses_val"] == 1
    assert meta["task"] == "rest"


def test_qa_attributes():
    qa = GlobalSignalQa()
    assert qa.name == "global-signal"
    assert qa.description


def test_add_cli_args():
    from argparse import ArgumentParser
    qa = GlobalSignalQa()
    parser = ArgumentParser()
    qa.add_cli_args(parser)
    args = parser.parse_args(["--output-dir", "/tmp/out"])
    assert args.output_dir == "/tmp/out"
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_global_signal.py -v`
Expected: FAIL

**Step 3: Write the implementation**

Create `src/neuro_workflow/qa/global_signal.py`:

```python
from __future__ import annotations

import logging
import re
from argparse import ArgumentParser, Namespace
from pathlib import Path

try:
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    import numpy as np
    import nibabel as nib
except ImportError:
    plt = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa

logger = logging.getLogger(__name__)


def parse_bids_meta(path: Path) -> dict:
    sub_match = re.search(r'sub-s(\d+)', path.name)
    ses_match = re.search(r'ses-(\d+)', path.name)
    task_match = re.search(r'task-([a-zA-Z0-9]+)', path.name)
    return {
        'sub_val': int(sub_match.group(1)) if sub_match else 0,
        'sub_str': sub_match.group(0) if sub_match else "sub-unknown",
        'ses_val': int(ses_match.group(1)) if ses_match else 0,
        'task': task_match.group(1) if task_match else "unknown",
        'path': path,
    }


def _calculate_global_signal(nifti_path: Path):
    img = nib.load(str(nifti_path))
    data = img.get_fdata()
    return np.mean(data, axis=(0, 1, 2))


class GlobalSignalQa:
    name = "global-signal"
    description = "Calculate and plot global signal from echo-2 BOLD data"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--output-dir", default=None, help="Output directory for figures")

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if plt is None:
            print("Error: 'matplotlib', 'nibabel', 'numpy' required. Install with: uv pip install -e \".[qa]\"")
            return

        bids_dir = Path(dataset_config["bids_dir"])
        output_dir = Path(getattr(args, "output_dir", None) or f"{bids_dir}/derivatives/global_signal_figs")
        output_dir.mkdir(parents=True, exist_ok=True)

        all_files = list(bids_dir.glob("sub-s*/ses-*/func/*echo-2*nii.gz"))
        if not all_files:
            print("No echo-2 BOLD files found")
            return

        meta_list = [parse_bids_meta(f) for f in all_files]
        meta_list.sort(key=lambda x: (x['sub_val'], x['ses_val'], x['task']))

        ordered_subs = list(dict.fromkeys(m['sub_val'] for m in meta_list))
        pdf_path = output_dir / 'all_subjects_global_signal.pdf'

        with PdfPages(pdf_path) as pdf:
            for sub_val in ordered_subs:
                sub_files = [m for m in meta_list if m['sub_val'] == sub_val]
                sub_str = sub_files[0]['sub_str']
                num_runs = len(sub_files)
                logger.info(f'Processing {sub_str}: {num_runs} runs...')

                fig, axes = plt.subplots(num_runs, 1, figsize=(12, 2.5 * num_runs), squeeze=False)
                for i, (m, ax_arr) in enumerate(zip(sub_files, axes)):
                    ax = ax_arr[0]
                    try:
                        gs = _calculate_global_signal(m['path'])
                        ax.plot(gs, color='#1a5276', linewidth=1.0)
                        ax.axvline(x=7, color='#c0392b', linestyle='--', alpha=0.7, label='TR=7')
                        ax.set_title(f"ses-{m['ses_val']:02d} | task-{m['task']} | {m['path'].name}", fontsize=8)
                        ax.set_ylabel('Intensity', fontsize=7)
                        if i == num_runs - 1:
                            ax.set_xlabel('TR', fontsize=8)
                    except Exception as e:
                        logger.error(f'Error processing {m["path"].name}: {e}')

                plt.tight_layout()
                png_path = output_dir / f'{sub_str}_global_signal.png'
                fig.savefig(png_path, dpi=150)
                pdf.savefig(fig)
                plt.close()

        print(f'PDF created at: {pdf_path}')


register_qa(GlobalSignalQa())
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_global_signal.py -v`
Expected: 3 PASS

**Step 5: Update CLI import**

Add to `src/neuro_workflow/cli.py`:

```python
import neuro_workflow.qa.global_signal  # noqa: F401
```

**Step 6: Commit**

```bash
git add src/neuro_workflow/qa/global_signal.py tests/qa/test_global_signal.py src/neuro_workflow/cli.py
git commit -m "feat: add global-signal QA command"
```

---

## Task 10: outlier-report QA Script

This is the most complex QA command. It ports `run_network.py`, `run_report.py`, and `plotting_functions.py` into a single module with submodules.

**Files:**
- Create: `src/neuro_workflow/qa/outlier_report.py`
- Test: `tests/qa/test_outlier_report.py`

**Step 1: Write the failing tests**

Create `tests/qa/test_outlier_report.py`:

```python
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.qa.outlier_report import OutlierReportQa


def test_qa_attributes():
    qa = OutlierReportQa()
    assert qa.name == "outlier-report"
    assert qa.description


def test_add_cli_args():
    qa = OutlierReportQa()
    parser = ArgumentParser()
    qa.add_cli_args(parser)
    args = parser.parse_args([
        "--lev1-dirs", "/path/a", "/path/b",
        "--exclusions-file", "/path/excl.json",
        "--output-dir", "/output",
    ])
    assert args.lev1_dirs == ["/path/a", "/path/b"]
    assert args.exclusions_file == "/path/excl.json"
    assert args.output_dir == "/output"
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_outlier_report.py -v`
Expected: FAIL

**Step 3: Write the implementation**

Create `src/neuro_workflow/qa/outlier_report.py`. This is a large module — port the core logic from `run_network.py` and `plotting_functions.py`, keeping the same function signatures but parameterizing all paths.

```python
"""Outlier report QA command.

Ports run_network.py, run_report.py, and plotting_functions.py into the QA framework.
Generates VIF + outlier analysis figures and summary CSVs.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import re
import shutil
from argparse import ArgumentParser, Namespace
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import img2pdf
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import seaborn as sns
    from matplotlib.cm import get_cmap
    from matplotlib.colorbar import ColorbarBase
    from matplotlib.colors import Normalize
    from matplotlib.gridspec import GridSpec
    from nilearn import datasets, plotting
    from nilearn.image import load_img
except ImportError:
    plt = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa

logger = logging.getLogger(__name__)


# --- BIDS parsing ---

def parse_bids_entities(path: str) -> Dict[str, Optional[str]]:
    filename = os.path.basename(path)
    patterns = {
        'subject': re.compile(r'sub-s([^_]+)'),
        'session': re.compile(r'ses-([^_]+)'),
        'run': re.compile(r'run-([^_]+)'),
        'task': re.compile(r'task-([^_]+)'),
        'contrast': re.compile(r'contrast-(.+?)_(?:rtmodel-[^_]+_)?stat-'),
    }
    entities: Dict[str, Optional[str]] = {key: None for key in patterns}
    entities['sub_ses_key'] = None
    for key, pattern in patterns.items():
        match = pattern.search(filename)
        if match:
            entities[key] = match.group(1)
    if entities['subject'] and entities['session']:
        entities['sub_ses_key'] = f'sub-s{entities["subject"]}_ses-{entities["session"]}'
    return entities


# --- Data collection ---

def load_exclusions(exclusions_file: str) -> Set[str]:
    if not os.path.exists(exclusions_file):
        raise FileNotFoundError(f'Exclusions file not found: {exclusions_file}')
    with open(exclusions_file) as f:
        data = json.load(f)
    excluded = set()
    for key in ('fmriprep_exclusions', 'behavioral_exclusions'):
        for exc in data.get(key, []):
            excluded.add(f"{exc['subject']}_{exc['session']}_{exc['task']}_{exc['run']}")
    return excluded


def is_scan_excluded(path: str, exclusions: Set[str]) -> bool:
    if not exclusions:
        return False
    ent = parse_bids_entities(path)
    if not all(ent.get(k) for k in ['subject', 'session', 'task', 'run']):
        return False
    key = f"sub-s{ent['subject']}_ses-{ent['session']}_task-{ent['task']}_run-{ent['run']}"
    return key in exclusions


def find_nifti_files(base_dirs: List[str]) -> List[str]:
    all_files = []
    for base_dir in base_dirs:
        pattern = os.path.join(base_dir, 'sub-s*', 'task-*', 'indiv_contrasts', '*stat-effect-size.nii.gz')
        from glob import glob as gglob
        all_files.extend(gglob(pattern))
    return sorted(all_files)


def extract_vif_from_csv(csv_path: str) -> Dict[str, float]:
    try:
        df = pd.read_csv(csv_path)
        return dict(zip(df['contrast'], df['VIF']))
    except Exception:
        return {}


def find_vif_files(base_dirs: List[str]) -> Dict[str, Dict[str, float]]:
    from glob import glob as gglob
    all_vif = {}
    for base_dir in base_dirs:
        pattern = os.path.join(base_dir, 'sub-s*', 'task-*', 'quality_control', '*_desc-contrastVIFs.csv')
        for vif_file in gglob(pattern):
            ent = parse_bids_entities(vif_file)
            if ent['sub_ses_key'] and ent['task']:
                if ent['run']:
                    key = f'{ent["sub_ses_key"]}_run-{ent["run"]}_{ent["task"]}'
                else:
                    key = f'{ent["sub_ses_key"]}_{ent["task"]}'
                all_vif[key] = extract_vif_from_csv(vif_file)
    return all_vif


def group_paths_by_filename_pattern(file_paths: List[str]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    for path in file_paths:
        filename = os.path.basename(path)
        pattern = re.sub(r'sub-s[^_]+', 'sub-sXXX', filename)
        pattern = re.sub(r'ses-[^_]+', 'ses-XX', pattern)
        pattern = re.sub(r'run-[^_]+', 'run-X', pattern)
        grouped[pattern].append(path)
    return dict(sorted(grouped.items()))


def get_contrast_vif_labels(vif_data, nifti_paths, contrast_name):
    labels = []
    for path in nifti_paths:
        ent = parse_bids_entities(path)
        label = '(vif=?)'
        if ent['sub_ses_key'] and ent['task'] and ent['run']:
            vif_key = f'{ent["sub_ses_key"]}_run-{ent["run"]}_{ent["task"]}'
            if vif_key not in vif_data:
                vif_key = f'{ent["sub_ses_key"]}_{ent["task"]}'
            if vif_key in vif_data:
                contrast_only = ent.get('contrast', '')
                if contrast_only in vif_data[vif_key]:
                    label = f'(vif={vif_data[vif_key][contrast_only]:.2f})'
        labels.append(label)
    return labels


# --- Outlier computation ---

def get_outlier_voxel_percentages(nifti_paths, n_std=2):
    try:
        data = np.array([load_img(p).get_fdata() for p in nifti_paths])
    except Exception:
        return [0.0] * len(nifti_paths)
    mean = np.mean(data, axis=0)
    std = np.std(data, axis=0)
    lower = mean - n_std * std
    upper = mean + n_std * std
    epsilon = 1e-6
    valid_mask = np.isfinite(std) & (std > epsilon)
    percentages = []
    for subj_data in data:
        mask = np.isfinite(subj_data) & valid_mask
        outliers = (subj_data < lower) | (subj_data > upper)
        valid = np.sum(mask)
        percentages.append(100 * np.sum(outliers & mask) / valid if valid > 0 else 0.0)
    return percentages


def get_symmetric_percentile_bounds(nifti_paths, percentile=98):
    all_data = np.concatenate([load_img(p).get_fdata().ravel() for p in nifti_paths])
    all_data = all_data[np.isfinite(all_data)]
    if len(all_data) == 0:
        return 1.0
    high = np.percentile(np.abs(all_data), percentile)
    return high if high > 0 else 1.0


# --- Plotting ---

def _plot_subject_grid(subject_labels, vif_labels, nifti_paths, outlier_pcts, mni_mask, contrast_name, vmax, vmin, cbar_title, n_std):
    subject_sessions = {}
    for i, label in enumerate(subject_labels):
        match = re.match(r'(sub-s[^_\s]+)', label)
        if match:
            sid = match.group(1)
            subject_sessions.setdefault(sid, []).append(i)
    unique = sorted(subject_sessions)
    nrows = len(unique)
    ncols = max(len(v) for v in subject_sessions.values()) if unique else 1
    fig = plt.figure(figsize=(ncols * 2.0, nrows * 1.6 + 1.5))
    gs = GridSpec(nrows, ncols, figure=fig, wspace=1.0, hspace=0.4)
    fs = 9 if nrows <= 20 else 7 if nrows <= 50 else 5
    for row, sid in enumerate(unique):
        for col, idx in enumerate(subject_sessions[sid]):
            ax = fig.add_subplot(gs[row, col])
            display = plotting.plot_stat_map(nifti_paths[idx], display_mode='z', cut_coords=[5], colorbar=False, vmax=vmax, vmin=vmin, title=None, axes=ax, bg_img=None, annotate=False)
            display.add_contours(mni_mask, colors='greenyellow', linewidths=1.5)
            ax.set_title(f'{subject_labels[idx]}\n({outlier_pcts[idx]:.1f}% > {n_std}SD)\n{vif_labels[idx]}', fontsize=fs, pad=4)
    cbar_ax = fig.add_axes([0.92, 0.25, 0.015, 0.5])
    norm = Normalize(vmin=vmin, vmax=vmax)
    ColorbarBase(cbar_ax, cmap=get_cmap('cold_hot'), norm=norm).set_label(cbar_title, fontsize=10)
    fig.suptitle(contrast_name, fontsize=14, y=0.95 if nrows <= 5 else 0.93 if nrows <= 15 else 0.91)
    return fig


def _build_outlier_df(labels, pcts, contrast, task=None, contrast_only=None, sessions=None, vif_labels=None):
    data = {'subject_label': labels, 'image_outlier_percentage': pcts, 'contrast_name': [contrast] * len(labels)}
    if task:
        data['task_name'] = [task] * len(labels)
    if contrast_only:
        data['contrast_only'] = [contrast_only] * len(labels)
    if sessions:
        data['session_id'] = sessions
    if vif_labels:
        vifs = []
        for vl in vif_labels:
            m = re.search(r'\(vif=([\d\.]+)\)', vl)
            vifs.append(float(m.group(1)) if m else np.nan)
        data['VIF'] = vifs
    return pd.DataFrame(data)


def combine_pngs_to_pdf(png_files, pdf_path):
    if not png_files:
        return
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, 'wb') as f:
        f.write(img2pdf.convert([str(p) for p in png_files]))


def summarize_outlier_percentages(df_list, output_dir, temp_dir=None):
    if not df_list:
        return []
    if temp_dir is None:
        temp_dir = output_dir
    os.makedirs(output_dir, exist_ok=True)
    combined = pd.concat(df_list, ignore_index=True)

    fig1, ax1 = plt.subplots(figsize=(8, 5))
    sns.histplot(combined['image_outlier_percentage'], bins=30, kde=False, ax=ax1)
    ax1.set_title('Distribution of Outlier Percentages (All)')
    path1 = os.path.join(temp_dir, 'outlier_percentage_dist_all.png')
    fig1.savefig(path1, dpi=300)
    plt.close(fig1)

    g = sns.displot(combined, x='image_outlier_percentage', col='contrast_name', col_wrap=5, bins=20, facet_kws={'sharex': False, 'sharey': False}, height=3, aspect=1.2)
    path2 = os.path.join(temp_dir, 'outlier_percentage_dist_by_image.png')
    g.savefig(path2, dpi=300)
    plt.close(g.fig)

    combined.to_csv(os.path.join(output_dir, 'percent_outlier_data.csv'), index=False)
    return [path1, path2]


# --- Main pipeline ---

def make_input_dicts(base_dirs, exclusions):
    nifti_files = find_nifti_files(base_dirs)
    if exclusions:
        nifti_files = [f for f in nifti_files if not is_scan_excluded(f, exclusions)]
    vif_data = find_vif_files(base_dirs)
    grouped = group_paths_by_filename_pattern(nifti_files)
    result = []
    for pattern, paths in grouped.items():
        if not paths:
            continue
        ent = parse_bids_entities(paths[0])
        task, contrast = ent.get('task'), ent.get('contrast')
        if not task or not contrast:
            continue
        sorted_paths = sorted(paths)
        vif_labels = get_contrast_vif_labels(vif_data, sorted_paths, contrast)
        path_ents = [parse_bids_entities(p) for p in sorted_paths]
        image_labels = [f'sub-s{e["subject"]}_ses-{e["session"]}_run-{e["run"]}' for e in path_ents]
        result.append({
            'main_title': f'{task}_{contrast}',
            'nifti_paths': sorted_paths,
            'image_labels': image_labels,
            'vif_labels': vif_labels,
            'data_type_label': 'Contrast Estimate',
            'task_name': task,
            'contrast_name': contrast,
            'session_ids': [e.get('session') for e in path_ents],
        })
    return result


def process_contrasts(base_dirs, output_dir, exclusions_file, n_std=3):
    exclusions = load_exclusions(exclusions_file) if exclusions_file else set()
    dicts_list = make_input_dicts(base_dirs, exclusions)
    if not dicts_list:
        print('No data found')
        return

    temp_dir = os.path.join(output_dir, 'temp')
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(temp_dir)

    png_files = []
    outlier_dfs = []
    mni_mask = datasets.load_mni152_brain_mask()

    for d in dicts_list:
        try:
            pcts = get_outlier_voxel_percentages(d['nifti_paths'], n_std=n_std)
            vmax = get_symmetric_percentile_bounds(d['nifti_paths'])
            fig = _plot_subject_grid(d['image_labels'], d['vif_labels'], d['nifti_paths'], pcts, mni_mask, d['main_title'], vmax, -vmax, d['data_type_label'], n_std)
            png_path = os.path.join(temp_dir, f'{d["main_title"]}_slice_grid.png')
            fig.savefig(png_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            del fig
            gc.collect()
            png_files.append(png_path)
            outlier_dfs.append(_build_outlier_df(d['image_labels'], pcts, d['main_title'], d.get('task_name'), d.get('contrast_name'), d.get('session_ids'), d['vif_labels']))
        except Exception as e:
            print(f'{d["main_title"]} error: {e}')

    summary_paths = summarize_outlier_percentages(outlier_dfs, output_dir, temp_dir)
    combine_pngs_to_pdf(summary_paths + sorted(png_files), os.path.join(output_dir, 'outlier_analysis.pdf'))
    shutil.rmtree(temp_dir)
    print(f'Outlier report saved to {output_dir}')


class OutlierReportQa:
    name = "outlier-report"
    description = "VIF + outlier analysis with figures and summary CSVs"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--lev1-dirs", nargs="+", help="First-level analysis output directories")
        parser.add_argument("--exclusions-file", default=None, help="JSON file with scan exclusions")
        parser.add_argument("--output-dir", default=None, help="Output directory for report")
        parser.add_argument("--n-std", type=float, default=3, help="Number of SDs for outlier threshold")

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if plt is None:
            print("Error: QA dependencies required. Install with: uv pip install -e \".[qa]\"")
            return
        base_dirs = getattr(args, "lev1_dirs", None) or []
        if not base_dirs:
            print("Error: --lev1-dirs is required for outlier-report")
            return
        output_dir = getattr(args, "output_dir", None) or f"{dataset_config['bids_dir']}/derivatives/outlier_report"
        exclusions_file = getattr(args, "exclusions_file", None)
        n_std = getattr(args, "n_std", 3)
        process_contrasts(base_dirs, output_dir, exclusions_file, n_std)


register_qa(OutlierReportQa())
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_outlier_report.py -v`
Expected: 2 PASS

**Step 5: Update CLI import**

Add to `src/neuro_workflow/cli.py`:

```python
import neuro_workflow.qa.outlier_report  # noqa: F401
```

**Step 6: Commit**

```bash
git add src/neuro_workflow/qa/outlier_report.py tests/qa/test_outlier_report.py src/neuro_workflow/cli.py
git commit -m "feat: add outlier-report QA command"
```

---

## Task 11: reliability QA Script

**Files:**
- Create: `src/neuro_workflow/qa/reliability.py`
- Test: `tests/qa/test_reliability.py`

**Step 1: Write the failing tests**

Create `tests/qa/test_reliability.py`:

```python
import re
from argparse import ArgumentParser, Namespace

from neuro_workflow.qa.reliability import ReliabilityQa, parse_bids_filename


def test_parse_bids_filename():
    result = parse_bids_filename("sub-s03_ses-01_task-rest_run-01_space-T1w_desc-preproc_bold.nii.gz")
    assert result["subject"] == "s03"
    assert result["session"] == "01"
    assert result["task"] == "rest"
    assert result["run"] == 1


def test_parse_bids_filename_no_match():
    assert parse_bids_filename("random_file.nii.gz") is None


def test_qa_attributes():
    qa = ReliabilityQa()
    assert qa.name == "reliability"
    assert qa.description


def test_add_cli_args():
    qa = ReliabilityQa()
    parser = ArgumentParser()
    qa.add_cli_args(parser)
    args = parser.parse_args(["--fmriprep-version", "24.1.0", "--output-dir", "/out"])
    assert args.fmriprep_version == "24.1.0"
    assert args.output_dir == "/out"
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_reliability.py -v`
Expected: FAIL

**Step 3: Write the implementation**

Create `src/neuro_workflow/qa/reliability.py`:

```python
from __future__ import annotations

import re
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional

try:
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.animation import FuncAnimation
    from nilearn.image import mean_img
    from nilearn.plotting import plot_epi
except ImportError:
    plt = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa

FILENAME_PATTERN = re.compile(
    r'sub-(\w+)_ses-(\w+)_task-(\w+)_run-(\d+)_space-T1w_desc-preproc_bold\.nii\.gz'
)


def parse_bids_filename(filename: str) -> Optional[dict]:
    match = FILENAME_PATTERN.search(filename)
    if not match:
        return None
    return {
        'subject': match.group(1),
        'session': match.group(2),
        'task': match.group(3),
        'run': int(match.group(4)),
    }


def _group_by_subject(file_paths):
    subjects = {}
    for fp in file_paths:
        parsed = parse_bids_filename(fp.name)
        if parsed is None:
            continue
        sub = parsed['subject']
        subjects.setdefault(sub, []).append({'path': fp, **{k: v for k, v in parsed.items() if k != 'subject'}})
    return subjects


def _sort_frames(frames):
    def key(f):
        ses_num = int(re.search(r'\d+', f['session']).group())
        return (ses_num, f['task'], f['run'])
    return sorted(frames, key=key)


def _create_movie(subject, frames, output_path):
    mean_images = []
    coords = None
    for frame in frames:
        avg = mean_img(str(frame['path']))
        if coords is None:
            coords = (avg.shape[0] // 2, avg.shape[1] // 2, avg.shape[2] // 2)
        mean_images.append(avg)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    views = [('z', coords[2], 'axial'), ('x', coords[0], 'sagittal'), ('y', coords[1], 'coronal')]

    def update(idx):
        for ax in axes:
            ax.clear()
        frame = frames[idx]
        label = f'{frame["task"]} ses-{frame["session"]} run-{frame["run"]:02d}'
        for ax, (mode, coord, title) in zip(axes, views):
            plot_epi(mean_images[idx], display_mode=mode, cut_coords=[coord], title=title, axes=ax, annotate=False, colorbar=False)
        fig.suptitle(label, fontsize=14)
        return []

    anim = FuncAnimation(fig, update, frames=len(mean_images), interval=1000, blit=False)
    anim.save(str(output_path), writer='ffmpeg', fps=1, codec='mpeg4')
    plt.close(fig)
    print(f'  Saved movie: {output_path} ({len(mean_images)} frames)')


class ReliabilityQa:
    name = "reliability"
    description = "Create MP4 movies showing fMRI reliability across sessions"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--fmriprep-version", default=None, help="fMRIPrep version for derivatives path")
        parser.add_argument("--output-dir", default=None, help="Output directory for movies")

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if plt is None:
            print("Error: 'nilearn', 'matplotlib' required. Install with: uv pip install -e \".[qa]\"")
            return

        bids_dir = Path(dataset_config["bids_dir"])
        version = getattr(args, "fmriprep_version", None) or "24.1.0rc2"
        deriv_dir = bids_dir / "derivatives" / f"fmriprep_{version}"
        output_dir = Path(getattr(args, "output_dir", None) or str(bids_dir / "derivatives" / "reliability_figs"))
        output_dir.mkdir(parents=True, exist_ok=True)

        files = list(deriv_dir.glob("sub-s*/ses-*/func/*space-T1w_desc-preproc_bold.nii.gz"))
        if not files:
            print(f"No preprocessed BOLD files found in {deriv_dir}")
            return

        print(f"Found {len(files)} T1w preprocessed files")
        subjects = _group_by_subject(files)
        print(f"Found {len(subjects)} subjects")

        for sub in sorted(subjects):
            print(f"\nProcessing sub-{sub} ({len(subjects[sub])} files)...")
            frames = _sort_frames(subjects[sub])
            out = output_dir / f"sub-{sub}_reliability_movie.mp4"
            try:
                _create_movie(sub, frames, out)
            except Exception as e:
                print(f"  ERROR for sub-{sub}: {e}")

        print("\nDone.")


register_qa(ReliabilityQa())
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/qa/test_reliability.py -v`
Expected: 4 PASS

**Step 5: Update CLI import**

Add to `src/neuro_workflow/cli.py`:

```python
import neuro_workflow.qa.reliability  # noqa: F401
```

**Step 6: Commit**

```bash
git add src/neuro_workflow/qa/reliability.py tests/qa/test_reliability.py src/neuro_workflow/cli.py
git commit -m "feat: add reliability QA command"
```

---

## Task 12: Core Exclusions Module (Schema, Load/Save, Compile, Query)

**Files:**
- Create: `src/neuro_workflow/core/exclusions.py`
- Test: `tests/core/test_exclusions.py`

**Step 1: Write the failing tests**

Create `tests/core/test_exclusions.py`:

```python
import json
from pathlib import Path

from neuro_workflow.core.exclusions import (
    EXCLUSIONS_DIR,
    validate_entry,
    save_source_entries,
    load_source_entries,
    save_overrides,
    load_overrides,
    compile_exclusions,
    load_compiled_exclusions,
    is_excluded,
    get_trim_info,
)


def test_validate_entry_valid():
    entry = {
        "subject": "sub-s01",
        "session": "ses-01",
        "task": "task-rest",
        "run": "run-1",
        "source": "motion",
        "action": "exclude",
        "reason": "High FD",
    }
    assert validate_entry(entry) is True


def test_validate_entry_missing_field():
    entry = {"subject": "sub-s01", "session": "ses-01"}
    assert validate_entry(entry) is False


def test_validate_entry_bad_action():
    entry = {
        "subject": "sub-s01",
        "session": "ses-01",
        "task": "task-rest",
        "run": "run-1",
        "source": "motion",
        "action": "invalid",
        "reason": "test",
    }
    assert validate_entry(entry) is False


def test_save_and_load_source_entries(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)
    entries = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        }
    ]
    save_source_entries("discovery", "motion", entries)
    loaded = load_source_entries("discovery", "motion")
    assert len(loaded) == 1
    assert loaded[0]["subject"] == "sub-s01"


def test_save_and_load_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)
    overrides = [
        {
            "subject": "sub-s02",
            "session": "ses-05",
            "task": "task-rest",
            "run": "run-1",
            "action": "force-include",
            "reason": "Override",
        }
    ]
    save_overrides("discovery", overrides)
    loaded = load_overrides("discovery")
    assert len(loaded) == 1
    assert loaded[0]["action"] == "force-include"


def test_compile_merges_sources(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    motion = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        }
    ]
    neg = [
        {
            "subject": "sub-s02",
            "session": "ses-03",
            "task": "task-flanker",
            "run": "run-1",
            "source": "neg-events",
            "action": "trim",
            "reason": "Non-monotonic",
            "metrics": {"onset_trim_index": 50, "total_rows": 200, "rows_to_keep": 150},
        }
    ]
    save_source_entries("test", "motion", motion)
    save_source_entries("test", "neg_events", neg)
    save_overrides("test", [])

    compiled = compile_exclusions("test")
    assert len(compiled) == 2


def test_compile_force_include_removes(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    motion = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        }
    ]
    overrides = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "action": "force-include",
            "reason": "Manual override",
        }
    ]
    save_source_entries("test", "motion", motion)
    save_overrides("test", overrides)

    compiled = compile_exclusions("test")
    assert len(compiled) == 0


def test_compile_force_exclude_adds(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    save_overrides("test", [
        {
            "subject": "sub-s99",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "action": "force-exclude",
            "reason": "Manual exclusion",
        }
    ])
    # No source files — just overrides
    compiled = compile_exclusions("test")
    assert len(compiled) == 1
    assert compiled[0]["action"] == "exclude"
    assert compiled[0]["source"] == "override"


def test_is_excluded(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    entries = [
        {
            "subject": "sub-s01",
            "session": "ses-01",
            "task": "task-rest",
            "run": "run-1",
            "source": "motion",
            "action": "exclude",
            "reason": "High FD",
        }
    ]
    save_source_entries("test", "motion", entries)
    save_overrides("test", [])
    compiled = compile_exclusions("test")

    assert is_excluded("sub-s01", "ses-01", "task-rest", "run-1", compiled) is True
    assert is_excluded("sub-s01", "ses-02", "task-rest", "run-1", compiled) is False


def test_get_trim_info(tmp_path, monkeypatch):
    monkeypatch.setattr("neuro_workflow.core.exclusions.EXCLUSIONS_DIR", tmp_path)

    entries = [
        {
            "subject": "sub-s03",
            "session": "ses-11",
            "task": "task-stop",
            "run": "run-1",
            "source": "neg-events",
            "action": "trim",
            "reason": "Non-monotonic",
            "metrics": {"onset_trim_index": 161, "total_rows": 726, "rows_to_keep": 565},
        }
    ]
    save_source_entries("test", "neg_events", entries)
    save_overrides("test", [])
    compiled = compile_exclusions("test")

    info = get_trim_info("sub-s03", "ses-11", "task-stop", "run-1", compiled)
    assert info is not None
    assert info["onset_trim_index"] == 161
    assert info["rows_to_keep"] == 565

    assert get_trim_info("sub-s99", "ses-01", "task-rest", "run-1", compiled) is None
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/core/test_exclusions.py -v`
Expected: FAIL (import error)

**Step 3: Write the implementation**

Create `src/neuro_workflow/core/exclusions.py`:

```python
"""Scan exclusion management: schema, persistence, compilation, and query API."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from neuro_workflow.core.config import CONFIG_DIR

EXCLUSIONS_DIR = CONFIG_DIR / "exclusions"

REQUIRED_FIELDS = {"subject", "session", "task", "run", "action", "reason"}
VALID_ACTIONS = {"exclude", "trim", "force-include", "force-exclude"}


def _scan_key(entry: dict) -> tuple:
    return (entry["subject"], entry["session"], entry["task"], entry["run"])


def validate_entry(entry: dict) -> bool:
    """Check that an entry has all required fields and a valid action."""
    if not REQUIRED_FIELDS.issubset(entry.keys()):
        return False
    if entry["action"] not in VALID_ACTIONS:
        return False
    return True


def _sources_dir(dataset_name: str) -> Path:
    return EXCLUSIONS_DIR / dataset_name / "sources"


def _overrides_path(dataset_name: str) -> Path:
    return EXCLUSIONS_DIR / dataset_name / "overrides.json"


def _compiled_path(dataset_name: str) -> Path:
    return EXCLUSIONS_DIR / dataset_name / "compiled_exclusions.json"


def save_source_entries(dataset_name: str, source_name: str, entries: list[dict]) -> None:
    """Write entries for a single source to its JSON file."""
    d = _sources_dir(dataset_name)
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"{source_name}.json", "w") as f:
        json.dump(entries, f, indent=2)


def load_source_entries(dataset_name: str, source_name: str) -> list[dict]:
    """Load entries for a single source."""
    path = _sources_dir(dataset_name) / f"{source_name}.json"
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_overrides(dataset_name: str, overrides: list[dict]) -> None:
    """Write manual override entries."""
    path = _overrides_path(dataset_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(overrides, f, indent=2)


def load_overrides(dataset_name: str) -> list[dict]:
    """Load manual override entries."""
    path = _overrides_path(dataset_name)
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def compile_exclusions(dataset_name: str, bids_dir: Optional[str] = None) -> list[dict]:
    """Merge all source files and overrides into a compiled exclusion list.

    1. Collect all entries from sources/*.json
    2. Apply overrides: force-include removes, force-exclude adds
    3. Save compiled result
    4. Optionally copy to derivatives
    """
    sources_dir = _sources_dir(dataset_name)
    all_entries: list[dict] = []

    if sources_dir.exists():
        for source_file in sorted(sources_dir.glob("*.json")):
            with open(source_file) as f:
                all_entries.extend(json.load(f))

    overrides = load_overrides(dataset_name)

    # Separate override types
    force_includes = {_scan_key(o) for o in overrides if o.get("action") == "force-include"}
    force_excludes = [o for o in overrides if o.get("action") == "force-exclude"]

    # Remove force-included scans
    if force_includes:
        all_entries = [e for e in all_entries if _scan_key(e) not in force_includes]

    # Add force-excluded scans
    for fe in force_excludes:
        all_entries.append({
            "subject": fe["subject"],
            "session": fe["session"],
            "task": fe["task"],
            "run": fe["run"],
            "source": "override",
            "action": "exclude",
            "reason": fe.get("reason", "Manual force-exclude"),
            "metrics": fe.get("metrics", {}),
        })

    # Save compiled
    compiled_path = _compiled_path(dataset_name)
    compiled_path.parent.mkdir(parents=True, exist_ok=True)
    with open(compiled_path, "w") as f:
        json.dump(all_entries, f, indent=2)

    # Copy to derivatives if bids_dir provided
    if bids_dir:
        deriv = Path(bids_dir) / "derivatives" / "exclusions"
        deriv.mkdir(parents=True, exist_ok=True)
        with open(deriv / "compiled_exclusions.json", "w") as f:
            json.dump(all_entries, f, indent=2)

    return all_entries


def load_compiled_exclusions(dataset_name: str) -> list[dict]:
    """Load the compiled exclusion list for a dataset."""
    path = _compiled_path(dataset_name)
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def is_excluded(subject: str, session: str, task: str, run: str, compiled: list[dict]) -> bool:
    """Check if a scan is excluded (action == 'exclude' or 'trim')."""
    key = (subject, session, task, run)
    return any(_scan_key(e) == key for e in compiled if e["action"] in ("exclude", "trim"))


def get_trim_info(subject: str, session: str, task: str, run: str, compiled: list[dict]) -> Optional[dict]:
    """Get trim metrics for a scan, or None if not a trim action."""
    key = (subject, session, task, run)
    for e in compiled:
        if _scan_key(e) == key and e["action"] == "trim":
            return e.get("metrics", {})
    return None
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/core/test_exclusions.py -v`
Expected: 11 PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/core/exclusions.py tests/core/test_exclusions.py
git commit -m "feat: add core exclusions module (schema, compile, query API)"
```

---

## Task 13: Exclusion Generator Protocol and Registry

**Files:**
- Create: `src/neuro_workflow/exclusions/__init__.py`
- Create: `src/neuro_workflow/exclusions/base.py`
- Test: `tests/exclusions/__init__.py`
- Test: `tests/exclusions/test_base.py`

**Step 1: Write the failing tests**

Create `tests/exclusions/__init__.py` (empty) and `tests/exclusions/test_base.py`:

```python
from neuro_workflow.exclusions.base import (
    register_generator,
    get_generator,
    list_generators,
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
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/exclusions/test_base.py -v`
Expected: FAIL (import error)

**Step 3: Write the implementation**

Create `src/neuro_workflow/exclusions/__init__.py` (empty).

Create `src/neuro_workflow/exclusions/base.py`:

```python
from __future__ import annotations

from argparse import ArgumentParser, Namespace
from typing import Protocol, runtime_checkable

_REGISTRY: dict[str, ExclusionGenerator] = {}


@runtime_checkable
class ExclusionGenerator(Protocol):
    name: str
    description: str

    def add_cli_args(self, parser: ArgumentParser) -> None: ...
    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]: ...


def register_generator(generator: ExclusionGenerator) -> None:
    _REGISTRY[generator.name] = generator


def get_generator(name: str) -> ExclusionGenerator | None:
    return _REGISTRY.get(name)


def list_generators() -> dict[str, ExclusionGenerator]:
    return dict(_REGISTRY)
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/exclusions/test_base.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/exclusions/__init__.py src/neuro_workflow/exclusions/base.py tests/exclusions/__init__.py tests/exclusions/test_base.py
git commit -m "feat: add ExclusionGenerator protocol and registry"
```

---

## Task 14: Motion Exclusion Generator

**Files:**
- Create: `src/neuro_workflow/exclusions/motion.py`
- Test: `tests/exclusions/test_motion.py`

**Step 1: Write the failing tests**

Create `tests/exclusions/test_motion.py`:

```python
from argparse import Namespace
from pathlib import Path

from neuro_workflow.exclusions.motion import MotionGenerator


def _make_confounds_tsv(func_dir, subject, session, task, run, fd_values, dvars_values):
    """Create a minimal confounds TSV with framewise_displacement and dvars columns."""
    filename = f"{subject}_{session}_task-{task}_run-{run}_desc-confounds_timeseries.tsv"
    lines = ["framewise_displacement\tdvars"]
    for fd, dv in zip(fd_values, dvars_values):
        lines.append(f"{fd}\t{dv}")
    (func_dir / filename).write_text("\n".join(lines))


def _make_deriv_tree(tmp_path, version="24.1.0rc2"):
    """Create a BIDS derivatives tree with confound files."""
    deriv = tmp_path / "bids" / "derivatives" / f"fmriprep_{version}"

    # Good scan (low motion)
    func1 = deriv / "sub-s01" / "ses-01" / "func"
    func1.mkdir(parents=True)
    _make_confounds_tsv(func1, "sub-s01", "ses-01", "flanker", "1",
                        [0.1] * 100, [1.0] * 100)

    # Bad scan (high FD proportion)
    func2 = deriv / "sub-s02" / "ses-01" / "func"
    func2.mkdir(parents=True)
    _make_confounds_tsv(func2, "sub-s02", "ses-01", "flanker", "1",
                        [0.6] * 100, [1.0] * 100)  # all FD > 0.5

    # Bad resting-state (high FD mean)
    func3 = deriv / "sub-s03" / "ses-01" / "func"
    func3.mkdir(parents=True)
    _make_confounds_tsv(func3, "sub-s03", "ses-01", "rest", "1",
                        [0.25] * 100, [1.0] * 100)  # mean FD = 0.25 > 0.2

    return str(tmp_path / "bids")


def test_generator_attributes():
    g = MotionGenerator()
    assert g.name == "motion"
    assert g.description


def test_generate_finds_bad_scans(tmp_path):
    bids_dir = _make_deriv_tree(tmp_path)
    g = MotionGenerator()
    config = {"bids_dir": bids_dir}
    args = Namespace(
        fmriprep_version="24.1.0rc2",
        fd_threshold=0.2,
        proportion_fd_threshold=0.2,
        proportion_dvars_threshold=0.2,
    )
    entries = g.generate("discovery", config, args)
    subjects = {e["subject"] for e in entries}
    # sub-s02 (high FD proportion) and sub-s03 (high rest FD mean) should be flagged
    assert "sub-s02" in subjects
    assert "sub-s03" in subjects
    # sub-s01 should NOT be flagged
    assert "sub-s01" not in subjects


def test_generate_all_actions_are_exclude(tmp_path):
    bids_dir = _make_deriv_tree(tmp_path)
    g = MotionGenerator()
    config = {"bids_dir": bids_dir}
    args = Namespace(
        fmriprep_version="24.1.0rc2",
        fd_threshold=0.2,
        proportion_fd_threshold=0.2,
        proportion_dvars_threshold=0.2,
    )
    entries = g.generate("discovery", config, args)
    assert all(e["action"] == "exclude" for e in entries)
    assert all(e["source"] == "motion" for e in entries)
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/exclusions/test_motion.py -v`
Expected: FAIL (import error)

**Step 3: Write the implementation**

Create `src/neuro_workflow/exclusions/motion.py`:

```python
"""Motion exclusion generator: reads fmriprep confound TSVs and applies thresholds."""
from __future__ import annotations

import re
from argparse import ArgumentParser, Namespace
from pathlib import Path

try:
    import numpy as np
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

from neuro_workflow.exclusions.base import register_generator


def _parse_confounds_filename(filename: str) -> dict | None:
    """Extract BIDS entities from a confounds filename."""
    m = re.match(
        r'(sub-\w+)_(ses-\w+)_task-(\w+)_run-(\w+)_desc-confounds_timeseries\.tsv',
        filename,
    )
    if not m:
        return None
    return {
        "subject": m.group(1),
        "session": m.group(2),
        "task": m.group(3),
        "run": m.group(4),
    }


def _compute_metrics(df: pd.DataFrame) -> dict:
    """Compute motion metrics from a confounds dataframe."""
    fd = pd.to_numeric(df.get("framewise_displacement", pd.Series(dtype=float)), errors="coerce").dropna()
    dvars = pd.to_numeric(df.get("dvars", pd.Series(dtype=float)), errors="coerce").dropna()
    return {
        "fmriprep_fd_mean": float(fd.mean()) if len(fd) > 0 else 0.0,
        "fmriprep_fd_std": float(fd.std()) if len(fd) > 0 else 0.0,
        "fmriprep_proportion_fd_over_0.5": float((fd > 0.5).mean()) if len(fd) > 0 else 0.0,
        "fmriprep_dvars_mean": float(dvars.mean()) if len(dvars) > 0 else 0.0,
        "fmriprep_dvars_std": float(dvars.std()) if len(dvars) > 0 else 0.0,
        "fmriprep_proportion_dvars_over_1.5": float((dvars > 1.5).mean()) if len(dvars) > 0 else 0.0,
    }


class MotionGenerator:
    name = "motion"
    description = "Generate motion exclusions from fmriprep confound files"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--fmriprep-version", required=False, default="24.1.0rc2",
                            help="fMRIPrep version for derivatives path")
        parser.add_argument("--fd-threshold", type=float, default=0.2,
                            help="FD mean threshold for resting-state (default: 0.2)")
        parser.add_argument("--proportion-fd-threshold", type=float, default=0.2,
                            help="Proportion FD > 0.5 threshold for task scans (default: 0.2)")
        parser.add_argument("--proportion-dvars-threshold", type=float, default=0.2,
                            help="Proportion DVARS > 1.5 threshold (default: 0.2)")

    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]:
        if pd is None:
            print("Error: 'pandas' required for motion generator. Install with: uv pip install -e \".[qa]\"")
            return []

        bids_dir = Path(dataset_config["bids_dir"])
        version = getattr(args, "fmriprep_version", "24.1.0rc2")
        deriv = bids_dir / "derivatives" / f"fmriprep_{version}"

        confound_files = sorted(deriv.glob("sub-*/ses-*/func/*_desc-confounds_timeseries.tsv"))
        if not confound_files:
            print(f"No confound files found in {deriv}")
            return []

        fd_thresh = args.fd_threshold
        prop_fd_thresh = args.proportion_fd_threshold
        prop_dvars_thresh = args.proportion_dvars_threshold

        entries = []
        for tsv_path in confound_files:
            parsed = _parse_confounds_filename(tsv_path.name)
            if not parsed:
                continue

            df = pd.read_csv(tsv_path, sep="\t")
            metrics = _compute_metrics(df)

            is_rest = parsed["task"] == "rest"
            reasons = []

            if is_rest:
                if metrics["fmriprep_fd_mean"] > fd_thresh:
                    reasons.append(
                        f"Resting state FD mean ({metrics['fmriprep_fd_mean']:.3f}) "
                        f"exceeded threshold ({fd_thresh})"
                    )
            else:
                if metrics["fmriprep_proportion_fd_over_0.5"] > prop_fd_thresh:
                    reasons.append(
                        f"Proportion FD > 0.5 ({metrics['fmriprep_proportion_fd_over_0.5']:.3f}) "
                        f"exceeded threshold ({prop_fd_thresh})"
                    )

            if metrics["fmriprep_proportion_dvars_over_1.5"] > prop_dvars_thresh:
                reasons.append(
                    f"Proportion DVARS > 1.5 ({metrics['fmriprep_proportion_dvars_over_1.5']:.3f}) "
                    f"exceeded threshold ({prop_dvars_thresh})"
                )

            if reasons:
                entries.append({
                    "subject": parsed["subject"],
                    "session": parsed["session"],
                    "task": f"task-{parsed['task']}",
                    "run": f"run-{parsed['run']}",
                    "source": "motion",
                    "action": "exclude",
                    "reason": "; ".join(reasons),
                    "metrics": metrics,
                })

        print(f"Motion generator: {len(entries)} exclusions from {len(confound_files)} confound files")
        return entries


register_generator(MotionGenerator())
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/exclusions/test_motion.py -v`
Expected: 3 PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/exclusions/motion.py tests/exclusions/test_motion.py
git commit -m "feat: add motion exclusion generator"
```

---

## Task 15: Neg-Events Exclusion Generator

**Files:**
- Create: `src/neuro_workflow/exclusions/neg_events.py`
- Test: `tests/exclusions/test_neg_events_gen.py`

**Step 1: Write the failing tests**

Create `tests/exclusions/test_neg_events_gen.py`:

```python
from argparse import Namespace
from pathlib import Path

from neuro_workflow.exclusions.neg_events import NegEventsGenerator


def test_generator_attributes():
    g = NegEventsGenerator()
    assert g.name == "neg-events"
    assert g.description


def test_generate_detects_trim(tmp_path):
    """Non-monotonic onset with >50% salvageable -> trim action."""
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)
    # 10 rows: first onset is out of order, rest monotonic (90% salvageable)
    lines = ["onset\tduration"]
    lines.append("5.0\t1.0")  # bad
    for i in range(1, 10):
        lines.append(f"{float(i)}\t1.0")
    (func / "sub-s01_ses-01_task-flanker_events.tsv").write_text("\n".join(lines))

    g = NegEventsGenerator()
    config = {"bids_dir": str(bids)}
    args = Namespace()
    entries = g.generate("test", config, args)
    assert len(entries) == 1
    assert entries[0]["action"] == "trim"
    assert entries[0]["metrics"]["onset_trim_index"] == 1
    assert entries[0]["metrics"]["rows_to_keep"] == 9


def test_generate_detects_exclude(tmp_path):
    """Non-monotonic onset with <50% salvageable -> exclude action."""
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)
    # Mostly non-monotonic: only last 2 of 10 rows are monotonic (20%)
    lines = ["onset\tduration"]
    for i in range(8):
        lines.append(f"{float(8 - i)}\t1.0")  # descending
    lines.append("9.0\t1.0")
    lines.append("10.0\t1.0")
    (func / "sub-s01_ses-01_task-flanker_events.tsv").write_text("\n".join(lines))

    g = NegEventsGenerator()
    config = {"bids_dir": str(bids)}
    args = Namespace()
    entries = g.generate("test", config, args)
    assert len(entries) == 1
    assert entries[0]["action"] == "exclude"


def test_generate_skips_monotonic(tmp_path):
    """Monotonic onsets -> no entries."""
    bids = tmp_path / "bids"
    func = bids / "sub-s01" / "ses-01" / "func"
    func.mkdir(parents=True)
    lines = ["onset\tduration"]
    for i in range(10):
        lines.append(f"{float(i)}\t1.0")
    (func / "sub-s01_ses-01_task-flanker_events.tsv").write_text("\n".join(lines))

    g = NegEventsGenerator()
    config = {"bids_dir": str(bids)}
    args = Namespace()
    entries = g.generate("test", config, args)
    assert len(entries) == 0
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/exclusions/test_neg_events_gen.py -v`
Expected: FAIL (import error)

**Step 3: Write the implementation**

Create `src/neuro_workflow/exclusions/neg_events.py`:

```python
"""Neg-events exclusion generator: detects non-monotonic event file onsets."""
from __future__ import annotations

import re
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Optional

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

from neuro_workflow.exclusions.base import register_generator


def _find_monotonic_point(onset_series) -> Optional[int]:
    """Find the index where onsets become monotonically increasing."""
    for i in range(len(onset_series)):
        if onset_series.iloc[i:].is_monotonic_increasing:
            return i
    return None


def _parse_event_filename(filename: str) -> dict | None:
    """Extract BIDS entities from an event filename."""
    sub = re.search(r'(sub-\w+)', filename)
    ses = re.search(r'(ses-\w+)', filename)
    task = re.search(r'task-(\w+)', filename)
    run = re.search(r'run-(\w+)', filename)
    if not sub or not ses or not task:
        return None
    return {
        "subject": sub.group(1),
        "session": ses.group(1),
        "task": f"task-{task.group(1)}",
        "run": f"run-{run.group(1)}" if run else "run-1",
    }


class NegEventsGenerator:
    name = "neg-events"
    description = "Detect non-monotonic event file onsets and generate trim/exclude entries"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        pass  # no extra args

    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]:
        if pd is None:
            print("Error: 'pandas' required for neg-events generator. Install with: uv pip install -e \".[qa]\"")
            return []

        bids_dir = Path(dataset_config["bids_dir"])
        event_files = sorted(bids_dir.glob("sub-*/ses-*/func/*event*.tsv"))
        if not event_files:
            print(f"No event files found in {bids_dir}")
            return []

        entries = []
        for fp in event_files:
            try:
                df = pd.read_csv(fp, sep="\t")
                if "onset" not in df.columns:
                    continue
                if df["onset"].is_monotonic_increasing:
                    continue

                parsed = _parse_event_filename(fp.name)
                if not parsed:
                    continue

                trim_idx = _find_monotonic_point(df["onset"])
                total_rows = len(df)

                if trim_idx is not None:
                    rows_to_keep = total_rows - trim_idx
                    salvage_ratio = rows_to_keep / total_rows
                    action = "trim" if salvage_ratio > 0.5 else "exclude"
                else:
                    rows_to_keep = 0
                    trim_idx = total_rows
                    action = "exclude"

                entries.append({
                    "subject": parsed["subject"],
                    "session": parsed["session"],
                    "task": parsed["task"],
                    "run": parsed["run"],
                    "source": "neg-events",
                    "action": action,
                    "reason": f"Non-monotonic onsets, {rows_to_keep / total_rows * 100:.1f}% salvageable",
                    "metrics": {
                        "onset_trim_index": trim_idx,
                        "total_rows": total_rows,
                        "rows_to_keep": rows_to_keep,
                    },
                })
            except Exception as e:
                print(f"Error reading {fp.name}: {e}")

        print(f"Neg-events generator: {len(entries)} entries from {len(event_files)} event files")
        return entries


register_generator(NegEventsGenerator())
```

**Step 4: Run tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/exclusions/test_neg_events_gen.py -v`
Expected: 4 PASS

**Step 5: Commit**

```bash
git add src/neuro_workflow/exclusions/neg_events.py tests/exclusions/test_neg_events_gen.py
git commit -m "feat: add neg-events exclusion generator"
```

---

## Task 16: Behavioral Stub Generator + Exclusions CLI Subcommand

**Files:**
- Create: `src/neuro_workflow/exclusions/behavioral.py`
- Modify: `src/neuro_workflow/cli.py`
- Test: `tests/exclusions/test_behavioral.py`
- Test: `tests/test_cli.py` (add exclusions CLI tests)

**Step 1: Write the failing tests**

Create `tests/exclusions/test_behavioral.py`:

```python
from argparse import Namespace
from neuro_workflow.exclusions.behavioral import BehavioralGenerator


def test_generator_attributes():
    g = BehavioralGenerator()
    assert g.name == "behavioral"
    assert g.description


def test_generate_returns_empty(tmp_path):
    g = BehavioralGenerator()
    config = {"bids_dir": str(tmp_path)}
    args = Namespace()
    entries = g.generate("test", config, args)
    assert entries == []
```

**Step 2: Run tests to verify they fail**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/exclusions/test_behavioral.py -v`
Expected: FAIL (import error)

**Step 3: Write the behavioral stub**

Create `src/neuro_workflow/exclusions/behavioral.py`:

```python
"""Behavioral exclusion generator (stub — future automated behavioral QA)."""
from __future__ import annotations

from argparse import ArgumentParser, Namespace

from neuro_workflow.exclusions.base import register_generator


class BehavioralGenerator:
    name = "behavioral"
    description = "Automated behavioral QA exclusions (not yet implemented)"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        pass

    def generate(self, dataset_name: str, dataset_config: dict, args: Namespace) -> list[dict]:
        print(
            "behavioral generator not yet implemented — "
            "use 'neuro-run exclusions import' or overrides.json for manual behavioral exclusions"
        )
        return []


register_generator(BehavioralGenerator())
```

**Step 4: Update CLI with exclusions subcommand**

Add to `src/neuro_workflow/cli.py`:

Import generators at the top (alongside pipeline/QA imports):

```python
from neuro_workflow.core.exclusions import (
    save_source_entries,
    save_overrides,
    load_overrides,
    compile_exclusions,
    load_compiled_exclusions,
)
from neuro_workflow.exclusions.base import get_generator, list_generators

import neuro_workflow.exclusions.motion  # noqa: F401
import neuro_workflow.exclusions.neg_events  # noqa: F401
import neuro_workflow.exclusions.behavioral  # noqa: F401
```

Add handler functions:

```python
def cmd_exclusions_generate(args):
    generator = get_generator(args.source)
    if generator is None:
        available = ", ".join(list_generators()) or "(none registered)"
        print(f"Error: unknown generator '{args.source}'. Available: {available}", file=sys.stderr)
        sys.exit(1)
    config = get_dataset(args.dataset)
    entries = generator.generate(args.dataset, config, args)
    save_source_entries(args.dataset, generator.name, entries)
    print(f"Saved {len(entries)} entries to sources/{generator.name}.json")


def cmd_exclusions_compile(args):
    config = get_dataset(args.dataset)
    compiled = compile_exclusions(args.dataset, bids_dir=config.get("bids_dir"))
    # Print summary
    from collections import Counter
    by_source = Counter(e["source"] for e in compiled)
    by_action = Counter(e["action"] for e in compiled)
    print(f"Compiled {len(compiled)} exclusions for '{args.dataset}':")
    for source, count in sorted(by_source.items()):
        print(f"  {source}: {count}")
    print(f"  Actions: {dict(by_action)}")


def cmd_exclusions_show(args):
    compiled = load_compiled_exclusions(args.dataset)
    if not compiled:
        print(f"No compiled exclusions for '{args.dataset}'. Run 'neuro-run exclusions compile {args.dataset}' first.")
        return
    from collections import Counter
    by_source = Counter(e["source"] for e in compiled)
    by_action = Counter(e["action"] for e in compiled)
    print(f"Exclusions for '{args.dataset}':")
    print(f"{'Source':<15} {'Exclude':>8} {'Trim':>8} {'Total':>8}")
    print("-" * 41)
    for source in sorted(by_source):
        src_entries = [e for e in compiled if e["source"] == source]
        n_exc = sum(1 for e in src_entries if e["action"] == "exclude")
        n_trim = sum(1 for e in src_entries if e["action"] == "trim")
        print(f"{source:<15} {n_exc:>8} {n_trim:>8} {len(src_entries):>8}")
    print("-" * 41)
    print(f"{'Total':<15} {by_action.get('exclude', 0):>8} {by_action.get('trim', 0):>8} {len(compiled):>8}")


def cmd_exclusions_import(args):
    import json
    with open(args.input_file) as f:
        entries = json.load(f)
    for entry in entries:
        entry["source"] = args.source_name
    save_source_entries(args.dataset, args.source_name, entries)
    print(f"Imported {len(entries)} entries as source '{args.source_name}'")
```

Add subcommand group in `main()`:

```python
    # exclusions
    excl_p = subparsers.add_parser("exclusions", help="Manage scan exclusions")
    excl_sub = excl_p.add_subparsers(dest="excl_command", required=True)

    # exclusions generate
    gen_p = excl_sub.add_parser("generate", help="Generate exclusions from a source")
    gen_p.add_argument("source", help="Generator name (e.g. motion, neg-events)")
    gen_p.add_argument("dataset", help="Dataset name")
    for gen in list_generators().values():
        gen.add_cli_args(gen_p)
    gen_p.set_defaults(func=cmd_exclusions_generate)

    # exclusions compile
    comp_p = excl_sub.add_parser("compile", help="Compile all exclusion sources")
    comp_p.add_argument("dataset", help="Dataset name")
    comp_p.set_defaults(func=cmd_exclusions_compile)

    # exclusions show
    show_excl_p = excl_sub.add_parser("show", help="Show exclusion summary")
    show_excl_p.add_argument("dataset", help="Dataset name")
    show_excl_p.set_defaults(func=cmd_exclusions_show)

    # exclusions import
    imp_p = excl_sub.add_parser("import", help="Import external exclusion list")
    imp_p.add_argument("source_name", help="Source name to assign")
    imp_p.add_argument("dataset", help="Dataset name")
    imp_p.add_argument("--input-file", required=True, help="Path to JSON file to import")
    imp_p.set_defaults(func=cmd_exclusions_import)
```

**Step 5: Run all tests to verify they pass**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/ -v`
Expected: all tests PASS

**Step 6: Commit**

```bash
git add src/neuro_workflow/exclusions/behavioral.py src/neuro_workflow/cli.py tests/exclusions/test_behavioral.py
git commit -m "feat: add behavioral stub generator and exclusions CLI subcommand"
```

---

## Task 17: Add QA + Exclusion Dependencies to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

**Step 1: Read current pyproject.toml**

Read `pyproject.toml` to see current state.

**Step 2: Add optional QA dependencies**

Add `[project.optional-dependencies]` section:

```toml
[project.optional-dependencies]
qa = [
    "nilearn>=0.12",
    "nibabel>=5.0",
    "matplotlib>=3.0",
    "pandas>=2.0",
    "numpy>=1.24",
    "img2pdf>=0.5",
    "seaborn>=0.13",
]
```

**Step 3: Verify install**

Run: `ml uv && unset VIRTUAL_ENV && uv pip install -e ".[qa]" --dry-run`

**Step 4: Run full test suite**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/ -v`
Expected: all tests PASS

**Step 5: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add optional QA dependencies to pyproject.toml"
```

---

## Task 18: Remove custom_scripts/ Directory

**Files:**
- Delete: `custom_scripts/` (entire directory)

**Step 1: Verify all scripts have been ported**

Check that every file in `custom_scripts/` has a corresponding implementation in the new package:

- `04_run_qsiprep.sbatch` -> `pipelines/qsiprep.py` + `templates/qsiprep.sbatch`
- `submit_fsqc.sh` -> `pipelines/fsqc.py` + `templates/fsqc.sbatch`
- `freesurfer_8.1.0.sbatch` -> `pipelines/freesurfer.py` + `templates/freesurfer.sbatch`
- `prepare_happy.sh` + `run_happy.sh` -> `pipelines/happy.py` + `templates/happy.sbatch`
- `run_neg_events.py` -> `qa/neg_events.py`
- `run_breaks.py` -> `qa/breaks.py`
- `run_global_signal.py` -> `qa/global_signal.py`
- `run_visualize_reliability.py` -> `qa/reliability.py`
- `run_network.py` + `run_report.py` + `plotting_functions.py` -> `qa/outlier_report.py`

**Step 2: Remove the directory**

```bash
rm -rf custom_scripts/
```

**Step 3: Run full test suite**

Run: `ml uv && unset VIRTUAL_ENV && uv run python -m pytest tests/ -v`
Expected: all tests still PASS

**Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove custom_scripts/ (all ported to neuro-workflow)"
```

---

## Task 19: Update README

**Files:**
- Modify: `README.md`

**Step 1: Read current README**

**Step 2: Update with new pipeline and QA command documentation**

Add sections covering:
- New pipelines: qsiprep, fsqc, freesurfer, happy
- QA commands: neg-events, breaks, global-signal, outlier-report, reliability
- Exclusions management: generate, compile, show, import
- Installing QA extras: `uv pip install -e ".[qa]"`
- Example commands for each

**Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README with Phase 2 pipelines and QA commands"
```
