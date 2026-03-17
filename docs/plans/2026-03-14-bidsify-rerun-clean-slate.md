# BIDS Rerun with Clean Slate: Archive, Rebuild, Validate

**Goal:** Archive current BIDS directories, rebuild Singularity container with updated code, re-run bidsify pipeline on all three samples, and verify improvements in corrupted files and duplicate handling.

**Context:** Recent bidsify improvements (reduced workers, safe metadata patching, duplicate detection) need verification on fresh BIDS outputs. Current directories have accumulated iterations and debugging artifacts.

**Key Verification Points:**
1. Fewer corrupted JSON files (test for RepetitionTime presence)
2. Proper .bidsignore entries for duplicate anatomical scans (e.g., s19 second T1w)
3. Proper .bidsignore entries for duplicate DWI scans
4. Reduced "missing metadata" validation errors

**Estimated Timeline:**
- Archive: ~5 min
- Container build: ~30 min
- Bidsify rerun: ~3-4 hours (all 57 subjects)
- Validation: ~1-2 hours

---

## Task 1: Archive Current BIDS Directories

**Files:**
- Source: `/scratch/users/logben/discovery_bids`
- Source: `/scratch/users/logben/validation_bids`
- Source: `/scratch/users/logben/excluded_bids`
- Target: `/scratch/users/logben/` (archive subdirs created here)

**Step 1: Verify current BIDS directory sizes**

Run:
```bash
du -sh /scratch/users/logben/discovery_bids /scratch/users/logben/validation_bids /scratch/users/logben/excluded_bids
```

Expected: Shows sizes (94G, 796G, 49G respectively)

**Step 2: Archive discovery_bids**

Run:
```bash
mv /scratch/users/logben/discovery_bids /scratch/users/logben/discovery_bids.archive_$(date +%Y%m%d_%H%M%S)
```

Expected: Directory renamed to `discovery_bids.archive_20260314_HHMMSS`

**Step 3: Archive validation_bids**

Run:
```bash
mv /scratch/users/logben/validation_bids /scratch/users/logben/validation_bids.archive_$(date +%Y%m%d_%H%M%S)
```

Expected: Directory renamed to `validation_bids.archive_20260314_HHMMSS`

**Step 4: Archive excluded_bids**

Run:
```bash
mv /scratch/users/logben/excluded_bids /scratch/users/logben/excluded_bids.archive_$(date +%Y%m%d_%H%M%S)
```

Expected: Directory renamed to `excluded_bids.archive_20260314_HHMMSS`

**Step 5: Verify archives exist and originals are gone**

Run:
```bash
ls -lh /scratch/users/logben/ | grep -E "bids|archive"
```

Expected: Shows three `.archive_*` directories, no `discovery_bids`, `validation_bids`, or `excluded_bids`

---

## Task 2: Rebuild Singularity Container

**Files:**
- Definition: `/home/users/logben/neuro_workflow/neuro_workflow.def`
- Output: `/home/groups/russpold/singularity_images/neuro_workflow.sif`

**Step 1: Create container build SLURM script**

Create `/tmp/build_container.sbatch`:

```bash
#!/bin/bash
#SBATCH --job-name=build-container
#SBATCH --partition=russpold
#SBATCH --time=01:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=4
#SBATCH --output=/home/users/logben/neuro_workflow/build_logs/container_build_%j.log
#SBATCH --error=/home/users/logben/neuro_workflow/build_logs/container_build_%j.err

set -e

echo "Starting Singularity container build..."
echo "Time: $(date)"
echo "Definition: /home/users/logben/neuro_workflow/neuro_workflow.def"
echo "Output: /home/groups/russpold/singularity_images/neuro_workflow.sif"
echo ""

mkdir -p /home/users/logben/neuro_workflow/build_logs

apptainer build --fakeroot --force \
    /home/groups/russpold/singularity_images/neuro_workflow.sif \
    /home/users/logben/neuro_workflow/neuro_workflow.def

echo ""
echo "Container build completed at $(date)"
echo "Size:"
ls -lh /home/groups/russpold/singularity_images/neuro_workflow.sif
```

**Step 2: Submit container build job**

Run:
```bash
sbatch /tmp/build_container.sbatch
```

Expected: Job ID printed (e.g., "Submitted batch job 18687600")

**Step 3: Monitor container build**

Run (repeat until job completes):
```bash
squeue -u logben -n "build-container"
```

Expected: Job appears with "R" (running), disappears when done

**Step 4: Verify build completed successfully**

Run:
```bash
tail -30 /home/users/logben/neuro_workflow/build_logs/container_build_*.log
```

Expected: Last line shows "Container build completed at [timestamp]" and no errors

