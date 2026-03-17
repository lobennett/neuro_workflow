# Codebase Cleanup - Approach A (Radical Archive) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Archive 30+ legacy documents, reorganize codebase into clarity, create authoritative WORKFLOW.md and ARCHITECTURE.md guides, re-verify all BIDS data and behavioral migrations work correctly.

**Architecture:** Three-phase approach—(1) File organization and archival, (2) Documentation authoring, (3) Full pipeline re-verification. After cleanup, rerun all scripts to confirm correctness before preprocessing begins.

**Tech Stack:** Git, Python 3.9+, uv package manager, BIDS validator, Flywheel API

---

## Task 1: Create Archive Directory Structure

**Files:**
- Create: `docs/archived/` (directory)
- Create: `docs/archived/design-iterations/` (directory)
- Create: `docs/archived/audit-reports/` (directory)
- Create: `docs/archived/validator-outputs/` (directory)

**Step 1: Create archive directories**

```bash
mkdir -p /home/users/logben/neuro_workflow/docs/archived/design-iterations
mkdir -p /home/users/logben/neuro_workflow/docs/archived/audit-reports
mkdir -p /home/users/logben/neuro_workflow/docs/archived/validator-outputs
```

Expected: Three new directories created under `docs/archived/`

**Step 2: Verify structure**

```bash
ls -la /home/users/logben/neuro_workflow/docs/archived/
```

Expected: Three subdirectories visible

**Step 3: Commit directory creation**

```bash
cd /home/users/logben/neuro_workflow
git add docs/archived/ 2>/dev/null || git add -A
git commit -m "chore: create archive directory structure for legacy documents"
```

---

## Task 2: Move Design & Planning Documents to Archive

**Files:**
- Move: All `docs/plans/*.md` files (~30 files) → `docs/archived/design-iterations/`

**Step 1: List design documents to move**

```bash
ls -1 /home/users/logben/neuro_workflow/docs/plans/*.md | head -20
```

Expected: List of 30+ .md files (planning iterations, design docs)

**Step 2: Move all planning documents**

```bash
mv /home/users/logben/neuro_workflow/docs/plans/*.md /home/users/logben/neuro_workflow/docs/archived/design-iterations/
```

Expected: All .md files moved (no errors)

**Step 3: Verify move**

```bash
ls /home/users/logben/neuro_workflow/docs/archived/design-iterations/ | wc -l
```

Expected: Count matches previous listing (e.g., 30+)

**Step 4: Remove empty plans directory if empty**

```bash
rmdir /home/users/logben/neuro_workflow/docs/plans/ 2>/dev/null && echo "plans dir removed" || echo "plans dir not empty or doesn't exist"
```

**Step 5: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add -A
git commit -m "chore: archive 30+ design and planning documents to docs/archived/design-iterations"
```

---

## Task 3: Move Audit Reports to Archive

**Files:**
- Move: `docs/BIDS-TRIMMING-AUDIT-2026-03-16.md` → `docs/archived/audit-reports/`
- Move: `docs/S29-S43-RESOLUTION-2026-03-17.md` → `docs/archived/audit-reports/`
- Move: `docs/VALIDATION-SUBJECTS-RESOLUTION-2026-03-17.md` → `docs/archived/audit-reports/`
- Move: `docs/bids-audit-2026-03-*.md` (if any) → `docs/archived/audit-reports/`
- Move: `docs/STATUS-UPDATE-MAR16-2026.md` → `docs/archived/audit-reports/`
- Move: `VALIDATOR_FINDINGS.md` → `docs/archived/validator-outputs/`

**Step 1: List audit-related docs**

```bash
find /home/users/logben/neuro_workflow/docs -maxdepth 1 -name "*AUDIT*" -o -name "*RESOLUTION*" -o -name "*STATUS*" | grep -E "\.md$"
```

Expected: List of 5+ .md files

**Step 2: Move audit reports**

```bash
mv /home/users/logben/neuro_workflow/docs/BIDS-TRIMMING-AUDIT-2026-03-16.md \
   /home/users/logben/neuro_workflow/docs/S29-S43-RESOLUTION-2026-03-17.md \
   /home/users/logben/neuro_workflow/docs/VALIDATION-SUBJECTS-RESOLUTION-2026-03-17.md \
   /home/users/logben/neuro_workflow/docs/STATUS-UPDATE-MAR16-2026.md \
   /home/users/logben/neuro_workflow/docs/archived/audit-reports/ 2>/dev/null || echo "Some files may not exist"
