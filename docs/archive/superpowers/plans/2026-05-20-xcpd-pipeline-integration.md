# XCP-D Pipeline Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `xcpd` pipeline to `neuro_workflow` that runs XCP-D 26.0.2 on the existing fmriprep derivatives (4 discovery + 41 validation subjects, excluding s03 until its fmriprep finishes), using Gracie Grimsrud's canonical flag set with 384 GB on bigmem to avoid her OOM failures.

**Architecture:** New `XcpdPipeline` class mirroring `FmriprepPipeline`/`QsiprepPipeline` (Pipeline Protocol + sbatch template), submitted via the standard `neuro-run submit xcpd <dataset>` CLI. Hard-codes Gracie's denoising flags in the template; `--xcpd-args` passthrough for ad-hoc additions. nipype work-dir preserved between runs for resume-on-timeout.

**Tech Stack:** Python 3.13, pytest, XCP-D 26.0.2 (apptainer), SLURM bigmem partition, uv for env management.

**Spec:** `docs/superpowers/specs/2026-05-20-xcpd-pipeline-integration-design.md`

---

## File map

**Created (code + tests):**
- `src/neuro_workflow/pipelines/xcpd.py` — `XcpdPipeline` class (~110 lines)
- `src/neuro_workflow/templates/xcpd.sbatch` — sbatch template with hardcoded Gracie flags (~55 lines)
- `tests/pipelines/test_xcpd.py` — pipeline class + template render tests (~110 lines)

**Modified:**
- `src/neuro_workflow/cli.py` — one import line for auto-registration

**Created (config files, not git-tracked code):**
- `subjects_discovery_xcpd.txt` — 4 lines (s10, s19, s29, s43)
- `subjects_validation_xcpd.txt` — 41 lines

**Created (file system, not git-tracked):**
- Symlink `/home/groups/russpold/singularity_images/xcpd_26.0.2.sif` → `/oak/.../shared/containers/xcp_d-26.0.2.sif`

**Created (dataset registry, written to `~/.neuro_workflow/datasets.json`):**
- `discovery_xcpd` dataset
- `validation_xcpd` dataset

**Modified (docs):**
- `docs/WORKFLOW.md` — add Step 10 (XCP-D) post-fmriprep

---

## Task 1: Pipeline class + tests (TDD)

**Files:**
- Create: `src/neuro_workflow/pipelines/xcpd.py`
- Create: `tests/pipelines/test_xcpd.py`

- [ ] **Step 1.1: Write the failing test file**

Create `tests/pipelines/test_xcpd.py`:

```python
import sys
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from neuro_workflow.pipelines.xcpd import XcpdPipeline


def make_args(**overrides):
    defaults = {
        "version": "26.0.2",
        "fmriprep_version": "25.2.4",
        "xcpd_args": "",
        "fs_license": "~/license.txt",
        "nthreads": None,
        "mem_per_cpu_gb": None,
        "time": None,
        "array_throttle": 8,
        "partition": None,
    }
    defaults.update(overrides)
    return Namespace(**defaults)


def make_config(tmp_path):
    subs = tmp_path / "subs.txt"
    subs.write_text("s10\ns19\ns29\n")
    return {
        "bids_dir": str(tmp_path / "bids"),
        "subjects_file": str(subs),
        "partition": "bigmem",
        "image_dir": "/images",
        "templateflow_dir": "/templateflow",
        "mail_user": None,
    }


def test_pipeline_attributes():
    p = XcpdPipeline()
    assert p.name == "xcpd"
    assert p.docker_uri == "docker://pennlinc/xcp_d"
    assert p.template_name == "xcpd.sbatch"


def test_default_resources():
    p = XcpdPipeline()
    assert p.default_resources["nthreads"] == 16
    assert p.default_resources["mem_per_cpu_gb"] == 24
    assert p.default_resources["time"] == "1-00:00:00"


def test_build_context_basic(tmp_path):
    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("discovery_xcpd", config, args)
    assert ctx["dataset_name"] == "discovery_xcpd"
    assert ctx["n_subjects"] == 3
    assert ctx["nthreads"] == 16
    assert ctx["mem_per_cpu_gb"] == 24
    assert ctx["image_path"] == "/images/xcpd_26.0.2.sif"
    assert ctx["xcpd_version"] == "26.0.2"
    assert ctx["fmriprep_dir"].endswith("derivatives/fmriprep_25.2.4")
    assert ctx["output_dir"].endswith("derivatives/xcp_d_26.0.2")
    assert ctx["array_throttle"] == 8


def test_build_context_version_required(tmp_path):
    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args(version=None)
    with patch.object(sys, "exit", side_effect=SystemExit):
        try:
            p.build_context("discovery_xcpd", config, args)
        except SystemExit:
            return
    assert False, "expected SystemExit"


def test_build_context_custom_resources(tmp_path):
    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args(nthreads=8, mem_per_cpu_gb=32, time="12:00:00", array_throttle=4)
    ctx = p.build_context("discovery_xcpd", config, args)
    assert ctx["nthreads"] == 8
    assert ctx["mem_per_cpu_gb"] == 32
    assert ctx["time"] == "12:00:00"
    assert ctx["array_throttle"] == 4


def test_build_context_custom_fmriprep_version(tmp_path):
    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args(fmriprep_version="24.1.1")
    ctx = p.build_context("discovery_xcpd", config, args)
    assert ctx["fmriprep_dir"].endswith("derivatives/fmriprep_24.1.1")


def test_template_renders(tmp_path):
    from neuro_workflow.core.slurm import render_template
    from neuro_workflow.pipelines.base import TEMPLATE_DIR

    p = XcpdPipeline()
    config = make_config(tmp_path)
    args = make_args()
    ctx = p.build_context("discovery_xcpd", config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)
    # Sanity checks: required flags present, no unresolved placeholders
    assert "--mode abcd" in script
    assert "--combine-runs" in script
    assert "--band-stop-min 12" in script
    assert "--motion-filter-type notch" in script
    assert "--participant-label" in script
    assert "{" not in script.replace("${SLURM_ARRAY_TASK_ID}", "").replace("${subject}", "")
    assert "apptainer run" in script
```