**Step 5: Verify container image exists and has reasonable size**

Run:
```bash
ls -lh /home/groups/russpold/singularity_images/neuro_workflow.sif
```

Expected: File exists, size > 1G (typically ~3-5G)

---

## Task 3: Re-run Bidsify on Discovery Sample

**Files:**
- Output: `/scratch/users/logben/discovery_bids/` (new, clean directory)
- Logs: `/home/users/logben/neuro_workflow/bidsify_logs/discovery_rerun_*.log`

**Step 1: Create discovery bidsify SLURM script**

Create `/tmp/bidsify_discovery.sbatch`:

```bash
#!/bin/bash
#SBATCH --job-name=bidsify-discovery
#SBATCH --partition=russpold
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=/home/users/logben/neuro_workflow/bidsify_logs/discovery_rerun_%j.log
#SBATCH --error=/home/users/logben/neuro_workflow/bidsify_logs/discovery_rerun_%j.err

set -e

cd /home/users/logben/neuro_workflow

echo "=========================================="
echo "BIDSIFY DISCOVERY - Clean Slate Rerun"
echo "=========================================="
echo "Job ID: $SLURM_JOB_ID"
echo "Start: $(date)"
echo ""

uv run python -m neuro_workflow.cli bidsify discovery \
    --output-dir /scratch/users/logben/discovery_bids \
    --overwrite \
    -v 2>&1 | tee -a /home/users/logben/neuro_workflow/bidsify_logs/discovery_rerun_$SLURM_JOB_ID.log

echo ""
echo "Discovery bidsify completed at $(date)"
echo "BIDS directory: /scratch/users/logben/discovery_bids"
```

**Step 2: Submit discovery bidsify job**

Run:
```bash
sbatch /tmp/bidsify_discovery.sbatch
```

Expected: Job ID printed (e.g., "Submitted batch job 18687610")

**Step 3: Monitor discovery bidsify job**

Run (repeat until completion):
```bash
squeue -u logben -n "bidsify-discovery"
```

Expected: Job runs for 30-60 minutes, then disappears

**Step 4: Verify discovery_bids was created with data**

Run:
```bash
ls /scratch/users/logben/discovery_bids/ | head -20
```

Expected: Shows `dataset_description.json`, `.bidsignore`, and 5 subject directories (sub-s03, sub-s10, sub-s19, sub-s29, sub-s43)

**Step 5: Check discovery .bidsignore for duplicate entries**

Run:
```bash
cat /scratch/users/logben/discovery_bids/.bidsignore | head -20
```

Expected: Shows entries for duplicate anatomical scans (s19 MPRAGEPromo_T1w), duplicate DWI, and any irreconcilable scans

---

## Task 4: Re-run Bidsify on Validation Sample (Non-Excluded)

**Files:**
- Output: `/scratch/users/logben/validation_bids/` (new, clean directory)
- Logs: `/home/users/logben/neuro_workflow/bidsify_logs/validation_rerun_*.log`

**Step 1: Create validation bidsify SLURM script**

Create `/tmp/bidsify_validation.sbatch`:

```bash
#!/bin/bash
#SBATCH --job-name=bidsify-validation
#SBATCH --partition=russpold
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=/home/users/logben/neuro_workflow/bidsify_logs/validation_rerun_%j.log
#SBATCH --error=/home/users/logben/neuro_workflow/bidsify_logs/validation_rerun_%j.err

set -e

cd /home/users/logben/neuro_workflow

VALIDATION_SUBJECTS=(s76 s247 s216 s286 s295 s300 s320 s321 s336 s373 s394 s415 s480 s180 s599 s645 s874 s956 s1035 s1057 s1058 s1127 s1134 s1175 s1189 s1258 s1267 s1270 s1273 s1292 s1314 s1326 s1338 s1351 s1391 s1399 s1402 s1408 s1445 s1481 s1486)

echo "=========================================="
echo "BIDSIFY VALIDATION (non-excluded) - Clean Slate Rerun"
echo "=========================================="
echo "Job ID: $SLURM_JOB_ID"
echo "Start: $(date)"
echo "Subjects: ${#VALIDATION_SUBJECTS[@]}"
echo ""

uv run python -m neuro_workflow.cli bidsify validation \
    --output-dir /scratch/users/logben/validation_bids \
    --subjects "${VALIDATION_SUBJECTS[@]}" \
    --overwrite \
    -v 2>&1 | tee -a /home/users/logben/neuro_workflow/bidsify_logs/validation_rerun_$SLURM_JOB_ID.log

echo ""
echo "Validation bidsify completed at $(date)"
echo "BIDS directory: /scratch/users/logben/validation_bids"
```

**Step 2: Submit validation bidsify job**

