# Pipeline Simplification Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove BOLD analyzer logic, behavioral trimming, and consolidate documentation to simplify the pipeline to its core functionality: 7-volume dummy removal and handling of duplicate/irreconcilable scans.

**Architecture:** The pipeline simplification removes two overlays (BOLD validation and behavioral trimming) that were introduced but are now causing data integrity issues. The core remains: bidsify downloads BIDS data with 7-volume dummy removal, duplicate anatomical detection marks scans for .bidsignore, and behavioral migration stays sample-aware but preserves raw behavioral timing.

**Tech Stack:** Python (uv), pytest, git, JSON configuration, BASH scripting

---

## Task 1: Document Irreconcilable Scans in reconciliation_config.json

**Files:**
- Modify: `config/reconciliation_config.json` (add new section)
- Reference: `docs/SCAN-NOTES.md` (already contains scan notes)

**Step 1: Read the current reconciliation_config.json**

```bash
cd /home/users/logben/neuro_workflow
head -30 config/reconciliation_config.json
```

Expected output: JSON object with subject aliases, session overrides, excluded subjects.

**Step 2: Read scan-notes.md to extract irreconcilable scans**

```bash
grep -A 2 "irreconcilable\|s29/ses-01\|s300/ses-08\|s1292/ses-04" docs/SCAN-NOTES.md
```

Expected output: Details about three irreconcilable scans.

**Step 3: Add irreconcilable_scans section to reconciliation_config.json**

Using Edit tool, add this section before the closing `}`:

```json
  "irreconcilable_scans": {
    "s29_ses-01_cuedTS": {
      "subject": "s29",
      "session": "ses-01",
      "task": "cuedTS",
      "reason": "BOLD functional scan exists but no corresponding behavioral events file (events were collected for spatialTS task instead)"
    },
    "s300_ses-08_flanker": {
      "subject": "s300",
      "session": "ses-08",
      "task": "flanker",
      "reason": "Behavioral data lost during server shutdown before save completed; only BOLD data recovered"
    },
    "s1292_ses-04_nBack": {
      "subject": "s1292",
      "session": "ses-04",
      "task": "nBack",
      "reason": "Scanner failure during acquisition; only partial BOLD data and no behavioral data collected"
    }
  }
```

**Step 4: Verify JSON syntax is valid**

```bash
uv run python -c "import json; json.load(open('config/reconciliation_config.json'))" && echo "✓ JSON valid"
```

Expected output: `✓ JSON valid`

**Step 5: Commit**

```bash
git add config/reconciliation_config.json
git commit -m "docs: Add irreconcilable_scans section to reconciliation_config.json"
```

---

## Task 2: Remove BOLD Analyzer Call from bidsify/run.py

**Files:**
- Modify: `src/neuro_workflow/bidsify/run.py` (remove BOLD analysis call)

**Step 1: Read run.py to find BOLD analysis invocation**

```bash
grep -n "run_bold_analysis\|BOLD\|analysis" src/neuro_workflow/bidsify/run.py | head -20
```

Expected output: Lines showing `run_bold_analysis_and_update_bidsignore` call.

**Step 2: Read the relevant section of run.py**

```bash
tail -100 src/neuro_workflow/bidsify/run.py
```

Expected output: Final section of run.py showing BOLD analysis call at end of main flow.

**Step 3: Remove BOLD analysis call using Edit tool**

Find the lines calling `run_bold_analysis_and_update_bidsignore()` and remove them. Also remove any related imports. Typical pattern will be near the end of the `run()` function, something like:

```python
# REMOVE THIS BLOCK:
run_bold_analysis_and_update_bidsignore(
    output_dir=output_dir,
    skip_validation=skip_validation,
    logger=logger
)
```

**Step 4: Verify removal by checking for no remaining BOLD analysis calls**

```bash
grep "run_bold_analysis\|BOLD.*analysis" src/neuro_workflow/bidsify/run.py
```

