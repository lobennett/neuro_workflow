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
- `STATUS-UPDATE-MAR14-2026.md` - Status snapshot (earlier)
- `STATUS-UPDATE-MAR16-2026.md` - Status snapshot (later)

**When to reference:** Understanding historical problems and how they were solved. For current pipeline status, check the authoritative sources listed below.

### `validator-outputs/`
Raw BIDS validator output files from validation runs. Preserved for audit trail.

**When to reference:** Never in normal workflow. Only for debugging specific validation issues by timestamp.

---

## Current Authoritative Documents

For current information, see:
- **`../CLAUDE.md`** - Project conventions and guidelines (root level)
- **`scan-notes.md`** - Active scan status and notes
- **`tr-based-short-scan-detection.md`** - Technical reference for BOLD validation
- **`WORKFLOW.md`** - Complete pipeline guide (under development)
- **`ARCHITECTURE.md`** - Package structure and design (under development)

---

**Last updated:** 2026-03-17