Run:
```bash
sbatch /tmp/bidsify_validation.sbatch
```

Expected: Job ID printed

**Step 3: Monitor validation bidsify job**

Run (repeat until completion):
```bash
squeue -u logben -n "bidsify-validation"
```

Expected: Job runs for 2-3 hours

**Step 4: Verify validation_bids was created with data**

Run:
```bash
ls /scratch/users/logben/validation_bids/ | wc -l
```

Expected: Shows 43+ items (dataset_description.json, .bidsignore, .bids-validation/, 41 subject dirs)

**Step 5: Check validation .bidsignore for entries**

Run:
```bash
cat /scratch/users/logben/validation_bids/.bidsignore | head -30
```

Expected: Shows entries for duplicate anatomical/DWI scans and any irreconcilable runs

---

## Task 5: Re-run Bidsify on Excluded Subjects

**Files:**
- Output: `/scratch/users/logben/excluded_bids/` (new, clean directory)
- Logs: `/home/users/logben/neuro_workflow/bidsify_logs/excluded_rerun_*.log`

**Step 1: Create excluded bidsify SLURM script**

Create `/tmp/bidsify_excluded.sbatch`:

```bash
#!/bin/bash
#SBATCH --job-name=bidsify-excluded
#SBATCH --partition=russpold
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=/home/users/logben/neuro_workflow/bidsify_logs/excluded_rerun_%j.log
#SBATCH --error=/home/users/logben/neuro_workflow/bidsify_logs/excluded_rerun_%j.err

set -e

cd /home/users/logben/neuro_workflow

echo "=========================================="
echo "BIDSIFY EXCLUDED - Clean Slate Rerun"
echo "=========================================="
echo "Job ID: $SLURM_JOB_ID"
echo "Start: $(date)"
echo ""

uv run python -m neuro_workflow.cli bidsify validation \
    --output-dir /scratch/users/logben/excluded_bids \
    --subjects s214 s222 s250 s297 s432 s823 s968 s1165 s1178 s1266 s1320 \
    --overwrite \
    -v 2>&1 | tee -a /home/users/logben/neuro_workflow/bidsify_logs/excluded_rerun_$SLURM_JOB_ID.log

echo ""
echo "Excluded bidsify completed at $(date)"
echo "BIDS directory: /scratch/users/logben/excluded_bids"
```

**Step 2: Submit excluded bidsify job**

Run:
```bash
sbatch /tmp/bidsify_excluded.sbatch
```

Expected: Job ID printed

**Step 3: Monitor excluded bidsify job**

Run (repeat until completion):
```bash
squeue -u logben -n "bidsify-excluded"
```

Expected: Job runs for 30-60 minutes

**Step 4: Verify excluded_bids was created with data**

Run:
```bash
ls /scratch/users/logben/excluded_bids/ | wc -l
```

Expected: Shows 13+ items (dataset_description.json, .bidsignore, 11 subject dirs)

**Step 5: Check excluded .bidsignore**

Run:
```bash
cat /scratch/users/logben/excluded_bids/.bidsignore | head -20
```

Expected: Shows entries for duplicate anatomical/DWI scans and any irreconcilable runs

---

## Task 6: Verify BIDS Directory Sizes

**Purpose:** Confirm all three BIDS directories contain complete data (comparable to archive sizes)

**Step 1: Check all three new directories exist**

Run:
```bash
ls -ld /scratch/users/logben/discovery_bids /scratch/users/logben/validation_bids /scratch/users/logben/excluded_bids
```

Expected: All three directories exist with current timestamps

**Step 2: Check total sizes**

Run:
```bash
du -sh /scratch/users/logben/discovery_bids /scratch/users/logben/validation_bids /scratch/users/logben/excluded_bids
```

Expected: Sizes approximately match archives (94G, 796G, 49G respectively)

**Step 3: Compare subject counts**

Run:
```bash
echo "Discovery subjects:" && ls /scratch/users/logben/discovery_bids | grep "^sub-" | wc -l
echo "Validation subjects:" && ls /scratch/users/logben/validation_bids | grep "^sub-" | wc -l
echo "Excluded subjects:" && ls /scratch/users/logben/excluded_bids | grep "^sub-" | wc -l
```

Expected: 5, 41, 11 respectively

---

## Task 7: Run BIDS Validator on All Three Datasets

**Files:**
- Validator image: `/home/groups/russpold/singularity_images/bids-validator_1.14.6.simg`
- Output logs: `/home/users/logben/neuro_workflow/validator_logs/discovery_validator_new.txt`, etc.

**Step 1: Create validator SLURM script**

Create `/tmp/validate_all_bids.sbatch`:

