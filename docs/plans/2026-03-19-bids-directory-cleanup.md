# BIDS Directory Cleanup and Run Renaming Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove problematic BOLD runs from two subjects (s480 and s43), rename remaining runs to maintain proper BIDS run numbering, and document changes in existing documentation.

**Architecture:** Two cleanup operations in separate BIDS directories: delete run-1 files and rename run-2 to run-1 for consistency. Add contextual notes to existing SCAN-NOTES.md and sourcedata README files.

**Tech Stack:** Bash scripting, file operations (rm, mv), BIDS validator, git

---

## Task 1: Delete and Rename s480 ses-03 task-goNogo in validation_bids

**Files:**
- Delete and Rename: `/scratch/users/logben/validation_bids/sub-s480/ses-03/func/*task-goNogo*`

**Step 1: List files to verify before deletion**

```bash
cd /scratch/users/logben/validation_bids
find sub-s480/ses-03/func/ -name "*task-goNogo*" -type f | sort
```

Expected output: 12 files total (run-1 and run-2, each with echo-1/2/3 + json)

**Step 2: Delete run-1 files**

```bash
cd /scratch/users/logben/validation_bids/sub-s480/ses-03/func/
rm -v sub-s480_ses-03_task-goNogo_run-1_echo-*.nii.gz
rm -v sub-s480_ses-03_task-goNogo_run-1_echo-*.json
```

Expected output: 6 files deleted

**Step 3: Rename run-2 to run-1**

```bash
cd /scratch/users/logben/validation_bids/sub-s480/ses-03/func/
for echo in 1 2 3; do
  mv sub-s480_ses-03_task-goNogo_run-2_echo-${echo}_bold.nii.gz sub-s480_ses-03_task-goNogo_run-1_echo-${echo}_bold.nii.gz
  mv sub-s480_ses-03_task-goNogo_run-2_echo-${echo}_bold.json sub-s480_ses-03_task-goNogo_run-1_echo-${echo}_bold.json
done
```

Expected output: No output on success

**Step 4: Verify final state**

```bash
find /scratch/users/logben/validation_bids/sub-s480/ses-03/func/ -name "*task-goNogo*" -type f | sort
```

Expected output: 6 files, all with run-1

---

## Task 2: Delete and Rename s43 ses-08 task-directedForgetting in discovery_bids

**Files:**
- Delete and Rename: `/scratch/users/logben/discovery_bids/sub-s43/ses-08/func/*task-directedForgetting*`

**Step 1: List files to verify before deletion**

```bash
cd /scratch/users/logben/discovery_bids
find sub-s43/ses-08/func/ -name "*task-directedForgetting*" -type f | sort
```

Expected output: 12 files total (run-1 and run-2, each with echo-1/2/3 + json)

**Step 2: Delete run-1 files**

```bash
cd /scratch/users/logben/discovery_bids/sub-s43/ses-08/func/
rm -v sub-s43_ses-08_task-directedForgetting_run-1_echo-*.nii.gz
rm -v sub-s43_ses-08_task-directedForgetting_run-1_echo-*.json
```

Expected output: 6 files deleted

**Step 3: Rename run-2 to run-1**

```bash
cd /scratch/users/logben/discovery_bids/sub-s43/ses-08/func/
for echo in 1 2 3; do
  mv sub-s43_ses-08_task-directedForgetting_run-2_echo-${echo}_bold.nii.gz sub-s43_ses-08_task-directedForgetting_run-1_echo-${echo}_bold.nii.gz
  mv sub-s43_ses-08_task-directedForgetting_run-2_echo-${echo}_bold.json sub-s43_ses-08_task-directedForgetting_run-1_echo-${echo}_bold.json
done
```

Expected output: No output on success

**Step 4: Verify final state**

```bash
find /scratch/users/logben/discovery_bids/sub-s43/ses-08/func/ -name "*task-directedForgetting*" -type f | sort
```

Expected output: 6 files, all with run-1

---

## Task 3: Update docs/SCAN-NOTES.md with Cleanup Notes

**Files:**
- Modify: `/home/users/logben/neuro_workflow/docs/SCAN-NOTES.md`

**Step 1: Add notes to SCAN-NOTES.md**

Using Edit tool, append this section to the end of SCAN-NOTES.md:

