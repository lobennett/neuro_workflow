# fMRIPrep Fieldmap↔BOLD Report Bug Reproduction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reproduce the fMRIPrep 25.2.5 fieldmap↔BOLD-reference alignment reportlet bug on sub-s8 (ses-01 good, ses-03 corrupt), using a BIDS filter file and a re-used FreeSurfer subject. Produces the output directory that a follow-up plan will inspect for root-cause.

**Architecture:** Add a minimal `--output-dir` flag to `neuro_workflow`'s fmriprep pipeline so the repro can write to scratch without touching Oak. Register the rdoc sample, pre-pull the 25.2.5 image, copy existing FreeSurfer outputs to scratch, submit a filtered run. A follow-up plan (written after this one completes) covers alignment verification, issue drafting, and the upstream PR.

**Tech Stack:** Python (neuro_workflow CLI), Apptainer/Singularity, SLURM, pytest, git, fmriprep 25.2.5 image.

---

## File Structure

**Files created:**
- `subjects_rdoc.txt` — one-line subject file (`s8`)
- `config/bids_filters/rdoc_s8_stroop.json` — BIDS filter scoping to ses-01+03, task-stroop
- `docs/superpowers/plans/2026-04-24-fmriprep-fmap-boldref-repro.md` (this file)
- (scratch, not in repo) `/scratch/users/logben/fmriprep_bug_repro/` — run output root

**Files modified:**
- `.gitignore` — add `work/` so issue/PR drafts stay local
- `src/neuro_workflow/pipelines/fmriprep.py` — add `--output-dir` flag + context
- `src/neuro_workflow/templates/fmriprep.sbatch` — add output bind line + use `{output_container}`
- `tests/pipelines/test_fmriprep.py` — add render tests for both default and override modes

---

### Task 1: Gitignore `work/` directory

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Add `work/` to `.gitignore`**

Append a new entry to `.gitignore`:

```
# Local scratch: issue/PR drafts, exploration notes
work/
```

- [ ] **Step 2: Verify**

Run: `git check-ignore -v work/`
Expected: prints `.gitignore:<line>:work/	work/` (or similar non-empty line)

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "$(cat <<'EOF'
chore: gitignore work/ for local drafts

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add `--output-dir` flag to fmriprep pipeline (TDD)

**Files:**
- Test: `tests/pipelines/test_fmriprep.py` (append)
- Modify: `src/neuro_workflow/pipelines/fmriprep.py`
- Modify: `src/neuro_workflow/templates/fmriprep.sbatch`

- [ ] **Step 1: Write three failing tests** (append to `tests/pipelines/test_fmriprep.py`)

```python
def test_fmriprep_output_dir_default(tmp_path):
    """When --output-dir is not set, derivatives land inside the BIDS bind."""
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
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir=None,
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert ctx["output_bind_line"] == ""
    assert ctx["output_container"] == "/data/derivatives"
    assert ctx["log_dir"] == "/oak/data/bids/derivatives/fmriprep_24.1.0/logs"


def test_fmriprep_output_dir_override(tmp_path):
    """When --output-dir is set, derivatives land in a bound external path."""
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
        version="25.2.5",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="~/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir="/scratch/users/logben/fmriprep_bug_repro",
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    assert "-B /scratch/users/logben/fmriprep_bug_repro:/out" in ctx["output_bind_line"]
    assert ctx["output_container"] == "/out"
    assert ctx["log_dir"] == "/scratch/users/logben/fmriprep_bug_repro/fmriprep_25.2.5/logs"


def test_fmriprep_render_with_output_dir(tmp_path):
    """Full render with --output-dir does NOT write into BIDS derivatives."""
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
        version="25.2.5",
        output_spaces="MNI152NLin2009cAsym:res-2",
        fmriprep_args="",
        fs_license="/home/user/license.txt",
        bids_filter_file=None,
        nthreads=None,
        mem_per_cpu_gb=None,
        time=None,
        output_dir="/scratch/users/logben/fmriprep_bug_repro",
    )

    ctx = p.build_context("test_ds", dataset_config, args)
    template_path = TEMPLATE_DIR / p.template_name
    script = render_template(template_path, ctx)

    assert "-B /scratch/users/logben/fmriprep_bug_repro:/out" in script
    assert "/out/fmriprep_25.2.5" in script
    assert "/data/derivatives" not in script
```