```bash
#!/bin/bash
#SBATCH --job-name=validate-bids
#SBATCH --partition=russpold
#SBATCH --time=03:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --output=/home/users/logben/neuro_workflow/validator_logs/validator_run_%j.log
#SBATCH --error=/home/users/logben/neuro_workflow/validator_logs/validator_run_%j.err

set -e

VALIDATOR_DIR="/home/users/logben/neuro_workflow/validator_logs"
mkdir -p "$VALIDATOR_DIR"

VALIDATOR_IMAGE="/home/groups/russpold/singularity_images/bids-validator_1.14.6.simg"

echo "=========================================="
echo "BIDS Validation - Clean Slate Datasets"
echo "=========================================="
echo "Job ID: $SLURM_JOB_ID"
echo "Start: $(date)"
echo ""

# Validate discovery
echo ">>> Validating Discovery Dataset"
apptainer run "$VALIDATOR_IMAGE" bids-validator \
    /scratch/users/logben/discovery_bids \
    --ignoreNiftiHeaders 2>&1 | tee "$VALIDATOR_DIR/discovery_validator_new.txt"

echo ""
echo ">>> Validating Validation Dataset"
apptainer run "$VALIDATOR_IMAGE" bids-validator \
    /scratch/users/logben/validation_bids \
    --ignoreNiftiHeaders 2>&1 | tee "$VALIDATOR_DIR/validation_validator_new.txt"

echo ""
echo ">>> Validating Excluded Dataset"
apptainer run "$VALIDATOR_IMAGE" bids-validator \
    /scratch/users/logben/excluded_bids \
    --ignoreNiftiHeaders 2>&1 | tee "$VALIDATOR_DIR/excluded_validator_new.txt"

echo ""
echo "=========================================="
echo "Validation completed at $(date)"
echo "Logs saved to: $VALIDATOR_DIR"
echo "=========================================="
```

**Step 2: Submit validator job**

Run:
```bash
sbatch /tmp/validate_all_bids.sbatch
```

Expected: Job ID printed

**Step 3: Monitor validator job**

Run (repeat until completion):
```bash
squeue -u logben -n "validate-bids"
```

Expected: Job runs for 1-2 hours

**Step 4: Check validator output summary**

Run:
```bash
tail -50 /home/users/logben/neuro_workflow/validator_logs/validator_run_*.log
```

Expected: Shows completion message with timestamps

**Step 5: Compare error counts (old vs. new)**

Run:
```bash
echo "=== DISCOVERY ===" && \
echo "Old errors:" && grep -c "^\[ERROR\]" /home/users/logben/neuro_workflow/validator_logs/discovery_validator.txt 2>/dev/null || echo "0" && \
echo "New errors:" && grep -c "^\[ERROR\]" /home/users/logben/neuro_workflow/validator_logs/discovery_validator_new.txt 2>/dev/null || echo "0" && \
echo ""
echo "=== VALIDATION ===" && \
echo "Old errors:" && grep -c "^\[ERROR\]" /home/users/logben/neuro_workflow/validator_logs/validation_validator.txt 2>/dev/null || echo "0" && \
echo "New errors:" && grep -c "^\[ERROR\]" /home/users/logben/neuro_workflow/validator_logs/validation_validator_new.txt 2>/dev/null || echo "0" && \
echo ""
echo "=== EXCLUDED ===" && \
echo "Old errors:" && grep -c "^\[ERROR\]" /home/users/logben/neuro_workflow/validator_logs/excluded_validator.txt 2>/dev/null || echo "0" && \
echo "New errors:" && grep -c "^\[ERROR\]" /home/users/logben/neuro_workflow/validator_logs/excluded_validator_new.txt 2>/dev/null || echo "0"
```

Expected: Shows reduced error counts in new runs

---

## Task 8: Inspect Key Validation Improvements

**Purpose:** Detailed verification of duplicate handling and metadata fixes

**Step 1: Check discovery .bidsignore has duplicate T1w entry**

Run:
```bash
grep "T1w\|T2w\|dwi" /scratch/users/logben/discovery_bids/.bidsignore | head -20
```

Expected: Shows entry for s19 second T1w or other duplicate anatomical scan

**Step 2: Check validation .bidsignore for duplicate entries**

Run:
```bash
grep "T1w\|T2w\|dwi" /scratch/users/logben/validation_bids/.bidsignore | head -20
```

Expected: Shows entries for duplicate scans across multiple subjects

**Step 3: Verify BOLD JSON has TaskName and RepetitionTime**

Run:
```bash
find /scratch/users/logben/validation_bids -name "*bold.json" -not -path "*.bidsignore*" | head -1 | xargs grep -H "TaskName\|RepetitionTime"
```

Expected: Shows both `"TaskName"` and `"RepetitionTime"` fields present