- [ ] **Step 1.2: Run test to verify it fails**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run pytest tests/pipelines/test_xcpd.py -v
```
Expected: `ModuleNotFoundError: No module named 'neuro_workflow.pipelines.xcpd'`

- [ ] **Step 1.3: Create `src/neuro_workflow/pipelines/xcpd.py`**

```python
import os
import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path

from neuro_workflow.core.slurm import count_subjects
from neuro_workflow.pipelines.base import register, build_mail_line, resolve_resources


class XcpdPipeline:
    name = "xcpd"
    docker_uri = "docker://pennlinc/xcp_d"
    template_name = "xcpd.sbatch"
    default_resources = {
        "nthreads": 16,
        "mem_per_cpu_gb": 24,
        "time": "1-00:00:00",
    }

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--version", default=None, help="XCP-D version tag (e.g. 26.0.2)")
        parser.add_argument("--fmriprep-version", default="25.2.4",
                            help="fMRIPrep derivatives version to consume (default: 25.2.4)")
        parser.add_argument("--xcpd-args", default="", help="Additional XCP-D arguments (appended to hardcoded flags)")
        parser.add_argument("--fs-license", default="~/license.txt", help="FreeSurfer license file")
        parser.add_argument("--nthreads", type=int, default=None, help="CPUs per task (default: 16)")
        parser.add_argument("--mem-per-cpu-gb", type=int, default=None, help="Memory per CPU in GB (default: 24)")
        parser.add_argument("--time", default=None, help="SLURM time limit (default: 1-00:00:00, bigmem cap)")
        parser.add_argument("--array-throttle", type=int, default=8, help="Max concurrent array tasks (default: 8)")
        parser.add_argument("--partition", default=None, help="SLURM partition (default: dataset config, typically 'bigmem')")

    def build_context(self, dataset_name: str, dataset_config: dict, args: Namespace) -> dict:
        if not getattr(args, "version", None):
            print("Error: --version is required for xcpd pipeline", file=sys.stderr)
            sys.exit(1)

        resources = resolve_resources(args, self.default_resources)
        nthreads = resources["nthreads"]
        mem_per_cpu_gb = resources["mem_per_cpu_gb"]
        time = resources["time"]

        n_subjects = count_subjects(dataset_config["subjects_file"])

        image_path = str(Path(dataset_config["image_dir"]) / f"xcpd_{args.version}.sif")
        fs_license = str(Path(args.fs_license).expanduser())

        scratch = os.environ.get("SCRATCH", "/tmp")
        work_dir = f"{scratch}/work/xcpd_{dataset_name}_{args.version}"

        fmriprep_dir = f"{dataset_config['bids_dir']}/derivatives/fmriprep_{args.fmriprep_version}"
        output_dir = f"{dataset_config['bids_dir']}/derivatives/xcp_d_{args.version}"
        log_dir = f"{output_dir}/logs"

        partition = args.partition if args.partition else dataset_config.get("partition", "bigmem")
        mail_line = build_mail_line(dataset_config)

        return {
            "dataset_name": dataset_name,
            "time": time,
            "n_subjects": n_subjects,
            "nthreads": nthreads,
            "mem_per_cpu_gb": mem_per_cpu_gb,
            "partition": partition,
            "log_dir": log_dir,
            "mail_line": mail_line,
            "subjects_file": dataset_config["subjects_file"],
            "image_path": image_path,
            "fmriprep_dir": fmriprep_dir,
            "output_dir": output_dir,
            "work_dir": work_dir,
            "fs_license": fs_license,
            "xcpd_version": args.version,
            "fmriprep_version": args.fmriprep_version,
            "xcpd_args": args.xcpd_args,
            "array_throttle": args.array_throttle,
        }