Also update the five existing tests in this file that build a `Namespace` (lines 45, 81, 110, 139, 171) to add `output_dir=None,` as a keyword so they don't rely on the `getattr` default behavior. Exact additions: add a new line `        output_dir=None,` immediately before the closing `)` of each Namespace call.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/pipelines/test_fmriprep.py -v
```

Expected: existing tests still pass (they don't assert on `output_bind_line`/`output_container`/`log_dir`); three new tests FAIL with `KeyError: 'output_bind_line'` (or similar) because `build_context` does not yet produce those keys.

- [ ] **Step 3: Modify `src/neuro_workflow/pipelines/fmriprep.py`**

Add to `add_cli_args` (after the existing `--bids-filter-file` line, before `--nthreads`):

```python
        parser.add_argument("--output-dir", default=None,
            help="Output derivatives root (default: <bids_dir>/derivatives)")
```

Replace the `log_dir = ...` line in `build_context` and the bids-filter block with:

```python
        output_dir = getattr(args, "output_dir", None)
        if output_dir:
            output_bind_line = f"-B {output_dir}:/out \\"
            output_container = "/out"
            log_dir = f"{output_dir}/fmriprep_{args.version}/logs"
        else:
            output_bind_line = ""
            output_container = "/data/derivatives"
            log_dir = f"{dataset_config['bids_dir']}/derivatives/fmriprep_{args.version}/logs"
```

Add to the returned dict (next to `config_bind_line`):

```python
            "output_bind_line": output_bind_line,
            "output_container": output_container,
```

- [ ] **Step 4: Modify `src/neuro_workflow/templates/fmriprep.sbatch`**

After the `{config_bind_line} \` line, insert a new line:

```
  {output_bind_line} \
```

Change the fmriprep invocation line:

```
  /data /data/derivatives/fmriprep_{fmriprep_version} participant \
```

to:

```
  /data {output_container}/fmriprep_{fmriprep_version} participant \
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/pipelines/test_fmriprep.py -v
```

Expected: all tests PASS (existing 6 + new 3 = 9 tests green).

- [ ] **Step 6: Run full template-render smoke test**

```bash
uv run pytest tests/test_all_templates_render.py -v
```

Expected: all tests PASS (no regression in other pipelines).

- [ ] **Step 7: Commit**

```bash
git add src/neuro_workflow/pipelines/fmriprep.py \
        src/neuro_workflow/templates/fmriprep.sbatch \
        tests/pipelines/test_fmriprep.py
git commit -m "$(cat <<'EOF'
feat: add --output-dir flag to fmriprep pipeline

Allows routing fmriprep derivatives to a path outside the BIDS directory
(e.g., scratch for one-off repro runs). Default behavior unchanged: when
--output-dir is not passed, derivatives still land in <bids_dir>/derivatives.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add rdoc subjects file + BIDS filter

**Files:**
- Create: `subjects_rdoc.txt`
- Create: `config/bids_filters/rdoc_s8_stroop.json`

- [ ] **Step 1: Create `subjects_rdoc.txt`** in the repo root with content:

```
s8
```

(single line, trailing newline)

- [ ] **Step 2: Create the BIDS filter JSON**

Create `config/bids_filters/rdoc_s8_stroop.json`:

```json
{
  "fmap": {"session": ["01", "03"]},
  "bold": {"session": ["01", "03"], "task": "stroop"},
  "t1w": {"session": "01"}
}
```

- [ ] **Step 3: Verify JSON is valid**