**Step 4: Verify fieldmap JSON has Units field**

Run:
```bash
find /scratch/users/logben/validation_bids -name "*fieldmap.json" | head -1 | xargs grep -H "Units"
```

Expected: Shows `"Units": "Hz"` in fieldmap sidecar

**Step 5: Check analysis.json for BOLD issues**

Run:
```bash
cat /scratch/users/logben/validation_bids/.bids-validation/analysis.json | python3 -m json.tool | head -50
```

Expected: Shows only missing_tr issues for specific problem scans, far fewer than before

---

## Task 9: Document Results and Archive Plan

**Purpose:** Record comparison metrics between old and new runs

**Step 1: Create summary report file**

Create `/home/users/logben/neuro_workflow/docs/bids-rerun-summary-2026-03-14.md`:

```markdown
# BIDS Rerun Results - Clean Slate (Mar 14, 2026)

## Container Build
- Status: [SUCCESS/FAILED]
- Image: /home/groups/russpold/singularity_images/neuro_workflow.sif
- Size: [size in GB]

## Bidsify Execution
- Discovery: [timestamp] - [X subjects processed]
- Validation: [timestamp] - [X subjects processed]
- Excluded: [timestamp] - [X subjects processed]

## Directory Sizes (new)
- discovery_bids: [size]
- validation_bids: [size]
- excluded_bids: [size]

## Validator Results (Error Reduction)

### Discovery
| Metric | Old | New | Change |
|--------|-----|-----|--------|
| ERROR count | ? | ? | ? |
| Missing TR | ? | ? | ? |
| Missing Units | ? | ? | ? |

### Validation
| Metric | Old | New | Change |
|--------|-----|-----|--------|
| ERROR count | ? | ? | ? |
| Missing TR | ? | ? | ? |
| Missing Units | ? | ? | ? |

### Excluded
| Metric | Old | New | Change |
|--------|-----|-----|--------|
| ERROR count | ? | ? | ? |

## Duplicate Scan Detection

### Anatomical Duplicates (.bidsignore entries)
- s19: Second T1w marked ✓/✗
- [Other subjects]: [status]

### DWI Duplicates
- [Subjects with duplicates]: [status]

## Corrupted File Fixes
- RepetitionTime parsing issues: [improved/same]
- JSON sidecar integrity: [improved/same]

## Next Steps
- [Archive old BIDS?]
- [Proceed with pipeline downstream?]
- [Further investigation needed?]
```

**Step 2: Run comparison script to populate report**

Run (in /home/users/logben/neuro_workflow):
```bash
cat > /tmp/compare_validators.sh << 'EOF'
#!/bin/bash

echo "Discovery old errors: $(grep -c '^\[ERROR\]' validator_logs/discovery_validator.txt 2>/dev/null || echo 0)"
echo "Discovery new errors: $(grep -c '^\[ERROR\]' validator_logs/discovery_validator_new.txt 2>/dev/null || echo 0)"
echo ""
echo "Validation old errors: $(grep -c '^\[ERROR\]' validator_logs/validation_validator.txt 2>/dev/null || echo 0)"
echo "Validation new errors: $(grep -c '^\[ERROR\]' validator_logs/validation_validator_new.txt 2>/dev/null || echo 0)"
echo ""
echo "Excluded old errors: $(grep -c '^\[ERROR\]' validator_logs/excluded_validator.txt 2>/dev/null || echo 0)"
echo "Excluded new errors: $(grep -c '^\[ERROR\]' validator_logs/excluded_validator_new.txt 2>/dev/null || echo 0)"
EOF

bash /tmp/compare_validators.sh
```

**Step 3: Fill in report with actual numbers and observations**

Review the comparison output and populate the summary report with actual metrics

**Step 4: Verify archived old BIDS directories still exist**

Run:
```bash
ls -ld /scratch/users/logben/*.archive_* | head -5
```

Expected: Shows three archived directories with timestamps

**Step 5: Document decision on old archives**

Add to report:
```markdown
## Archive Management
- Old discovery_bids archived to: discovery_bids.archive_[timestamp]
- Old validation_bids archived to: validation_bids.archive_[timestamp]
- Old excluded_bids archived to: excluded_bids.archive_[timestamp]
- Retention: [Keep for 2 weeks / Delete immediately / Other]
```

---

## Task 10: Verify 1-1 Correspondence Between BIDS and Sourcedata Behavioral Files

**Purpose:** Ensure every BIDS functional task has a corresponding behavioral data file in sourcedata, and vice versa. This is critical for event file creation and downstream processing.