register(XcpdPipeline())
```

- [ ] **Step 1.4: Run tests — they will still fail because template doesn't exist**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run pytest tests/pipelines/test_xcpd.py::test_pipeline_attributes tests/pipelines/test_xcpd.py::test_default_resources tests/pipelines/test_xcpd.py::test_build_context_basic tests/pipelines/test_xcpd.py::test_build_context_version_required tests/pipelines/test_xcpd.py::test_build_context_custom_resources tests/pipelines/test_xcpd.py::test_build_context_custom_fmriprep_version -v
```
Expected: 6 tests PASS. The 7th (`test_template_renders`) will fail because the template doesn't exist yet — leave that for Task 2.

- [ ] **Step 1.5: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add src/neuro_workflow/pipelines/xcpd.py tests/pipelines/test_xcpd.py
git -c commit.gpgsign=false commit -m "feat(xcpd): add XcpdPipeline class + tests

Mirrors the FmriprepPipeline/QsiprepPipeline pattern. Default resources
target bigmem (16 cpus x 24 GB = 384 GB, 24h walltime). build_context
emits fmriprep_dir and output_dir paths derived from the dataset's
bids_dir and the user-specified fmriprep/xcpd versions."
```

---

## Task 2: sbatch template

**Files:**
- Create: `src/neuro_workflow/templates/xcpd.sbatch`

- [ ] **Step 2.1: Create the template file**

Create `src/neuro_workflow/templates/xcpd.sbatch`:

```bash
#!/bin/bash
#SBATCH -J xcpd_{dataset_name}
#SBATCH --time={time}
#SBATCH -n 1
#SBATCH --array=1-{n_subjects}%{array_throttle}
#SBATCH --cpus-per-task={nthreads}
#SBATCH --mem-per-cpu={mem_per_cpu_gb}G
#SBATCH -p {partition}
#SBATCH -o {log_dir}/%x-%A-%a.out
#SBATCH -e {log_dir}/%x-%A-%a.err
{mail_line}

subject=$(sed "${{SLURM_ARRAY_TASK_ID}}q;d" {subjects_file} | tr -d '\r')

XCPD_IMG="{image_path}"

mkdir -p "{log_dir}"
mkdir -p "{work_dir}/sub-${{subject}}"
mkdir -p "{output_dir}/sub-${{subject}}"

apptainer run --cleanenv \
  -B {fmriprep_dir}:/data:ro \
  -B {output_dir}:/out \
  -B {work_dir}:/work \
  -B {fs_license}:/opt/freesurfer/license.txt \
  "$XCPD_IMG" \
  /data /out participant \
  --participant-label "$subject" \
  -w /work/sub-${{subject}} \
  --mode abcd \
  --despike \
  --fd-thresh 0.3 \
  --input-type fmriprep \
  --warp-surfaces-native2std \
  --combine-runs \
  --linc-qc \
  --min-time 150 \
  --min-coverage 0.5 \
  --band-stop-min 12 --band-stop-max 20 --motion-filter-type notch \
  --omp-nthreads 3 \
  --nprocs {nthreads} \
  --smoothing 0 \
  --motion-filter-order 4 \
  {xcpd_args} \
  -vv