```bash
uv run python -c "import json; json.load(open('config/bids_filters/rdoc_s8_stroop.json'))"
```

Expected: no output (valid JSON loads silently).

- [ ] **Step 4: Commit**

```bash
git add subjects_rdoc.txt config/bids_filters/rdoc_s8_stroop.json
git commit -m "$(cat <<'EOF'
feat: add rdoc sample subjects file and sub-s8 stroop BIDS filter

For reproducing the fmriprep fieldmap<->boldref alignment report bug on
sub-s8 ses-01 vs ses-03 (51 vs 60 slice fmap mismatch).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Register rdoc dataset with `neuro-run`

**Files:**
- Modifies: `~/.neuro_workflow/datasets.json` (user state, not committed)

- [ ] **Step 1: Register the dataset**

```bash
cd /home/users/logben/neuro_workflow
uv run neuro-run add-dataset rdoc \
  --bids-dir /oak/stanford/groups/russpold/data/rdoc_grant/rdoc_fmri_bids \
  --subjects-file subjects_rdoc.txt \
  --partition russpold \
  --mail-user logben@stanford.edu
```

Expected output: `Dataset 'rdoc' saved.`

- [ ] **Step 2: Verify registration**

```bash
uv run neuro-run show --list
```

Expected: listing includes `rdoc: /oak/stanford/groups/russpold/data/rdoc_grant/rdoc_fmri_bids`.

---

### Task 5: Preview rendered sbatch (no submit)

**Files:** None written.

- [ ] **Step 1: Render and inspect the sbatch script**

```bash
cd /home/users/logben/neuro_workflow
uv run neuro-run show fmriprep rdoc \
  --version 25.2.5 \
  --output-dir /scratch/users/logben/fmriprep_bug_repro \
  --bids-filter-file config/bids_filters/rdoc_s8_stroop.json \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsnative func anat" \
  --fmriprep-args "--notrack --skip-bids-validation" \
  --time 04:00:00 --mem-per-cpu-gb 8 --nthreads 8
```

- [ ] **Step 2: Sanity-check the rendered script**

Visually confirm these substrings are present in the output:
- `#SBATCH --array=1-1%` (only 1 subject)
- `#SBATCH --time=04:00:00`
- `-B /scratch/users/logben/fmriprep_bug_repro:/out`
- `-B /home/users/logben/neuro_workflow/config/bids_filters:/config`
- `/out/fmriprep_25.2.5 participant`
- `--bids-filter-file /config/rdoc_s8_stroop.json`
- `--notrack`
- `--skip-bids-validation`

Confirm these substrings are ABSENT:
- `/data/derivatives` (should be replaced by `/out`)

If anything is wrong, fix the template or pipeline code and add a regression test before proceeding.

---

### Task 6: Pre-pull fmriprep 25.2.5 Singularity image

**Files:** Produces `/home/groups/russpold/singularity_images/fmriprep_25.2.5.sif` on disk.

- [ ] **Step 1: Check if image already exists**

```bash
ls -lh /home/groups/russpold/singularity_images/fmriprep_25.2.5.sif 2>&1
```

If present (>1 GB) — skip to next task.

- [ ] **Step 2: Pull via compute node, block until done**

**Agentic executor note:** use the Bash tool with `run_in_background: true` and poll via `squeue`. Do NOT use `sbatch --wait` synchronously — a 10+-minute pull exceeds the Bash tool's 10-minute hard cap.

Submit:
```bash
sbatch -p russpold --mem=8G --time=00:30:00 \
  --job-name=fmriprep_pull \
  -o /tmp/fmriprep_pull.log \
  --wrap "apptainer pull /home/groups/russpold/singularity_images/fmriprep_25.2.5.sif docker://nipreps/fmriprep:25.2.5"
```

Record the JOBID. Poll with:
```bash
sacct -j <JOBID> --format=JobID,State,Elapsed,ExitCode
```
Re-run until `State=COMPLETED`. Expected runtime 5–15 min.