**Files:**
- BIDS functional: `/scratch/users/logben/{discovery,validation,excluded}_bids/sub-*/ses-*/func/task-*.nii.gz`
- Sourcedata behavioral: `/oak/stanford/groups/russpold/data/network_grant/sourcedata/behavioral_data/sub-*/ses-*/beh/`
- Excluded sourcedata: `/oak/stanford/groups/russpold/data/network_grant/excluded_sourcedata/behavioral_data/sub-*/ses-*/beh/`
- Report: `/home/users/logben/neuro_workflow/docs/bids-sourcedata-correspondence-2026-03-14.md`

**Step 1: Create correspondence checking script**

Create `/tmp/check_bids_sourcedata_correspondence.py`:

```python
#!/usr/bin/env python3
"""Check 1-1 correspondence between BIDS functional scans and sourcedata behavioral files."""

import json
from collections import defaultdict
from pathlib import Path

def extract_bids_tasks(bids_dir):
    """Extract all functional tasks from BIDS directory.

    Returns dict: {subject: {session: [task_list]}}
    """
    tasks = defaultdict(lambda: defaultdict(set))
    bids_path = Path(bids_dir)

    for func_file in bids_path.glob("sub-*/ses-*/func/*_bold.nii.gz"):
        # Extract subject, session, and task from path
        # Format: sub-XXX/ses-YY/func/sub-XXX_ses-YY_task-TASKNAME_bold.nii.gz
        parts = func_file.stem.split("_")
        subject = None
        session = None
        task = None

        for part in parts:
            if part.startswith("sub-"):
                subject = part
            elif part.startswith("ses-"):
                session = part
            elif part.startswith("task-"):
                task = part

        if subject and session and task:
            tasks[subject][session].add(task)

    return {s: {ses: sorted(list(tasks_set)) for ses, tasks_set in sessions.items()}
            for s, sessions in tasks.items()}

def extract_sourcedata_sessions(sourcedata_dir):
    """Extract all behavioral sessions from sourcedata.

    Returns dict: {subject: {session: [behavioral_files]}}
    """
    sessions = defaultdict(lambda: defaultdict(set))
    sourcedata_path = Path(sourcedata_dir)

    for beh_file in sourcedata_path.glob("sub-*/ses-*/beh/*.csv"):
        # Extract subject and session from path
        # Format: sub-XXX/ses-YY/beh/sub-XXX_ses-YY_task-TASKNAME.csv
        parts = beh_file.stem.split("_")
        subject = None
        session = None

        for part in parts:
            if part.startswith("sub-"):
                subject = part
            elif part.startswith("ses-"):
                session = part

        if subject and session:
            sessions[subject][session].add(beh_file.name)

    return {s: {ses: sorted(list(files_set)) for ses, files_set in sess.items()}
            for s, sess in sessions.items()}

def compare_datasets(bids_tasks, sourcedata_sessions):
    """Compare BIDS tasks with sourcedata behavioral files.

    Returns: (matches, missing_behavioral, orphaned_behavioral)
    """
    matches = []
    missing_behavioral = []
    orphaned_behavioral = []

    # Check each BIDS task has corresponding behavioral file
    for subject in sorted(bids_tasks.keys()):
        for session in sorted(bids_tasks[subject].keys()):
            for task in bids_tasks[subject][session]:
                # Look for corresponding behavioral file
                # Extract task name from "task-TASKNAME" format
                task_name = task.replace("task-", "")

                if subject in sourcedata_sessions and session in sourcedata_sessions[subject]:
                    # Look for matching behavioral file
                    found = False
                    for beh_file in sourcedata_sessions[subject][session]:
                        if f"task-{task_name}" in beh_file:
                            matches.append((subject, session, task, beh_file))
                            found = True
                            break

                    if not found:
                        missing_behavioral.append((subject, session, task))
                else:
                    missing_behavioral.append((subject, session, task))

    # Check for orphaned behavioral files
    for subject in sorted(sourcedata_sessions.keys()):
        for session in sorted(sourcedata_sessions[subject].keys()):
            for beh_file in sourcedata_sessions[subject][session]:
                # Extract task from behavioral filename
                if "task-" in beh_file:
                    task_name = beh_file.split("task-")[1].split(".")[0].split("_")[0]
                    task_full = f"task-{task_name}"

                    if subject not in bids_tasks or \
                       session not in bids_tasks[subject] or \
                       task_full not in bids_tasks[subject][session]:
                        orphaned_behavioral.append((subject, session, beh_file))

    return matches, missing_behavioral, orphaned_behavioral

def main():
    # Extract from all three datasets
    print("=" * 80)
    print("CHECKING BIDS <-> SOURCEDATA CORRESPONDENCE")
    print("=" * 80)
    print()

    datasets = {
        "discovery": {
            "bids": "/scratch/users/logben/discovery_bids",
            "sourcedata": "/oak/stanford/groups/russpold/data/network_grant/sourcedata",
            "excluded_sourcedata": None,
        },
        "validation": {
            "bids": "/scratch/users/logben/validation_bids",
            "sourcedata": "/oak/stanford/groups/russpold/data/network_grant/sourcedata",
            "excluded_sourcedata": "/oak/stanford/groups/russpold/data/network_grant/excluded_sourcedata",
        },
        "excluded": {
            "bids": "/scratch/users/logben/excluded_bids",
            "sourcedata": None,
            "excluded_sourcedata": "/oak/stanford/groups/russpold/data/network_grant/excluded_sourcedata",
        },
    }

    all_results = {}

    for sample_name, paths in datasets.items():
        print(f"\n### {sample_name.upper()} DATASET ###\n")

        if not Path(paths["bids"]).exists():
            print(f"BIDS directory not found: {paths['bids']}")
            continue

        # Extract BIDS tasks
        bids_tasks = extract_bids_tasks(paths["bids"])
        print(f"Found {sum(len(sessions) for sessions in bids_tasks.values())} BIDS sessions")

        # Extract sourcedata (include both regular and excluded)
        all_sourcedata = defaultdict(lambda: defaultdict(set))

        if paths["sourcedata"] and Path(paths["sourcedata"] / "behavioral_data").exists():
            sourcedata_regular = extract_sourcedata_sessions(paths["sourcedata"] / "behavioral_data")
            for subj, sessions in sourcedata_regular.items():
                for sess, files in sessions.items():
                    all_sourcedata[subj][sess].update(files)

        if paths["excluded_sourcedata"] and Path(paths["excluded_sourcedata"] / "behavioral_data").exists():
            sourcedata_excluded = extract_sourcedata_sessions(paths["excluded_sourcedata"] / "behavioral_data")
            for subj, sessions in sourcedata_excluded.items():
                for sess, files in sessions.items():
                    all_sourcedata[subj][sess].update(files)

        sourcedata_sessions = {s: {ses: sorted(list(files_set)) for ses, files_set in sess.items()}
                               for s, sess in all_sourcedata.items()}
        print(f"Found {sum(len(sessions) for sessions in sourcedata_sessions.values())} sourcedata sessions")

        # Compare
        matches, missing_beh, orphaned_beh = compare_datasets(bids_tasks, sourcedata_sessions)

        print(f"\nMatches (1-1 correspondence): {len(matches)}")
        print(f"BIDS tasks with missing behavioral: {len(missing_beh)}")
        print(f"Orphaned behavioral files: {len(orphaned_beh)}")

        if missing_beh:
            print(f"\n  Missing behavioral files:")
            for subject, session, task in missing_beh[:10]:  # Show first 10
                print(f"    {subject}/{session}/{task}")
            if len(missing_beh) > 10:
                print(f"    ... and {len(missing_beh) - 10} more")

        if orphaned_beh:
            print(f"\n  Orphaned behavioral files:")
            for subject, session, beh_file in orphaned_beh[:10]:  # Show first 10
                print(f"    {subject}/{session}/{beh_file}")
            if len(orphaned_beh) > 10:
                print(f"    ... and {len(orphaned_beh) - 10} more")

        all_results[sample_name] = {
            "bids_tasks": bids_tasks,
            "sourcedata_sessions": sourcedata_sessions,
            "matches": len(matches),
            "missing_behavioral": missing_beh,
            "orphaned_behavioral": orphaned_beh,
        }

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    for sample_name, results in all_results.items():
        total_issues = len(results["missing_behavioral"]) + len(results["orphaned_behavioral"])
        status = "✓ PASS" if total_issues == 0 else f"✗ ISSUES ({total_issues})"
        print(f"{sample_name:15} | {results['matches']:4} matches | {status}")

if __name__ == "__main__":
    main()
```