Expected output: (empty - no matches)

**Step 5: Run basic syntax check**

```bash
uv run python -m py_compile src/neuro_workflow/bidsify/run.py
```

Expected output: (no errors)

**Step 6: Commit**

```bash
git add src/neuro_workflow/bidsify/run.py
git commit -m "refactor: Remove BOLD analyzer call from bidsify run.py"
```

---

## Task 3: Remove BOLD Analysis Integration Function

**Files:**
- Modify: `src/neuro_workflow/bidsify/integration.py` (remove `run_bold_analysis_and_update_bidsignore` function)

**Step 1: Read integration.py to find BOLD analysis function**

```bash
grep -n "def run_bold_analysis\|def.*bold\|def.*analysis" src/neuro_workflow/bidsify/integration.py
```

Expected output: Line numbers of BOLD analysis functions.

**Step 2: Read the function and surrounding code**

```bash
sed -n '1,50p' src/neuro_workflow/bidsify/integration.py
```

Expected output: Imports and function definitions.

**Step 3: Identify and remove the entire `run_bold_analysis_and_update_bidsignore()` function**

Using Edit tool, remove the complete function definition (typically 30-50 lines).

**Step 4: Remove `_load_task_tr_counts()` helper function if present**

```bash
grep -n "_load_task_tr_counts" src/neuro_workflow/bidsify/integration.py
```

If found, remove this function as well using Edit tool.

**Step 5: Remove unused imports**

Check for imports like:
- `from neuro_workflow.bids_validation.bold_analyzer import BoldAnalyzer`
- `from neuro_workflow.config import ...` (if only used for TR counts)

Remove any imports that are now unused.

**Step 6: Verify no dangling references to removed functions**

```bash
grep "run_bold_analysis\|_load_task_tr_counts\|BoldAnalyzer" src/neuro_workflow/bidsify/integration.py
```

Expected output: (empty - no matches)

**Step 7: Run syntax check**

```bash
uv run python -m py_compile src/neuro_workflow/bidsify/integration.py
```

Expected output: (no errors)

**Step 8: Commit**

```bash
git add src/neuro_workflow/bidsify/integration.py
git commit -m "refactor: Remove BOLD analyzer integration function"
```

---

## Task 4: Remove Behavioral File Trimming from rename_behavioral_to_sourcedata.py

**Files:**
- Modify: `scripts/rename_behavioral_to_sourcedata.py`

**Step 1: Read the script to find trimming logic**

```bash
grep -n "trim\|cutoff\|time_elapsed\|slice" scripts/rename_behavioral_to_sourcedata.py | head -20
```

Expected output: Lines related to behavioral trimming.

**Step 2: Understand the current trimming implementation**

```bash
sed -n '1,100p' scripts/rename_behavioral_to_sourcedata.py | grep -A 10 -B 5 "trim\|cutoff"
```

Expected output: Context around trimming logic.

**Step 3: Identify all trimming-related code blocks**

Look for:
- CSV file reading and column-based trimming
- time_elapsed cutoff calculations
- Behavioral file writing with reduced rows

**Step 4: Remove trimming logic using Edit tool**

Remove any blocks that:
- Calculate cutoff times based on BIDS scan times
- Filter CSV rows based on time_elapsed
- Write trimmed behavioral files

Keep the core logic that:
- Reads behavioral CSVs
- Copies them to sourcedata/behavioral_data structure
- Updates session_mapping.json

**Step 5: Verify no trimming references remain**

```bash
grep -i "trim\|cutoff\|slice.*behavioral" scripts/rename_behavioral_to_sourcedata.py
```

Expected output: (empty or only comments explaining why trimming was removed)

**Step 6: Run syntax check**

```bash
uv run python -m py_compile scripts/rename_behavioral_to_sourcedata.py
```

Expected output: (no errors)

**Step 7: Commit**

```bash
git add scripts/rename_behavioral_to_sourcedata.py
git commit -m "refactor: Remove behavioral file trimming from rename script"
```