exitcode=$?
echo "Task ${{SLURM_ARRAY_TASK_ID}} ($subject) finished with exit code $exitcode"
exit $exitcode
```

Notes for the implementer:
- `{{var}}` becomes `{var}` after Python string-format escapes (this is how the existing fmriprep.sbatch handles bash variable references). The `render_template` helper uses `.format()` so all `{key}` placeholders need a context entry.
- Work dir is per-subject (`{work_dir}/sub-${{subject}}/`) so array tasks don't collide.
- No cleanup on success — we preserve the nipype cache so timeout-resume works.

- [ ] **Step 2.2: Run the template render test**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run pytest tests/pipelines/test_xcpd.py::test_template_renders -v
```
Expected: PASS. Template renders with no unresolved `{...}` placeholders and contains the expected XCP-D flags.

- [ ] **Step 2.3: Run the whole test file to confirm all 7 tests pass**

```bash
uv run pytest tests/pipelines/test_xcpd.py -v
```
Expected: 7/7 PASS.

- [ ] **Step 2.4: Commit**

```bash
git add src/neuro_workflow/templates/xcpd.sbatch
git -c commit.gpgsign=false commit -m "feat(xcpd): add sbatch template with Gracie's canonical flags

Hardcodes the XCP-D denoising flag set from
/oak/.../grimsrud/projects/pfm_compare/code/fmriprep_xcpd/run_xcpd.sh
(--mode abcd --despike --fd-thresh 0.3 --combine-runs --linc-qc
--min-time 150 --min-coverage 0.5, notch motion filter 12-20 Hz).
Per-subject work dir under {work_dir}/sub-\$subject/ for array-task
isolation. No work-dir cleanup so nipype can resume timed-out runs."
```

---

## Task 3: CLI auto-registration

**Files:**
- Modify: `src/neuro_workflow/cli.py`

- [ ] **Step 3.1: Read the existing auto-registration block**

```bash
grep -n "import neuro_workflow.pipelines" /home/users/logben/neuro_workflow/src/neuro_workflow/cli.py
```
Expected: lines 20-29 listing the existing pipeline imports.

- [ ] **Step 3.2: Add the xcpd import**

Edit `src/neuro_workflow/cli.py` — locate the block:

```python
import neuro_workflow.pipelines.mshbm  # noqa: F401
import neuro_workflow.pipelines.bidsify  # noqa: F401
```

Add after it (so the imports are alphabetical-ish, fmriprep-family adjacent):

```python
import neuro_workflow.pipelines.mshbm  # noqa: F401
import neuro_workflow.pipelines.bidsify  # noqa: F401
import neuro_workflow.pipelines.xcpd  # noqa: F401
```

- [ ] **Step 3.3: Verify auto-registration works**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run python -c "from neuro_workflow.cli import list_pipelines; print(sorted(list_pipelines()))"
```
Expected: a list containing `'xcpd'` along with the other pipelines.

- [ ] **Step 3.4: Run full test suite to make sure nothing broke**

```bash
uv run pytest tests/pipelines/ -v 2>&1 | tail -20
```
Expected: all pipeline tests pass (including the new xcpd ones).

- [ ] **Step 3.5: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add src/neuro_workflow/cli.py
git -c commit.gpgsign=false commit -m "feat(xcpd): wire xcpd into the cli pipeline registry"
```

---

## Task 4: Container symlink

**Files:**
- Create: `/home/groups/russpold/singularity_images/xcpd_26.0.2.sif` (symlink)

- [ ] **Step 4.1: Verify the source container exists**

```bash
ls -lh /oak/stanford/groups/russpold/shared/containers/xcp_d-26.0.2.sif
```
Expected: 1.8G file.

- [ ] **Step 4.2: Verify the destination is writable**

```bash
ls -ld /home/groups/russpold/singularity_images/
```
Expected: directory listing showing group write permission for russpold (the `g+w` flag in `drwxrwsr-x`).

If write permission is missing, request the user grant access or symlink into an alternate writable location and override `image_dir` in dataset registration.

- [ ] **Step 4.3: Create the symlink**

```bash
ln -sf /oak/stanford/groups/russpold/shared/containers/xcp_d-26.0.2.sif \
       /home/groups/russpold/singularity_images/xcpd_26.0.2.sif
ls -l /home/groups/russpold/singularity_images/xcpd_26.0.2.sif
```
Expected: symlink listing showing `-> /oak/.../shared/containers/xcp_d-26.0.2.sif`.