**Step 2: Run correspondence checking script**

Run:
```bash
uv run python /tmp/check_bids_sourcedata_correspondence.py 2>&1 | tee /tmp/correspondence_check.log
```

Expected: Shows breakdown per dataset with matches, missing behavioral files, and orphaned behavioral files

**Step 3: Save correspondence checking script to repository**

Run:
```bash
cp /tmp/check_bids_sourcedata_correspondence.py /home/users/logben/neuro_workflow/scripts/check_bids_sourcedata_correspondence.py
chmod +x /home/users/logben/neuro_workflow/scripts/check_bids_sourcedata_correspondence.py
```

**Step 4: Re-run after full pipeline completion**

After Tasks 3-5 (all bidsify jobs complete), run:
```bash
cd /home/users/logben/neuro_workflow
uv run python scripts/check_bids_sourcedata_correspondence.py 2>&1 | tee docs/correspondence_check_results_2026-03-14.txt
```

Expected: Shows complete correspondence analysis

**Step 5: Review correspondence report**

Run:
```bash
cat /home/users/logben/neuro_workflow/docs/correspondence_check_results_2026-03-14.txt
```

Expected output format:
```
========================================
CHECKING BIDS <-> SOURCEDATA CORRESPONDENCE
========================================

### DISCOVERY DATASET ###

Found X BIDS sessions
Found X sourcedata sessions

Matches (1-1 correspondence): X
BIDS tasks with missing behavioral: X
Orphaned behavioral files: X

[Missing/Orphaned details...]

### VALIDATION DATASET ###
...

### EXCLUDED DATASET ###
...

========================================
SUMMARY
========================================
discovery        | NNN matches | ✓ PASS
validation       | NNNN matches | ✗ ISSUES (X)
excluded         | NN matches | ✓ PASS
```