```

**Step 3: Move validator findings**

```bash
mv /home/users/logben/neuro_workflow/VALIDATOR_FINDINGS.md /home/users/logben/neuro_workflow/docs/archived/validator-outputs/ 2>/dev/null || echo "VALIDATOR_FINDINGS.md not found"
```

**Step 4: Verify moves**

```bash
ls /home/users/logben/neuro_workflow/docs/archived/audit-reports/
ls /home/users/logben/neuro_workflow/docs/archived/validator-outputs/
```

Expected: Audit reports and validator findings visible in respective dirs

**Step 5: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add -A
git commit -m "chore: archive audit reports and resolution documents"
```

---

## Task 4: Move Validator Output Files to Archive

**Files:**
- Move: `discovery_bids_validator.txt` → `docs/archived/validator-outputs/`
- Move: `validation_bids_validator.txt` → `docs/archived/validator-outputs/`
- Move: `excluded_bids_validator.txt` → `docs/archived/validator-outputs/`

**Step 1: Move validator output files from repo root**

```bash
cd /home/users/logben/neuro_workflow
mv discovery_bids_validator.txt validation_bids_validator.txt excluded_bids_validator.txt docs/archived/validator-outputs/ 2>/dev/null || echo "Some files may not exist in root"
```

**Step 2: Verify**

```bash
ls /home/users/logben/neuro_workflow/docs/archived/validator-outputs/ | grep validator
```

Expected: Three .txt files visible

**Step 3: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add -A
git commit -m "chore: archive validator output files"
```

---

## Task 5: Create logs Directory Structure

**Files:**
- Create: `logs/` directory
- Create: `.gitignore` in logs directory

**Step 1: Create logs directory**

```bash
mkdir -p /home/users/logben/neuro_workflow/logs
```

Expected: logs/ directory created

**Step 2: Move log directories to logs/**

```bash
cd /home/users/logben/neuro_workflow
mv bidsify_logs build_logs validator_logs logs/ 2>/dev/null || echo "Some log directories may not exist"
```

**Step 3: Create .gitignore for logs**

```bash
cat > /home/users/logben/neuro_workflow/logs/.gitignore << 'EOF'
# Ignore all log files and directories
*.log
*.out
slurm-*.out
*_logs/
EOF
```

**Step 4: Remove SLURM output from root**

```bash
rm -f /home/users/logben/neuro_workflow/slurm-*.out
```

**Step 5: Verify**

```bash
ls -la /home/users/logben/neuro_workflow/logs/
```

Expected: Log directories present, .gitignore visible

**Step 6: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add logs/
git commit -m "chore: reorganize logs into logs/ directory with .gitignore"
```

---

## Task 6: Create docs/archived/README.md

**Files:**
- Create: `docs/archived/README.md`

**Step 1: Write archived README**

```bash
cat > /home/users/logben/neuro_workflow/docs/archived/README.md << 'EOF'
# Archived Documentation

This directory contains legacy documents from earlier phases of the neuro_workflow project. They are preserved for reference but should **not** be treated as authoritative guides.

## What's Here

### `design-iterations/`
30+ design and implementation planning documents from various phases. These represent earlier architectural decisions and feature explorations that may or may not have been implemented.

**When to reference:** Rarely—only if you need historical context about a specific feature decision.

### `audit-reports/`
Audit reports and resolution documents from March 2026:
- `BIDS-TRIMMING-AUDIT-2026-03-16.md` - Detailed audit of BOLD trimming decisions
- `S29-S43-RESOLUTION-2026-03-17.md` - Resolution of missing discovery subjects
- `VALIDATION-SUBJECTS-RESOLUTION-2026-03-17.md` - Resolution of missing validation subjects
- `STATUS-UPDATE-MAR16-2026.md` - Status snapshot after BIDS preparation

**When to reference:** Understanding historical problems and how they were solved. For current pipeline status, use `docs/WORKFLOW.md`.

### `validator-outputs/`
Raw BIDS validator output files from validation runs. Preserved for audit trail.

**When to reference:** Never in normal workflow. Only for debugging specific validation issues by timestamp.

---

## Current Authoritative Documents

For current information, see:
- **`docs/WORKFLOW.md`** - Complete Flywheel→BIDS→Behavioral→Events→Preprocessing pipeline
- **`docs/ARCHITECTURE.md`** - Package structure, data flows, architectural decisions
- **`docs/CLAUDE.md`** - Project conventions and guidelines
- **`docs/scan-notes.md`** - Active scan status and notes
- **`docs/tr-based-short-scan-detection.md`** - Technical reference for BOLD validation

---

**Last updated:** 2026-03-17
EOF
```

