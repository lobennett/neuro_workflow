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

## Why Archived

These files documented features or approaches that have been removed as part of the pipeline simplification:

1. **BOLD Analyzer Removal**: Files related to TR-based short scan detection, automatic BOLD validation during bidsify
2. **Behavioral Trimming Removal**: No trimming of behavioral data to match BOLD scan times
3. **Consolidation**: Critical information consolidated into authoritative references

## Authoritative References (Current)

All critical information has been consolidated into:
- `docs/WORKFLOW.md` - Complete pipeline documentation
- `docs/ARCHITECTURE.md` - System design and module reference
- `docs/SCAN-NOTES.md` - Scan issues and special handling
- `docs/CLAUDE.md` - Project conventions and guidelines

See `docs/archived/README.md` for archive guidance.