**Step 6: Create detailed correspondence report**

If any issues found, create `/home/users/logben/neuro_workflow/docs/bids-sourcedata-correspondence-2026-03-14.md`:

```markdown
# BIDS <-> Sourcedata Behavioral Correspondence Report

Generated: 2026-03-14

## Overview

This report documents the 1-1 correspondence between BIDS functional scans and sourcedata behavioral data files.

### Summary Table

| Dataset | BIDS Sessions | Sourcedata Sessions | Perfect Matches | Missing Behavioral | Orphaned Behavioral |
|---------|---------------|-------------------|-----------------|-------------------|-------------------|
| Discovery | X | X | X | X | X |
| Validation | X | X | X | X | X |
| Excluded | X | X | X | X | X |

## Issues Found

### Missing Behavioral Files (BIDS task with no sourcedata file)

These functional scans have no corresponding behavioral data:

**Discovery:**
- None

**Validation:**
- [List subjects/sessions/tasks with no behavioral file]

**Excluded:**
- None

### Orphaned Behavioral Files (No corresponding BIDS task)

These behavioral files have no corresponding functional scan in BIDS:

**Discovery:**
- None

**Validation:**
- [List subjects/sessions/behavioral files with no BIDS task]
- *Note: May be expected if BIDS task was marked for .bidsignore*

**Excluded:**
- None

## Recommendations

Based on correspondence analysis:

1. **If Missing Behavioral:** Check if behavioral data exists but wasn't migrated properly, or if task was skipped by experimental protocol
2. **If Orphaned Behavioral:** Verify if BIDS task was excluded (check .bidsignore) or if behavioral file is from a non-included run
3. **If Perfect Match:** Proceed with event file creation
```

**Step 7: Document findings in main summary report**

Add section to `/home/users/logben/neuro_workflow/docs/bids-rerun-summary-2026-03-14.md`:

```markdown
## Behavioral Data Correspondence

- Discovery: ✓ Full 1-1 correspondence verified
- Validation: [PASS/ISSUES] - X missing, Y orphaned
- Excluded: ✓ Full 1-1 correspondence verified

See `bids-sourcedata-correspondence-2026-03-14.md` for details.
```

**Step 8: If all correspondence verified, document clearance for event creation**

Run:
```bash
cat >> /home/users/logben/neuro_workflow/docs/bids-rerun-summary-2026-03-14.md << 'EOF'

## Clearance for Event File Creation

- [Date]: Behavioral data correspondence verified
- Status: Ready to proceed with event file creation and BIDS movement
- Issues resolved: [List any addressed issues]
EOF
```

---

## Summary

This plan provides a structured approach to:
1. **Clean up** existing BIDS iterations by archiving them with timestamps
2. **Rebuild** the Singularity container to include all latest code changes
3. **Re-run** bidsify on all three datasets from scratch
4. **Validate** improvements in JSON integrity, metadata completeness, and duplicate detection
5. **Verify** 1-1 correspondence between BIDS functional scans and sourcedata behavioral files
6. **Document** findings to understand impact of code improvements and readiness for event creation

All SLURM jobs include proper logging, error handling, and progress tracking. Validators run after all bidsify jobs complete to provide clean comparison. Behavioral correspondence check runs after full bidsify completion to ensure readiness for downstream event file creation.

1. **Clean up** existing BIDS iterations by archiving them with timestamps
2. **Rebuild** the Singularity container to include all latest code changes
3. **Re-run** bidsify on all three datasets from scratch
4. **Validate** improvements in JSON integrity, metadata completeness, and duplicate detection
5. **Document** findings to understand impact of code improvements

All SLURM jobs include proper logging, error handling, and progress tracking. Validators run after all bidsify jobs complete to provide clean comparison.