- [ ] **Step 3: Verify image**

```bash
ls -lh /home/groups/russpold/singularity_images/fmriprep_25.2.5.sif
apptainer exec /home/groups/russpold/singularity_images/fmriprep_25.2.5.sif fmriprep --version
```

Expected: SIF file >1 GB, `fmriprep --version` prints `fmriprep v25.2.5`.

---

### Task 7: Copy existing FreeSurfer to scratch

**Files:** Produces `/scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sourcedata/freesurfer/sub-s8/` on disk.

- [ ] **Step 1: Create output scaffold**

```bash
mkdir -p /scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sourcedata
mkdir -p /scratch/users/logben/fmriprep_bug_repro/work
```

- [ ] **Step 2: Check scratch has room**

```bash
du -sh /oak/stanford/groups/russpold/data/rdoc_grant/rdoc_fmri_bids/derivatives/fmriprep_25.2.0/sourcedata/freesurfer/sub-s8
df -h /scratch/users/logben
```

Confirm scratch free space is >> FreeSurfer subject size (usually 1–3 GB).

- [ ] **Step 3: Copy FreeSurfer (use compute node for big I/O)**

Submit (not blocking):
```bash
sbatch -p russpold --mem=4G --time=00:30:00 \
  --job-name=fs_copy \
  -o /tmp/fs_copy.log \
  --wrap "cp -r /oak/stanford/groups/russpold/data/rdoc_grant/rdoc_fmri_bids/derivatives/fmriprep_25.2.0/sourcedata/freesurfer /scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sourcedata/"
```

Record JOBID. Poll `sacct -j <JOBID>` until `State=COMPLETED`. Expected runtime: 2–10 min.

- [ ] **Step 4: Verify copy integrity**

```bash
ls /scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sourcedata/freesurfer/sub-s8/scripts/build-stamp.txt
cat /scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sourcedata/freesurfer/sub-s8/scripts/build-stamp.txt
```

Expected: file exists, contents `freesurfer-linux-ubuntu22_x86_64-7.3.2-20220804-6354275`.

---

### Task 8: Submit the reproduction run

**Files:** Produces output in `/scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/`.

- [ ] **Step 1: Submit**

```bash
cd /home/users/logben/neuro_workflow
uv run neuro-run submit fmriprep rdoc \
  --version 25.2.5 \
  --output-dir /scratch/users/logben/fmriprep_bug_repro \
  --bids-filter-file config/bids_filters/rdoc_s8_stroop.json \
  --output-spaces "MNI152NLin2009cAsym:res-2 fsnative func anat" \
  --fmriprep-args "--notrack --skip-bids-validation" \
  --time 04:00:00 --mem-per-cpu-gb 8 --nthreads 8
```

Expected: Prints the rendered sbatch, then `Submitted batch job <JOBID>`. Record the JOBID.

- [ ] **Step 2: Verify job is queued/running**

```bash
squeue -u $USER -o "%.10i %.20j %.8T %.10M %.6D %R"
```

Expected: a row with name `fmriprep_rdoc` in PENDING or RUNNING state.

---

### Task 9: Monitor run to completion

**Files:** Final outputs under `/scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/`.

- [ ] **Step 1: Check job state (do NOT block in a wait loop)**

Run this single-shot check; if still running, wait (disconnect / come back later) and re-run. Agentic executors should **not** sit in a `while` loop — shell command timeout is short. If running the plan interactively, the user may choose to background-monitor.

```bash
JOBID=<record from Task 8>
sacct -j $JOBID --format=JobID,State,Elapsed,ExitCode
```

Expected end state: `State=COMPLETED ExitCode=0:0`. Other common states:
- `RUNNING` / `PENDING` — not done yet; wait and retry this step.
- `FAILED` / `TIMEOUT` / `OUT_OF_MEMORY` — investigate logs (next step).