- [ ] **Step 4.4: Verify the symlink resolves and apptainer can read it**

```bash
apptainer exec /home/groups/russpold/singularity_images/xcpd_26.0.2.sif xcp_d --version 2>&1 | head -3
```
Expected: XCP-D version string (e.g. `xcp_d v26.0.2`).

If this fails (file not found, permission denied), troubleshoot before proceeding to dataset registration.

---

## Task 5: Subjects files

**Files:**
- Create: `/home/users/logben/neuro_workflow/subjects_discovery_xcpd.txt`
- Create: `/home/users/logben/neuro_workflow/subjects_validation_xcpd.txt`

- [ ] **Step 5.1: Create the discovery subjects file (4 subjects, excluding s03)**

```bash
cat > /home/users/logben/neuro_workflow/subjects_discovery_xcpd.txt <<'EOF'
s10
s19
s29
s43
EOF
cat /home/users/logben/neuro_workflow/subjects_discovery_xcpd.txt
```
Expected: 4 lines printed.

- [ ] **Step 5.2: Create the validation subjects file (41 subjects)**

```bash
cat > /home/users/logben/neuro_workflow/subjects_validation_xcpd.txt <<'EOF'
s76
s180
s216
s247
s286
s295
s300
s320
s321
s336
s373
s394
s415
s480
s599
s645
s874
s956
s1035
s1057
s1058
s1127
s1134
s1175
s1189
s1258
s1267
s1270
s1273
s1292
s1314
s1326
s1338
s1351
s1391
s1399
s1402
s1408
s1445
s1481
s1486
EOF
wc -l /home/users/logben/neuro_workflow/subjects_validation_xcpd.txt
```
Expected: `41 /home/users/logben/neuro_workflow/subjects_validation_xcpd.txt`.

- [ ] **Step 5.3: Cross-check against the canonical validation list in pipeline_config**

```bash
python3 -c "
import json
cfg = json.load(open('/home/users/logben/neuro_workflow/config/pipeline_config.json'))
canon = sorted(cfg['samples']['validation'])
ours = sorted(open('/home/users/logben/neuro_workflow/subjects_validation_xcpd.txt').read().split())
print('canon:', len(canon))
print('ours:', len(ours))
print('match:', canon == ours)
print('diff:', set(canon) ^ set(ours))
"
```
Expected: `match: True`, `diff: set()`.

If diff is non-empty, regenerate the file from pipeline_config to match exactly:
```bash
python3 -c "
import json
cfg = json.load(open('/home/users/logben/neuro_workflow/config/pipeline_config.json'))
print('\n'.join(cfg['samples']['validation']))
" > /home/users/logben/neuro_workflow/subjects_validation_xcpd.txt
```

- [ ] **Step 5.4: Commit (subjects files are tracked)**

```bash
cd /home/users/logben/neuro_workflow
git add subjects_discovery_xcpd.txt subjects_validation_xcpd.txt
git -c commit.gpgsign=false commit -m "chore(xcpd): add subjects files for discovery + validation cohorts

Discovery excludes s03 (fmriprep rerun in flight as of 2026-05-20);
will be added later via 'echo s03 >> subjects_discovery_xcpd.txt'.
Validation is the full 41-subject canonical list."
```

---

## Task 6: Register datasets

**Files:**
- Modifies: `~/.neuro_workflow/datasets.json` (via `neuro-run add-dataset` CLI)

- [ ] **Step 6.1: Register `discovery_xcpd`**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run neuro-run add-dataset discovery_xcpd \
  --bids-dir /scratch/users/logben/discovery_bids \
  --subjects-file /home/users/logben/neuro_workflow/subjects_discovery_xcpd.txt \
  --partition bigmem \
  --mail-user logben@stanford.edu
```
Expected: `Dataset 'discovery_xcpd' saved.`

- [ ] **Step 6.2: Register `validation_xcpd`**

```bash
uv run neuro-run add-dataset validation_xcpd \
  --bids-dir /scratch/users/logben/validation_bids \
  --subjects-file /home/users/logben/neuro_workflow/subjects_validation_xcpd.txt \
  --partition bigmem \
  --mail-user logben@stanford.edu
```
Expected: `Dataset 'validation_xcpd' saved.`

- [ ] **Step 6.3: Verify both datasets are registered**

```bash
uv run neuro-run show --list 2>&1 | grep xcpd
```
Expected:
```
  discovery_xcpd: /scratch/users/logben/discovery_bids
  validation_xcpd: /scratch/users/logben/validation_bids