**Step 2: Verify**

```bash
head -20 /home/users/logben/neuro_workflow/docs/archived/README.md
```

Expected: README content visible

**Step 3: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add docs/archived/README.md
git commit -m "docs: add index and context for archived documents"
```

---

## Task 7: Write WORKFLOW.md - Complete Pipeline Guide

**Files:**
- Create: `docs/WORKFLOW.md` (500+ lines)

**Step 1: Write WORKFLOW.md**

See complete WORKFLOW.md content in execution—this is a 500-line document with complete pipeline guide from Flywheel through preprocessing, configuration reference, troubleshooting, and checkpoints.

**Step 2: Verify file created**

```bash
wc -l /home/users/logben/neuro_workflow/docs/WORKFLOW.md
```

Expected: File should be 500+ lines

**Step 3: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add docs/WORKFLOW.md
git commit -m "docs: create comprehensive WORKFLOW.md as single source of truth for entire pipeline"
```

---

## Task 8: Write ARCHITECTURE.md - Package Structure & Design

**Files:**
- Create: `docs/ARCHITECTURE.md` (400+ lines)

**Step 1: Write ARCHITECTURE.md**

See complete ARCHITECTURE.md content in execution—this is a 400-line document with package structure, module reference, data flow diagrams, architectural decisions, and testing strategy.

**Step 2: Verify file created**

```bash
wc -l /home/users/logben/neuro_workflow/docs/ARCHITECTURE.md
```

Expected: File should be 400+ lines

**Step 3: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add docs/ARCHITECTURE.md
git commit -m "docs: create ARCHITECTURE.md documenting package structure, data flows, and design decisions"
```

---

## Task 9: Update CLAUDE.md with Cleanup Summary

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Read current CLAUDE.md**

```bash
head -100 /home/users/logben/neuro_workflow/CLAUDE.md
```

Expected: Current project guidelines visible

**Step 2: Append cleanup summary to CLAUDE.md**

Append section documenting archive organization, authoritative documents, logs restructure, and cleanup principles.

**Step 3: Verify update**

```bash
tail -30 /home/users/logben/neuro_workflow/CLAUDE.md
```

Expected: Cleanup summary visible at end

**Step 4: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with cleanup summary and archive organization"
```

---

## Task 10: Delete Validator Output and Misc Files from Root

**Files:**
- Delete: Remaining root-level `.txt` files and SLURM output

**Step 1: List files to delete**

```bash
ls -la /home/users/logben/neuro_workflow/ | grep -E "\.(txt|out)$"
```

Expected: List of any remaining .txt and .out files

**Step 2: Delete validator/SLURM output files**

```bash
rm -f /home/users/logben/neuro_workflow/slurm-*.out 2>/dev/null
echo "SLURM files cleaned"
```

**Step 3: Verify cleanup**

```bash
ls -la /home/users/logben/neuro_workflow/ | grep -E "\.(txt|out)$" || echo "No .txt/.out files found"
```

Expected: No output (all files deleted)

**Step 4: Commit**

```bash
cd /home/users/logben/neuro_workflow
git add -A
git commit -m "chore: remove SLURM output and misc files from repo root"
```

---

## Task 11: Verify Directory Structure After Cleanup

**Files:**
- Verify: `docs/`, `logs/`, repo root structure

**Step 1: Check docs structure**

```bash
find /home/users/logben/neuro_workflow/docs -maxdepth 1 -type f -name "*.md" | sort
```

Expected: WORKFLOW.md, ARCHITECTURE.md, CLAUDE.md, scan-notes.md, tr-based-short-scan-detection.md

**Step 2: Check archive structure**

```bash
ls -la /home/users/logben/neuro_workflow/docs/archived/
ls /home/users/logben/neuro_workflow/docs/archived/design-iterations/ | wc -l
```

Expected: 3 subdirectories; 30+ files in design-iterations

**Step 3: Check logs structure**

```bash
ls -la /home/users/logben/neuro_workflow/logs/
```