If failed: inspect `sacct -j $JOBID --format=JobID,State,ExitCode,Reason` and the log at `/scratch/users/logben/fmriprep_bug_repro/fmriprep_25.2.5/logs/fmriprep_rdoc-<JOBID>-1.{out,err}`. Do NOT retry blindly — root-cause the failure before resubmission.

- [ ] **Step 2: Confirm HTML report exists**

```bash
ls /scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sub-s8.html
```

Expected: file exists.

---

### Task 10: Inventory outputs (hand-off to follow-up plan)

**Files:** None written. Output becomes input for the follow-up plan.

- [ ] **Step 1: Inventory output filenames**

```bash
OUT=/scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sub-s8
for sess in 01 03; do
  echo "=== ses-$sess ==="
  ls $OUT/ses-$sess/fmap/ 2>/dev/null
  ls $OUT/ses-$sess/func/*bold* $OUT/ses-$sess/func/*boldref* 2>/dev/null
  ls $OUT/ses-$sess/xfm/ 2>/dev/null
done
```

- [ ] **Step 2: Inventory figures**

```bash
ls $OUT/figures/ | grep -i "fmap\|sdc\|fieldmap\|bold"
```

- [ ] **Step 3: Save inventory + report links to `work/`**

```bash
mkdir -p /home/users/logben/neuro_workflow/work
OUT=/scratch/users/logben/fmriprep_bug_repro/derivatives/fmriprep_25.2.5/sub-s8
{
  echo "# fMRIPrep 25.2.5 sub-s8 output inventory"
  echo "Generated: $(date)"
  echo
  echo "## Report HTML"
  echo "$OUT.html"
  echo
  echo "## fmap/"
  for sess in 01 03; do
    echo "### ses-$sess"
    ls $OUT/ses-$sess/fmap/ 2>/dev/null | sed 's/^/- /'
  done
  echo
  echo "## xfm/"
  for sess in 01 03; do
    echo "### ses-$sess"
    ls $OUT/ses-$sess/xfm/ 2>/dev/null | sed 's/^/- /'
  done
  echo
  echo "## figures/"
  ls $OUT/figures/ 2>/dev/null | grep -iE "fmap|sdc|fieldmap|bold" | sed 's/^/- /'
} > /home/users/logben/neuro_workflow/work/fmriprep_output_inventory.md
cat /home/users/logben/neuro_workflow/work/fmriprep_output_inventory.md
```

- [ ] **Step 4: Report to user, stop here**

Plan 1 complete. Output to report: contents of `work/fmriprep_output_inventory.md` plus:

- confirmation the sub-s8.html report contains the `Alignment between the anatomical reference of the fieldmap and the BOLD reference` section with a broken figure for ses-03 and a working one for ses-01
- the JOBID + runtime (from `sacct`)

Do NOT start on issue drafting, alignment verification, or PR work. Those belong to a follow-up plan written against the actual output inventory (exact filenames can vary by fmriprep output version).

---

## Follow-up Plan (not yet written)

After Task 10 completes, write a second plan
(`docs/superpowers/plans/2026-04-24-fmriprep-bug-issue-and-pr.md`) covering:

1. Apply `from-fmap_to-boldref` transform with `antsApplyTransforms` for both sessions
2. Open fsleyes overlay, screenshot alignment for both sessions (to prove coreg is fine)
3. Draft GitHub issue at `work/fmriprep_issue_draft.md`
4. User reviews issue draft; if approved, file via `gh issue create` on the correct repo
5. Fork + clone target repo (`fmriprep`, `sdcflows`, or `niworkflows`)
6. Read CONTRIBUTING + locate reportlet code, root-cause the bug
7. Write failing unit test, apply minimal fix, run test suite
8. Draft PR description at `work/fmriprep_pr_description.md`
9. User reviews PR draft; if approved, push + `gh pr create`

The follow-up plan is deferred because exact filenames, root-cause location, and fix shape
depend on runtime data from Task 10 and code inspection that hasn't been done yet.