```markdown
## BIDS Structural Cleanup - March 19, 2026

### s480 ses-03 task-goNogo (validation_bids)

**Issue**: Duplicate BOLD runs (run-1 and run-2 present for same task in same session)

**Resolution**:
- Deleted: run-1_echo-{1,2,3}_bold.{nii.gz,json} (6 files)
- Promoted: run-2 → run-1 (6 files renamed)
- Rationale: BIDS validator flagged duplicate runs; run-1 was original acquisition, run-2 was repeat. Kept run-2 based on acquisition quality assessment.

### s43 ses-08 task-directedForgetting (discovery_bids)

**Issue**: 3D BOLD file (incomplete scan - ended prematurely) with duplicate run numbering

**Resolution**:
- Deleted: run-1_echo-{1,2,3}_bold.{nii.gz,json} (6 files, 3D scan)
- Promoted: run-2 → run-1 (6 files renamed, valid 4D scan)
- Rationale: run-1 was incomplete 3D acquisition; run-2 is valid 4D functional data. BIDS validator identified the 3D issue; cleanup removes invalid data while maintaining proper run numbering.
```

**Step 2: Verify content was added**

```bash
tail -30 /home/users/logben/neuro_workflow/docs/SCAN-NOTES.md
```

Expected output: New section visible at end of file

---

## Task 4: Add Cleanup Notes to validation_bids/sourcedata

**Files:**
- Modify or Create: `/scratch/users/logben/validation_bids/sourcedata/README.md` or equivalent

**Step 1: Check if README exists**

```bash
ls -la /scratch/users/logben/validation_bids/sourcedata/
```

Expected output: List of existing sourcedata files

**Step 2: Add brief cleanup note**

If a README exists, append to it. If not, create a minimal note file:

```bash
cat >> /scratch/users/logben/validation_bids/sourcedata/CLEANUP_NOTES.txt << 'EOF'
BIDS Structural Cleanup - March 19, 2026
=========================================

s480 ses-03 task-goNogo:
- Deleted duplicate run-1 (6 files)
- Promoted run-2 to run-1 for proper BIDS naming
- See docs/SCAN-NOTES.md for details
EOF
```

Expected output: File created/appended

---

## Task 5: Add Cleanup Notes to discovery_bids/sourcedata

**Files:**
- Modify or Create: `/scratch/users/logben/discovery_bids/sourcedata/README.md` or equivalent

**Step 1: Add brief cleanup note**

```bash
cat >> /scratch/users/logben/discovery_bids/sourcedata/CLEANUP_NOTES.txt << 'EOF'
BIDS Structural Cleanup - March 19, 2026
=========================================

s43 ses-08 task-directedForgetting:
- Deleted run-1 (3D incomplete scan, 6 files)
- Promoted run-2 to run-1 (valid 4D scan)
- See docs/SCAN-NOTES.md for details
EOF
```

Expected output: File created/appended

---

## Task 6: Run BIDS Validator on Both Directories

**Files:**
- Validate: `/scratch/users/logben/discovery_bids/` and `/scratch/users/logben/validation_bids/`

**Step 1: Validate discovery_bids**

```bash
cd /scratch/users/logben
bids-validator discovery_bids/ 2>&1 | tail -20
```

Expected output: Validator results, should show no structural errors

**Step 2: Validate validation_bids**

```bash
cd /scratch/users/logben
bids-validator validation_bids/ 2>&1 | tail -20
```

Expected output: Validator results, should show no structural errors

**Step 3: Verify both s43 and s480 files exist with correct naming**

```bash
echo "=== s43 discovery_bids ===" && \
find /scratch/users/logben/discovery_bids/sub-s43/ses-08/func/ -name "*task-directedForgetting*" | wc -l && \
echo "=== s480 validation_bids ===" && \
find /scratch/users/logben/validation_bids/sub-s480/ses-03/func/ -name "*task-goNogo*" | wc -l
```

Expected output: 6 files for each, all with run-1

---

## Task 7: Commit Documentation and SCAN-NOTES Changes

**Files:**
- Commit: `docs/SCAN-NOTES.md` and sourcedata cleanup notes

**Step 1: Stage documentation changes**

```bash
cd /home/users/logben/neuro_workflow
git add docs/SCAN-NOTES.md
git status
```

Expected output: docs/SCAN-NOTES.md staged

**Step 2: Commit**

```bash
git commit -m "docs: Add BIDS cleanup notes for s480 and s43

- s480 ses-03 task-goNogo (validation): Duplicate runs removed, run-2 promoted to run-1
- s43 ses-08 task-directedForgetting (discovery): 3D incomplete scan removed, run-2 promoted to run-1
- Validated both directories post-cleanup
- Added cleanup notes to sourcedata directories"
```

**Step 3: Verify commit**

```bash
git log --oneline -1
```

Expected output: Commit message visible

---

## Testing Strategy

**File existence**: Verify correct number of files remain after deletion/renaming (should be 6 per subject)

**BIDS validation**: Run validator on both directories to confirm structural integrity

**File naming**: Confirm all remaining files have run-1 in their names (no run-2)

---

## Rollback Plan

If validation fails:

```bash
# Revert git changes to SCAN-NOTES.md
cd /home/users/logben/neuro_workflow
git revert <commit-hash>

# Files in /scratch are not version controlled; if needed, restore from backup or re-run bidsify
```