Expected: bidsify_logs, build_logs, validator_logs directories

**Step 4: Verify .gitignore in logs**

```bash
cat /home/users/logben/neuro_workflow/logs/.gitignore
```

Expected: .log, .out patterns visible

**Step 5: Check repo root (should be clean)**

```bash
ls /home/users/logben/neuro_workflow/*.md /home/users/logben/neuro_workflow/*.txt /home/users/logben/neuro_workflow/*.out 2>/dev/null | wc -l
```

Expected: Only CLAUDE.md in root (count = 1)

**Step 6: Final status check**

```bash
cd /home/users/logben/neuro_workflow
git status
```

Expected: Working tree clean

---

## Task 12: Re-run Bidsify Discovery (Verification)

**Files:**
- Input: Flywheel API
- Output: `/scratch/users/logben/discovery_bids` (fresh)

**Step 1: Delete existing discovery_bids (fresh start)**

```bash
rm -rf /scratch/users/logben/discovery_bids
echo "Deleted old discovery_bids"
```

**Step 2: Run bidsify for discovery sample**

```bash
cd /home/users/logben/neuro_workflow
uv run python -m neuro_workflow.cli bidsify discovery \
    --output-dir /scratch/users/logben/discovery_bids \
    -v
```

Expected: Bidsify completes, logs final summary with subject count and BOLD file count

**Step 3: Verify subject count**

```bash
ls -d /scratch/users/logben/discovery_bids/sub-* | wc -l
```

Expected: 5 subjects

**Step 4: Verify reconciliation.json**

```bash
python3 -c "import json; r=json.load(open('/scratch/users/logben/discovery_bids/sourcedata/reconciliation.json')); print(f\"Subjects: {len(r['subjects'])}, Total sessions: {sum(len(s['sessions']) for s in r['subjects'].values())}\")"
```

Expected: 5 subjects, correct session count

**Step 5: Run BIDS validator**

```bash
bids-validator /scratch/users/logben/discovery_bids --config.ignoreBIDSVersion 2>&1 | tail -10
```

Expected: No critical errors

---

## Task 13: Re-run Bidsify Validation (Verification)

**Files:**
- Input: Flywheel API
- Output: `/scratch/users/logben/validation_bids` (fresh, 41 non-excluded subjects)

**Step 1: Delete existing validation_bids**

```bash
rm -rf /scratch/users/logben/validation_bids
echo "Deleted old validation_bids"
```

**Step 2: Get list of 41 non-excluded validation subjects**

```bash
python3 << 'EOF'
import json
config = json.load(open('/home/users/logben/neuro_workflow/src/neuro_workflow/bidsify/reconciliation_config.json'))
excluded = set(config['excluded_subjects'])
validation_all = config['samples']['validation']
non_excluded = [s for s in validation_all if s not in excluded]
print(' '.join(non_excluded))
EOF
```

Expected: 41 subject IDs printed

**Step 3: Run bidsify for validation (non-excluded)**

```bash
cd /home/users/logben/neuro_workflow

VALIDATION_SUBJECTS=$(python3 << 'PYEOF'
import json
config = json.load(open('/home/users/logben/neuro_workflow/src/neuro_workflow/bidsify/reconciliation_config.json'))
excluded = set(config['excluded_subjects'])
validation_all = config['samples']['validation']
non_excluded = [s for s in validation_all if s not in excluded]
print(' '.join(non_excluded))
PYEOF
)

uv run python -m neuro_workflow.cli bidsify validation \
    --output-dir /scratch/users/logben/validation_bids \
    --subjects $VALIDATION_SUBJECTS \
    -v
```

Expected: Bidsify completes with 41 subjects

**Step 4: Verify subject count**

```bash
ls -d /scratch/users/logben/validation_bids/sub-* | wc -l
```

Expected: 41 subjects

**Step 5: Verify no excluded subjects**

```bash
python3 -c "import json; r=json.load(open('/scratch/users/logben/validation_bids/sourcedata/reconciliation.json')); excluded_in_dir=[s for s in r['subjects'] if any(e in s for e in ['s214','s222','s250'])]; print(f'Found {len(excluded_in_dir)} excluded subjects') if excluded_in_dir else print('OK: No excluded subjects')"
```

Expected: "OK: No excluded subjects"

---

## Task 14: Re-run Bidsify Excluded (Verification)