---

## Task 5: Remove Behavioral File Trimming from migrate_archive_behavioral_data.py

**Files:**
- Modify: `scripts/migrate_archive_behavioral_data.py`

**Step 1: Search for trimming logic in migration script**

```bash
grep -n "trim\|cutoff\|time_elapsed\|slice" scripts/migrate_archive_behavioral_data.py
```

Expected output: Lines related to behavioral trimming (if any).

**Step 2: Check if trimming is applied to out-of-scanner and survey data**

```bash
sed -n '1,200p' scripts/migrate_archive_behavioral_data.py | grep -A 5 -B 5 "out_of_scanner\|survey"
```

Expected output: Context showing where behavioral data is processed.

**Step 3: Identify and remove any trimming logic**

Look for and remove any code that:
- Applies time-based filtering to out-of-scanner behavior files
- Filters survey data based on behavioral session times
- Performs any row-slicing on behavioral data

Keep the core migration logic intact.

**Step 4: Verify no trimming references remain**

```bash
grep -i "trim\|cutoff\|slice.*data\|time_based.*filter" scripts/migrate_archive_behavioral_data.py
```

Expected output: (empty or only comments)

**Step 5: Run syntax check**

```bash
uv run python -m py_compile scripts/migrate_archive_behavioral_data.py
```

Expected output: (no errors)

**Step 6: Commit**

```bash
git add scripts/migrate_archive_behavioral_data.py
git commit -m "refactor: Remove behavioral file trimming from migration script"
```

---

## Task 6: Delete config/task_tr_counts.json

**Files:**
- Delete: `config/task_tr_counts.json`

**Step 1: Verify file exists and contains TR configuration**

```bash
head -10 config/task_tr_counts.json
```

Expected output: JSON with task_tr_counts section.

**Step 2: Search for any references to this config file**

```bash
grep -r "task_tr_counts" src/ scripts/ tests/ --include="*.py" | grep -v ".pyc"
```

Expected output: (should be empty after Tasks 2-3; if not, those tasks incomplete)

**Step 3: Delete the file**

```bash
rm config/task_tr_counts.json
```

**Step 4: Verify deletion**

```bash
ls -la config/task_tr_counts.json 2>&1 | grep "No such file"
```

Expected output: `No such file or directory`

**Step 5: Commit deletion**

```bash
git add -u config/task_tr_counts.json
git commit -m "chore: Remove obsolete task_tr_counts.json config file"
```

---

## Task 7: Consolidate Outdated Documentation and Identify Deletions

**Files:**
- Read/Audit: All files in `docs/` directory
- Target for deletion: 8 files (audit-2026-03-11, audit-2026-03-13, bold-analysis-report, BOLD-VALIDATION-COMPLETE, BOLD-VALIDATION-AUTOMATIC, bids-rerun-summary, IMPLEMENTATION-SUMMARY, task-4-summary)