```

---

## Task 7: Preview the rendered sbatch

**No file changes — just verifies the pipeline produces a sensible script.**

- [ ] **Step 7.1: Render the discovery sbatch (don't submit yet)**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run neuro-run show xcpd discovery_xcpd --version 26.0.2 2>&1 | head -40
```
Expected: prints a complete sbatch script. Verify:
- `#SBATCH -J xcpd_discovery_xcpd`
- `#SBATCH --array=1-4%8`
- `#SBATCH --cpus-per-task=16`
- `#SBATCH --mem-per-cpu=24G`
- `#SBATCH -p bigmem`
- `#SBATCH --time=1-00:00:00`
- `XCPD_IMG="/home/groups/russpold/singularity_images/xcpd_26.0.2.sif"`
- Binds include `fmriprep_25.2.4:/data`, `xcp_d_26.0.2:/out`
- The XCP-D arg block has all of: `--mode abcd`, `--despike`, `--combine-runs`, `--band-stop-min 12 --band-stop-max 20 --motion-filter-type notch`

If any of these are wrong, fix the pipeline class or template before proceeding.

- [ ] **Step 7.2: Render the validation sbatch as a second sanity check**

```bash
uv run neuro-run show xcpd validation_xcpd --version 26.0.2 2>&1 | head -10
```
Expected: same shape, with `--array=1-41%8` and validation BIDS paths.

---

## Task 8: Sanity-submit one validation subject

**Files:** None (operational SLURM submission).