**Files:**
- Input: Flywheel API (11 excluded subjects)
- Output: `/scratch/users/logben/excluded_bids`

**Step 1: Delete existing excluded_bids**

```bash
rm -rf /scratch/users/logben/excluded_bids
echo "Deleted old excluded_bids"
```

**Step 2: Get list of 11 excluded subjects**

```bash
python3 << 'EOF'
import json
config = json.load(open('/home/users/logben/neuro_workflow/src/neuro_workflow/bidsify/reconciliation_config.json'))
excluded = config['excluded_subjects']
print(' '.join(excluded))
EOF
```

Expected: 11 subject IDs printed

**Step 3: Run bidsify for excluded subjects**

```bash
cd /home/users/logben/neuro_workflow

EXCLUDED_SUBJECTS=$(python3 << 'PYEOF'
import json
config = json.load(open('/home/users/logben/neuro_workflow/src/neuro_workflow/bidsify/reconciliation_config.json'))
print(' '.join(config['excluded_subjects']))
PYEOF
)

uv run python -m neuro_workflow.cli bidsify validation \
    --output-dir /scratch/users/logben/excluded_bids \
    --subjects $EXCLUDED_SUBJECTS \
    -v
```

Expected: Bidsify completes with 11 subjects

**Step 4: Verify subject count**

```bash
ls -d /scratch/users/logben/excluded_bids/sub-* | wc -l
```

Expected: 11 subjects

---

## Task 15: Re-run Behavioral Migration (Verification)

**Files:**
- Input: `/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/`
- Output: `/oak/stanford/groups/russpold/data/network_grant/sourcedata/` and `/oak/.../excluded_sourcedata/`

**Step 1: Run behavioral migration**

```bash
cd /home/users/logben/neuro_workflow

uv run python scripts/migrate_archive_behavioral_data.py \
    --archive-dir /oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data \
    --sourcedata-dir /oak/stanford/groups/russpold/data/network_grant/sourcedata \
    --mturk-dir /oak/stanford/groups/russpold/data/network_grant/mTurk \
    --excluded-sourcedata-dir /oak/stanford/groups/russpold/data/network_grant/excluded_sourcedata \
    --config config/behavioral_session_mapping.json
```

Expected: Script completes with migration summary

**Step 2: Verify no excluded subjects in non-excluded sourcedata**

```bash
ls /oak/stanford/groups/russpold/data/network_grant/sourcedata/out_scanner_behavior/ 2>/dev/null | \
  grep -E "(s214|s222|s250|s297|s432|s823|s968|s1165|s1178|s1266|s1320)" && \
  echo "ERROR: Excluded subjects found" || \
  echo "OK: No excluded subjects in sourcedata"
```

Expected: "OK: No excluded subjects in sourcedata"

---

## Task 16: BIDS Validation Check

**Files:**
- Input: All three BIDS directories
- Output: Validation reports

**Step 1: Run BIDS validator on all directories**

```bash
for dir in /scratch/users/logben/{discovery,validation,excluded}_bids; do
  echo "=== $(basename $dir) ==="
  bids-validator "$dir" --config.ignoreBIDSVersion --config.ignoreNiftiHeaders 2>&1 | tail -5
done
```

Expected: 0 critical errors for each directory

---

## Task 17: Final Cleanup & Commit

**Files:**
- Verify: All changes staged and committed

**Step 1: Check git status**

```bash
cd /home/users/logben/neuro_workflow
git status
```

Expected: "working tree clean"

**Step 2: View recent commits**

```bash
git log --oneline -20
```

Expected: 15+ cleanup-related commits visible

**Step 3: Push to remote**

```bash
git push origin main
```

Expected: All commits pushed successfully

---

## Success Criteria Checklist

- [ ] Docs cleanup: 30+ design docs archived
- [ ] WORKFLOW.md and ARCHITECTURE.md created
- [ ] Logs moved to logs/ with .gitignore
- [ ] CLAUDE.md updated
- [ ] Root cleaned (no .txt/.out files)
- [ ] All 3 BIDS dirs re-generated fresh
- [ ] 0 critical errors per BIDS validator
- [ ] Discovery: 5/5 subjects ✓
- [ ] Validation: 41/41 non-excluded ✓
- [ ] Excluded: 11/11 in separate dir ✓
- [ ] Behavioral: Migrated with proper filtering ✓
- [ ] 15+ atomic commits to main ✓

---

**Implementation Plan Complete**