**Step 1: List all markdown files in docs/**

```bash
find docs/ -maxdepth 1 -name "*.md" -type f | sort
```

Expected output: Complete list of all doc files.

**Step 2: Read each outdated file and extract critical information**

For each of the 8 files marked for deletion, check:
- Does it contain information NOT in WORKFLOW.md or ARCHITECTURE.md?
- Are there specific scan issues, audit findings, or test results that need preserving?

Key files to audit:
- `docs/bids-audit-2026-03-13.md` → Check for behavioral-BIDS correspondence findings
- `docs/bold-analysis-report-2026-03-14.md` → Check for missing TR scans findings
- `docs/IMPLEMENTATION-SUMMARY-MAR14-2026.md` → Check for TR-based detection approach (being removed)

**Step 3: Create an audit checklist**

```bash
cat > /tmp/doc_audit.txt << 'EOF'
File: bids-audit-2026-03-11.md
- [ ] Extract critical info
- [ ] Verify already in WORKFLOW.md
- [ ] Ready to delete

File: bids-audit-2026-03-13.md
- [ ] Extract critical info (behavioral correspondence)
- [ ] Verify already documented
- [ ] Ready to delete

File: bold-analysis-report-2026-03-14.md
- [ ] Extract any missing TR scan findings
- [ ] Update scan-notes.md if new scans found
- [ ] Ready to delete

File: BOLD-VALIDATION-COMPLETE.md
- [ ] Check for 52 test reference
- [ ] Verify tests still pass
- [ ] Ready to delete

File: BOLD-VALIDATION-AUTOMATIC.md
- [ ] This entire feature being removed
- [ ] No info needed
- [ ] Safe to delete

File: bids-rerun-summary-2026-03-14.md
- [ ] Template file, superseded by actual runs
- [ ] No critical info
- [ ] Safe to delete

File: IMPLEMENTATION-SUMMARY-MAR14-2026.md
- [ ] TR-based detection approach (being removed)
- [ ] No info needed in new pipeline
- [ ] Safe to delete

File: task-4-summary-e2e-testing.md
- [ ] Historical test summary
- [ ] Tests still exist in tests/
- [ ] Safe to delete
EOF
cat /tmp/doc_audit.txt
```

**Step 4: Review critical findings from bold-analysis-report-2026-03-14.md**

```bash
grep -i "missing.*TR\|scan.*issue\|3D.*scan" docs/bold-analysis-report-2026-03-14.md 2>/dev/null || echo "File may not exist or no critical findings"
```

**Step 5: Verify scan-notes.md is complete**

```bash
wc -l docs/SCAN-NOTES.md 2>/dev/null || echo "Not yet renamed; check docs/scan-notes.md"
ls -la docs/*scan* 2>/dev/null | head -5
```

Expected: scan-notes.md exists with comprehensive scan issue documentation.

**Step 6: Commit this audit step**

```bash
git add docs/SCAN-NOTES.md
git commit -m "docs: Consolidate scan notes (audit complete, ready for consolidation)"
```

---

## Task 8: Rename Documentation Files to UPPERCASE-KEBAB-CASE Format

**Files:**
- Rename (using `git mv`):
  - `docs/scan-notes.md` → `docs/SCAN-NOTES.md`
  - `docs/tr-based-short-scan-detection.md` → `docs/TR-BASED-SHORT-SCAN-DETECTION.md`

**Step 1: Check current file names**

```bash
ls -la docs/*.md | grep -i "scan\|tr-based"
```

Expected output: Current lowercase names.

**Step 2: Rename using git mv (preserves history)**

```bash
cd /home/users/logben/neuro_workflow
git mv docs/scan-notes.md docs/SCAN-NOTES.md
git mv docs/tr-based-short-scan-detection.md docs/TR-BASED-SHORT-SCAN-DETECTION.md
```

Expected output: (no output on success)

**Step 3: Verify renames**

```bash
ls -la docs/SCAN-NOTES.md docs/TR-BASED-SHORT-SCAN-DETECTION.md
```

Expected output: Files present with new names.

**Step 4: Update references to renamed files in other docs**

Check CLAUDE.md and WORKFLOW.md for references:

```bash
grep -n "scan-notes\|tr-based-short" docs/CLAUDE.md docs/WORKFLOW.md docs/ARCHITECTURE.md 2>/dev/null
```

If found, update using Edit tool (change relative links).

**Step 5: Commit renames**

```bash
git add docs/CLAUDE.md docs/WORKFLOW.md docs/ARCHITECTURE.md 2>/dev/null || true
git commit -m "docs: Rename to UPPERCASE-KEBAB-CASE format"
```

---

## Task 9: Delete Outdated Documentation Files

**Files:**
- Delete: 8 files from docs/ directory

**Step 1: Double-check no critical info will be lost**

```bash
for file in \
  docs/bids-audit-2026-03-11.md \
  docs/bids-audit-2026-03-13.md \
  docs/bold-analysis-report-2026-03-14.md \
  docs/BOLD-VALIDATION-COMPLETE.md \
  docs/BOLD-VALIDATION-AUTOMATIC.md \
  docs/bids-rerun-summary-2026-03-14.md \
  docs/IMPLEMENTATION-SUMMARY-MAR14-2026.md \
  docs/task-4-summary-e2e-testing.md; do
  [ -f "$file" ] && echo "Found: $file" || echo "Already gone: $file"
done
```

Expected output: Confirmation of which files exist.

**Step 2: Move files to archived directory (safe deletion)**

```bash
# Create archive subdirectory if needed
mkdir -p docs/archived/cleanup-2026-03-18

# Move files
for file in \
  docs/bids-audit-2026-03-11.md \
  docs/bids-audit-2026-03-13.md \
  docs/bold-analysis-report-2026-03-14.md \
  docs/BOLD-VALIDATION-COMPLETE.md \
  docs/BOLD-VALIDATION-AUTOMATIC.md \
  docs/bids-rerun-summary-2026-03-14.md \
  docs/IMPLEMENTATION-SUMMARY-MAR14-2026.md \
  docs/task-4-summary-e2e-testing.md; do
  [ -f "$file" ] && mv "$file" docs/archived/cleanup-2026-03-18/
done
```

Expected output: (no output on success)

**Step 3: Create archive index/README for cleanup batch**

```bash
cat > docs/archived/cleanup-2026-03-18/README.md << 'EOF'
# Cleanup Batch - March 18, 2026

Files archived during pipeline simplification (BOLD analyzer removal, behavioral trimming removal).

## Archived Files

- `bids-audit-2026-03-11.md` - Old vs New BIDS comparison (superseded by final BIDS state)
- `bids-audit-2026-03-13.md` - Behavioral-BIDS correspondence (info merged into WORKFLOW.md)
- `bold-analysis-report-2026-03-14.md` - BOLD validation results (feature removed)
- `BOLD-VALIDATION-COMPLETE.md` - Implementation summary (feature removed)
- `BOLD-VALIDATION-AUTOMATIC.md` - Automatic validation during bidsify (feature removed)
- `bids-rerun-summary-2026-03-14.md` - Expected rerun template (outdated)
- `IMPLEMENTATION-SUMMARY-MAR14-2026.md` - TR-based detection (feature removed)
- `task-4-summary-e2e-testing.md` - Historical test summary (tests still in tests/)

All critical information has been consolidated into:
- `docs/WORKFLOW.md` - Complete pipeline documentation
- `docs/ARCHITECTURE.md` - System design and module reference
- `docs/SCAN-NOTES.md` - Scan issues and special handling

See `docs/archived/README.md` for archive guidance.
EOF
```

**Step 4: Verify archives were moved**

```bash
ls -la docs/archived/cleanup-2026-03-18/
```

Expected output: 8 files listed.

**Step 5: Stage and commit archive move**

```bash
git add docs/archived/cleanup-2026-03-18/
git commit -m "chore: Archive outdated documentation from pipeline simplification

Moved 8 outdated files to docs/archived/cleanup-2026-03-18/:
- BOLD validation reports (feature removed)
- Old audit reports (superseded)
- Implementation summaries (feature removed)

All critical information consolidated in WORKFLOW.md, ARCHITECTURE.md, SCAN-NOTES.md"
```

---

## Task 10: Run Test Suite to Verify No Breakage

**Files:**
- Test: All test files in `tests/`

**Step 1: Run the full test suite**

```bash
cd /home/users/logben/neuro_workflow
uv run pytest tests/ -v --tb=short 2>&1 | head -100
```

Expected output: Tests should pass (or show same failures as before removal).

**Step 2: Run specific bidsify tests**

```bash
uv run pytest tests/bidsify/ -v 2>&1 | tail -30
```

Expected output: All tests pass.

**Step 3: Run behavioral archive tests**

```bash
uv run pytest tests/behavioral_archive/ -v 2>&1 | tail -30
```

Expected output: All tests pass.

**Step 4: Check for any import errors in modified files**

```bash
uv run python -c "from neuro_workflow.bidsify import run; from neuro_workflow.behavioral_archive import migrate; print('✓ All imports successful')"
```

Expected output: `✓ All imports successful`

**Step 5: Commit test verification**

```bash
git add -A
git commit -m "test: Verify all tests pass after pipeline simplification"
```

---

## Task 11: Verify BIDS Directories and .bidsignore Content

**Files:**
- Check: `/scratch/users/logben/discovery_bids/.bidsignore`
- Check: `/scratch/users/logben/validation_bids/.bidsignore`
- Check: `/scratch/users/logben/excluded_bids/.bidsignore`

**Step 1: Check discovery_bids .bidsignore content**

```bash
head -20 /scratch/users/logben/discovery_bids/.bidsignore
wc -l /scratch/users/logben/discovery_bids/.bidsignore
```

Expected output: File should contain only duplicate anatomical entries (no TR-based exclusions).

**Step 2: Check validation_bids .bidsignore content**

```bash
head -30 /scratch/users/logben/validation_bids/.bidsignore
grep -c "3D\|TR\|short" /scratch/users/logben/validation_bids/.bidsignore || echo "No TR-based exclusions found (good)"
```

Expected output: Should contain anatomical duplicates and irreconcilable scan entries (no TR-count entries).

**Step 3: Check excluded_bids .bidsignore content**

```bash
head -20 /scratch/users/logben/excluded_bids/.bidsignore
```

Expected output: Should contain duplicate anatomical entries.

**Step 4: Verify .bids-validation/analysis.json no longer exists (BOLD analyzer removed)**

```bash
ls -la /scratch/users/logben/discovery_bids/.bids-validation/ 2>&1 | head -5
```

Expected output: Directory may be gone or contain only old analysis.json (will be removed on next bidsify run).

**Step 5: Create verification summary document**

```bash
cat > /tmp/bidsignore_verification.txt << 'EOF'
BIDSIGNORE Verification Report
==============================

Discovery BIDS:
- Entries: $(wc -l < /scratch/users/logben/discovery_bids/.bidsignore)
- Contains duplicates: $(grep -c "duplicate\|anat" /scratch/users/logben/discovery_bids/.bidsignore || echo "0")
- Contains TR-based exclusions: $(grep -c "TR\|scan_duration" /scratch/users/logben/discovery_bids/.bidsignore || echo "0")

Validation BIDS:
- Entries: $(wc -l < /scratch/users/logben/validation_bids/.bidsignore)
- Contains duplicates: $(grep -c "duplicate\|anat" /scratch/users/logben/validation_bids/.bidsignore || echo "unknown")
- Contains irreconcilable scans: $(grep -c "s29.*ses-01\|s300.*ses-08\|s1292.*ses-04" /scratch/users/logben/validation_bids/.bidsignore || echo "0")

Excluded BIDS:
- Entries: $(wc -l < /scratch/users/logben/excluded_bids/.bidsignore)
- Contains duplicates: $(grep -c "duplicate\|anat" /scratch/users/logben/excluded_bids/.bidsignore || echo "0")
EOF
cat /tmp/bidsignore_verification.txt
```

**Step 6: Document final state**

```bash
git log --oneline -10
```

Expected output: Last 10 commits showing all refactoring work.

---

## Task 12: Final Summary and Cleanup

**Files:**
- Create: `docs/PIPELINE-SIMPLIFICATION-COMPLETED-2026-03-18.md`

**Step 1: Create summary document**

```bash
cat > docs/PIPELINE-SIMPLIFICATION-COMPLETED-2026-03-18.md << 'EOF'
# Pipeline Simplification - Completed March 18, 2026

## Summary

Successfully removed BOLD analyzer logic, behavioral trimming, and consolidated outdated documentation to streamline the pipeline.

## Changes Made

### Code Removals ✓
- [x] Removed BOLD analyzer call from `bidsify/run.py`
- [x] Removed `run_bold_analysis_and_update_bidsignore()` from `bidsify/integration.py`
- [x] Removed behavioral file trimming from `rename_behavioral_to_sourcedata.py`
- [x] Removed behavioral file trimming from `migrate_archive_behavioral_data.py`
- [x] Deleted `config/task_tr_counts.json`

### Configuration Updates ✓
- [x] Added `irreconcilable_scans` section to `config/reconciliation_config.json`
  - s29/ses-01 cuedTS (no behavioral events file)
  - s300/ses-08 flanker (behavioral data lost)
  - s1292/ses-04 nBack (scanner failure)

### Documentation ✓
- [x] Renamed `scan-notes.md` → `SCAN-NOTES.md`
- [x] Renamed `tr-based-short-scan-detection.md` → `TR-BASED-SHORT-SCAN-DETECTION.md`
- [x] Archived 8 outdated files to `docs/archived/cleanup-2026-03-18/`
- [x] Created archive index

### Verification ✓
- [x] All tests passing
- [x] No syntax errors in modified files
- [x] BIDS directories verified
- [x] .bidsignore files contain only appropriate entries

## Pipeline Now Handles

1. **BIDS Download**: Bidsify pulls data from Flywheel
2. **Dummy Removal**: 7-volume dummy trimming applied to all BOLD files
3. **Duplicate Detection**: Duplicate anatomical scans marked in .bidsignore
4. **Irreconcilable Scans**: Known problem scans documented and excluded
5. **Behavioral Migration**: Sample-aware routing to discovery/validation/excluded directories
6. **No Automatic TR-Based Exclusions**: TR counting removed

## Next Steps

- Proceed with preprocessing (fMRIPrep)
- Event file creation handles behavioral-BIDS temporal alignment
- Use reconciliation_config.json for reference on known issues

## Commits

All changes committed in 8 commits:
1. Add irreconcilable_scans to reconciliation_config.json
2. Remove BOLD analyzer call from run.py
3. Remove BOLD analyzer integration function
4. Remove behavioral trimming from rename_behavioral_to_sourcedata.py
5. Remove behavioral trimming from migrate_archive_behavioral_data.py
6. Delete task_tr_counts.json
7. Rename docs to UPPERCASE-KEBAB-CASE
8. Archive outdated documentation

## Files Still In Use

- `config/behavioral_session_mapping.json` - KEEP (behavioral migration)
- `config/behavioral_samples.json` - KEEP (sample filtering)
- `docs/WORKFLOW.md` - Authoritative pipeline reference
- `docs/ARCHITECTURE.md` - System design reference
- `docs/SCAN-NOTES.md` - Scan issues reference
- `docs/CLAUDE.md` - Project conventions
EOF
cat docs/PIPELINE-SIMPLIFICATION-COMPLETED-2026-03-18.md
```

**Step 2: Commit final summary**

```bash
git add docs/PIPELINE-SIMPLIFICATION-COMPLETED-2026-03-18.md
git commit -m "docs: Add pipeline simplification completion summary"
```

**Step 3: Final status check**

```bash
git log --oneline -12
git status
```

Expected output: Clean working directory, 8+ commits showing the work.

---

## Testing Strategy

**Unit tests**: Existing pytest suite should pass (no test changes needed, only removals of tested features)

**Integration tests**: Run full test suite to verify no new import errors or broken dependencies

**Manual verification**: Check .bidsignore files contain only expected entries (duplicates + irreconcilable scans, no TR-based)

**Behavioral scripts**: Quick syntax check ensures no broken imports after removals

---

## Rollback Plan

If issues discovered:

```bash
git log --oneline --all | head -15  # Find commit before Task 1
git reset --soft <commit-hash>      # Keep changes in staging
git reset HEAD                      # Unstage
git checkout -- .                   # Discard
```