**Purpose:** Confirm XCP-D starts cleanly (no immediate BIDS validation failure like Gracie's last attempt). Not a runtime smoke test — just a "does it not die in the first 5 minutes" check. If it gets past initialization, we submit the rest of the cohort in Task 9.

- [ ] **Step 8.1: Create a single-subject subjects file**

```bash
cat > /tmp/subjects_xcpd_smoke.txt <<'EOF'
s76
EOF
```

- [ ] **Step 8.2: Temporarily re-register validation_xcpd to point at the smoke file**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run neuro-run add-dataset validation_xcpd_smoke \
  --bids-dir /scratch/users/logben/validation_bids \
  --subjects-file /tmp/subjects_xcpd_smoke.txt \
  --partition bigmem \
  --mail-user logben@stanford.edu
```
Expected: `Dataset 'validation_xcpd_smoke' saved.`

- [ ] **Step 8.3: Submit the smoke job**

```bash
uv run neuro-run submit xcpd validation_xcpd_smoke --version 26.0.2
```
Expected: `Submitted batch job <SMOKE_JID>`. Record JID.

- [ ] **Step 8.4: Wait for job to enter `R` state, then tail log**

```bash
# Wait until state == R
while [[ "$(squeue -j <SMOKE_JID> -h -o %t 2>/dev/null)" == "PD" ]]; do sleep 30; done
# Find the log file (path is in the rendered script's #SBATCH -o line)
log=$(ls -tr /scratch/users/logben/validation_bids/derivatives/xcp_d_26.0.2/logs/*-${SMOKE_JID}-*.out 2>/dev/null | tail -1)
sleep 60   # let xcp_d start
tail -50 "$log"
```
Expected: lines indicating XCP-D started — workflow logs, no immediate BIDSValidationError, no immediate Python traceback.

If you see `BIDSValidationError` or `Cannot find ...`, investigate before submitting the cohort. Likely causes: wrong fmriprep_dir bind, missing `dataset_description.json` (we verified this earlier — should be present).

- [ ] **Step 8.5: Once confirmed running cleanly, let it continue OR cancel**

If you want to keep the smoke job to also count as the first cohort job (it would otherwise be re-run as part of the full validation cohort), let it run. Otherwise, cancel:

```bash
scancel <SMOKE_JID>
```

Then continue to Task 9.

---

## Task 9: Submit full cohort (45 subjects)

**Files:** None (operational).

- [ ] **Step 9.1: Submit discovery (4 subjects)**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run neuro-run submit xcpd discovery_xcpd --version 26.0.2
```
Expected: `Submitted batch job <DISC_JID>` (array `<DISC_JID>_1` through `_4`).

- [ ] **Step 9.2: Submit validation (41 subjects)**

```bash
uv run neuro-run submit xcpd validation_xcpd --version 26.0.2
```
Expected: `Submitted batch job <VAL_JID>` (array `_1` through `_41`).

- [ ] **Step 9.3: Confirm queue state**

```bash
squeue -u logben | grep xcpd | head
```
Expected: many `PD` and up to 8 `R` xcpd jobs (throttle limit).

---

## Task 10: Resume protocol (only if a subject hits 24h)

**Files:** None (operational; only execute if needed).

- [ ] **Step 10.1: Identify failed/timed-out jobs**

```bash
sacct -u logben --starttime now-3days --format=JobID,JobName,State,ExitCode,Elapsed -X 2>&1 | grep xcpd | grep -E "TIMEOUT|FAILED"
```

Note the array index of each failure. The subject is line `N` in the relevant subjects file (1-indexed).

- [ ] **Step 10.2: Verify the work dir was preserved**

For a failed task at array index N, find the subject:
```bash
SUB=$(sed "${N}q;d" /home/users/logben/neuro_workflow/subjects_validation_xcpd.txt)
ls -d /scratch/users/logben/work/xcpd_validation_xcpd_26.0.2/sub-${SUB}/ 2>&1
```
Expected: directory exists.

- [ ] **Step 10.3: Resubmit the dataset**

```bash
cd /home/users/logben/neuro_workflow
module load uv
uv run neuro-run submit xcpd validation_xcpd --version 26.0.2
```

The SLURM array will re-run all indices. For subjects that already completed (exit 0), XCP-D detects the existing output dir and skips. For subjects that timed out, nipype reads the cached work dir and resumes from the last completed node.

If you want to avoid re-running succeeded subjects entirely, create a smaller subjects file with just the failed-subject labels and register a temporary dataset for it.

---

## Task 11: Update WORKFLOW.md

**Files:**
- Modify: `docs/WORKFLOW.md`

- [ ] **Step 11.1: Read the current WORKFLOW.md to find the last numbered step**

```bash
grep -n "^## Step" /home/users/logben/neuro_workflow/docs/WORKFLOW.md
```
Expected: a list of steps (probably ending at Step 9: fMRIPrep).

- [ ] **Step 11.2: Append the new XCP-D step**

Open `docs/WORKFLOW.md` and after the last existing Step (e.g. "Step 9: fMRIPrep"), append:

```markdown
## Step 10. XCP-D post-fMRIPrep denoising

Once fMRIPrep is complete for a subject, run XCP-D 26.0.2 to produce
denoised BOLD + connectivity outputs. Uses the canonical flag set from
the lab's PFM-compare project.

Per-subject resources: bigmem partition, 384 GB, 24 h walltime. Throttle
array to 8 concurrent jobs to be polite to the lab queue.

```bash
uv run neuro-run submit xcpd discovery_xcpd --version 26.0.2
uv run neuro-run submit xcpd validation_xcpd --version 26.0.2
```

Outputs land at `<bids_dir>/derivatives/xcp_d_26.0.2/sub-<S>/`.

If a subject times out at 24 h, simply resubmit — nipype reads its cached
work dir at `$SCRATCH/work/xcpd_<dataset>_26.0.2/sub-<S>/` and resumes.
```

- [ ] **Step 11.3: Verify the addition**

```bash
tail -25 /home/users/logben/neuro_workflow/docs/WORKFLOW.md
```
Expected: the Step 10 block is present.

- [ ] **Step 11.4: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add docs/WORKFLOW.md docs/superpowers/specs/2026-05-20-xcpd-pipeline-integration-design.md docs/superpowers/plans/2026-05-20-xcpd-pipeline-integration.md
git -c commit.gpgsign=false commit -m "docs(xcpd): add Step 10 to WORKFLOW + commit spec + plan"
```

---

## Success criteria

- All 7 pipeline tests pass
- `neuro-run show xcpd discovery_xcpd --version 26.0.2` produces a valid sbatch
- Smoke job (sub-s76) starts cleanly and reaches workflow execution within 5 min of `R` state
- Cohort submission (45 subjects) lands in queue
- Eventually, all 45 subjects' XCP-D jobs exit 0 with outputs at
  `<bids_dir>/derivatives/xcp_d_26.0.2/sub-<S>/`

Once those are met, this plan is complete. Adding sub-s03 (after its fmriprep rerun finishes) is a one-line follow-up: `echo s03 >> subjects_discovery_xcpd.txt && uv run neuro-run submit xcpd discovery_xcpd --version 26.0.2`.
