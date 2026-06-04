# neuro_workflow Architecture

## Overview

The neuro_workflow package is a neuroimaging analysis pipeline that orchestrates the conversion of Flywheel project data to BIDS format (with inline dummy volume trimming), manages behavioral data migration, and supports multi-level statistical analysis. The system is designed with simplicity, robustness, and data integrity as core principles.

**Key Characteristics:**
- Sequential processing for simplicity and reliability
- Comprehensive error handling and logging
- Multi-sample support (discovery, validation, excluded)
- Dummy volume trimming (7 TRs) during bidsify
- BIDS-compliant outputs
- Run numbering for duplicate scans (no .bidsignore generation)
- Full lineage tracking of data transformations

## Package Structure

```
src/neuro_workflow/
├── analysis/                      # Level 1 and 2 analysis orchestration
│   ├── config.py                 # Analysis configuration management
│   ├── core/
│   │   ├── task_utils.py         # Task-specific utility functions
│   │   └── utils.py              # Core analysis utilities
│   ├── io/
│   │   └── file_discovery.py     # BIDS file discovery and indexing
│   ├── lev1/
│   │   ├── __init__.py
│   │   ├── processing/           # Task-specific processing modules
│   │   └── run.py                # Level 1 analysis orchestrator
│   ├── lev2/
│   │   ├── __init__.py
│   │   └── run.py                # Level 2 (group) analysis orchestrator
│   ├── mshbm/
│   │   ├── __init__.py
│   │   └── run.py                # Multi-session hierarchical Bayes orchestrator
│   └── task_config/
│       ├── loader.py             # Task configuration file loader
│       └── tasks/                # Task-specific configuration templates
│
├── behavioral_archive/            # Behavioral data migration and normalization
│   ├── copy_utils.py             # Retry-enabled file copy utilities
│   ├── migrate.py                # Migration logic for mTurk, surveys, behavioral
│   ├── normalize_filenames.py    # Filename normalization per data type
│   └── sample_validation.py      # Sample filtering and subject validation
│
├── bidsify/                       # Flywheel → BIDS conversion (sequential, dummy trim, run numbering)
│   ├── bids_writer.py            # BIDS file output and JSON patching
│   ├── config.py                 # Pipeline config loader (load_pipeline_config)
│   ├── file_selector.py          # Acquisition file type selection
│   ├── flywheel_query.py         # Subject/session querying with alias merging
│   ├── physio.py                 # Physiological data conversion and export
│   ├── physio_query.py           # Gephysio analysis matching
│   └── run.py                    # Main orchestrator (entry point)
│
├── cli.py                        # Command-line interface entry point
│
├── core/                         # Shared utilities and base classes
│   ├── config.py                # Project-wide configuration
│   ├── exclusions.py            # Subject/run exclusion tracking
│   ├── image.py                 # NIfTI/imaging utilities
│   └── slurm.py                 # SLURM job submission helpers
│
├── events/                       # Event file creation and validation
│   ├── create.py                # Event file generation from behavioral data
│   ├── qc.py                    # Event quality assurance checks
│   ├── qc_globals.py            # Global signal extraction utilities
│   ├── trim.py                  # Event timing trimming and synchronization
│   └── utils.py                 # Event utilities and normalization
│
├── exclusions/                   # Subject and run exclusion criteria
│   ├── base.py                  # Base exclusion class
│   ├── behavioral.py            # Behavioral data exclusion rules
│   ├── motion.py                # Motion-based exclusion criteria
│   └── neg_events.py            # Negative event exclusion rules
│
├── pipelines/                    # Pipeline orchestration wrappers
│   ├── base.py                  # Base pipeline class
│   ├── bidsify.py               # Bidsify pipeline wrapper
│   ├── fmriprep.py              # fMRIPrep pipeline wrapper
│   ├── freesurfer.py            # FreeSurfer pipeline wrapper
│   ├── fsqc.py                  # FreeSurfer QC wrapper
│   ├── happy.py                 # HAPPY pipeline wrapper
│   ├── lev1.py                  # Level 1 analysis pipeline wrapper
│   ├── lev2.py                  # Level 2 analysis pipeline wrapper
│   ├── mshbm.py                 # MSHBM pipeline wrapper
│   ├── prep_mshbm.py            # MSHBM preparation wrapper
│   └── qsiprep.py               # QSIPrep pipeline wrapper
│
├── qa/                           # Quality assurance modules
│   ├── base.py                  # Base QA class
│   ├── breaks.py                # Scanner break detection
│   ├── fieldmap_check.py        # Fieldmap quality checks
│   ├── global_signal.py         # Global signal extraction and analysis
│   ├── lev1_outliers.py         # Cohort lev1 VIF + outlier detection (feeds exclusions)
│   ├── reliability_movies.py    # Reliability movies via the bold-reliability-movies CLI
│   └── neg_events.py            # Negative event analysis
│
└── templates/                    # SLURM job submission templates
    ├── bidsify.sbatch
    ├── fmriprep.sbatch
    ├── freesurfer.sbatch
    ├── fsqc.sbatch
    ├── happy.sbatch
    ├── lev1.sbatch
    ├── lev2.sbatch
    ├── mshbm.sbatch
    ├── prep_mshbm.sbatch
    └── qsiprep.sbatch
```

## Module Reference

### Core Bidsify Modules

#### run.py - Main Orchestrator
**Purpose:** Primary entry point for Flywheel → BIDS conversion with dummy volume trimming and run numbering for duplicates.

**Key Classes/Functions:**
- `build_reconciliation(canonical_label, sessions, fw_sources)`: Constructs reconciliation record mapping BIDS subject to Flywheel sources
- `download_physio_analysis(analysis, dest_dir)`: Extracts gephysio CSV files from Flywheel
- `_safe_patch_sidecar(json_path, max_retries=3, **fields)`: Safely patches sidecar JSON with retry logic (handles corrupted files, API timeouts)
- `main_bidsify(...)`: Main orchestration function that:
  - Queries Flywheel for subjects and sessions (sequentially)
  - Merges aliased subject variants
  - Applies session overrides (exclusions, reassignments)
  - Downloads and places files in BIDS structure
  - Trims 7 dummy BOLD volumes immediately after NIfTI download
  - Assigns run numbering (run-01, run-02) to duplicate scans
  - Patches JSON sidecars with metadata
  - Downloads physiological data (not trimmed)
  - Generates reconciliation.json
  - Writes session_timestamps.tsv

**Key Design Decisions:**
- **Sequential processing:** No parallelism; simpler and more reliable
- **Retry logic:** 3 attempts for sidecar patching with backoff
- **Duplicate handling:** Duplicate scans receive run numbering (run-01, run-02) instead of being excluded
- **No .bidsignore generation:** Bidsify does not create .bidsignore; curation is a separate manual step
- **Physio downloaded, not trimmed:** Physiological data is converted to BIDS format but not trimmed
- **Error tolerance:** Physio failures generate warnings instead of silent skips

#### flywheel_query.py - Session Merging & Alias Resolution
**Purpose:** Query Flywheel project and merge sessions from aliased subject variants.

**Key Functions:**
- `collect_subject_sessions(canonical_label, all_subjects, aliases, session_overrides)`: Gathers all sessions for a canonical subject including:
  - Alias mapping resolution (handles naming variants like "s03", "003", "subj03")
  - Session exclusions (honored via reconciliation_config.json)
  - Session reassignments (moving sessions between subjects)
  - Timestamp-based sorting for reproducible session numbering
- `build_session_timeline(sessions)`: Constructs chronological timeline for session numbering
- `query_project_subjects(project)`: Retrieves all subjects from Flywheel project with error handling

**Data Flow:**
```
Flywheel Project
    ↓
All Subjects + Aliases Dict
    ↓
collect_subject_sessions()
    ├─ Merge aliased variants
    ├─ Apply session overrides
    └─ Sort by timestamp
    ↓
List of Session Dicts
    ├─ fw_subject, fw_session
    ├─ timestamp, acquisitions
    └─ bids_session (assigned later)
```

#### bids_writer.py - BIDS File Output
**Purpose:** Write files to BIDS structure with proper JSON sidecar patching.

**Key Functions:**
- `bids_filename(subject, session, task, acquisition, suffix, extension)`: Generates BIDS-compliant filenames
- `patch_sidecar(json_path, **fields)`: Updates JSON sidecar with additional fields; creates file if missing
- `download_and_place(acquisition, dest_dir, bids_filename)`: Downloads file from Flywheel and places in BIDS directory
- `write_dataset_description(bids_dir)`: Creates BIDS dataset_description.json
- `write_readme(bids_dir)`: Creates BIDS README.md with sample information

**BIDS Compliance:**
- Generates filenames per BIDS v1.9+ specification
- Creates required JSON sidecars with TR, RepetitionTime, EchoTime, etc.
- Maintains directory structure: sub-XXX/ses-YY/anat|func|dwi|fmap|physio/
- Tracks data provenance in dataset_description.json

#### config.py - Pipeline Configuration
**Purpose:** Load and manage pipeline configuration, BIDS acquisition mapping, and session/subject overrides.

**Key Functions:**
- `map_acquisition(acquisition, project_name)`: Maps Flywheel acquisition label to BIDS task/suffix
- `load_pipeline_config()`: Loads `config/pipeline_config.json` with:
  - Alias mappings (variant → canonical subject)
  - Session overrides (exclusions, reassignments)
  - Sample definitions (discovery, validation, excluded)

**Configuration Format:**
```json
{
  "aliases": {"003": "s03", "subj03": "s03"},
  "overrides": {
    "s03": {
      "session_label": {"exclude": true, "reason": "..."}
    }
  }
}
```

#### file_selector.py - Acquisition Selection
**Purpose:** Filter and select appropriate acquisitions for BIDS conversion.

**Key Functions:**
- `select_files(acquisitions, file_types)`: Selects acquisition files based on type
- Handles multiple modalities: anatomical, functional, dwi, fmap, physio
- Implements modality-specific logic for file selection

### Behavioral Data Migration Modules

#### migrate.py - Core Migration Logic
**Purpose:** Migrate behavioral, survey, and mTurk data from archive to structured locations.

**Key Functions:**
- `migrate_mturk_data(archive_dir, dest_dir, dry_run=False)`:
  - Copies all mTurk data (no sample filtering)
  - Normalizes filenames
  - Handles retry logic for network timeouts
  - Returns migration stats: files_copied, files_skipped, bytes_transferred

- `migrate_out_of_scanner_data(archive_dir, samples, dest_dir, excluded_dest_dir, dry_run=False)`:
  - Migrates out-of-scanner behavioral recordings
  - Filters by sample (discovery/validation)
  - Routes excluded subjects to separate directory
  - Preserves directory structure

- `migrate_survey_data(archive_dir, samples, dest_dir, excluded_dest_dir, dry_run=False)`:
  - Migrates prescan survey data
  - Converts JSON surveys to CSV format
  - Preserves question/response metadata
  - Sample-filtered output

- `migrate_demographics_data(archive_dir, samples, dest_dir, excluded_dest_dir, dry_run=False)`:
  - Migrates participant demographics
  - Maintains metadata associations
  - Sample-filtered output

- `convert_json_survey_to_csv(json_path)`:
  - Converts JSON survey format to CSV
  - Preserves metadata in header row
  - Stores multi-choice options as JSON strings

**Sample Filtering Logic:**
```
For each subject:
1. Check if in excluded subjects dict → route to excluded_dest_dir
2. Else check if in sample (discovery/validation) → route to dest_dir
3. Else skip (log as not in sample)
```

#### sample_validation.py - Sample Filtering
**Purpose:** Determine subject sample membership and exclusion status.

**Key Functions:**
- `load_samples_from_config(config_path)`: Load sample configuration
  - Handles three JSON formats (legacy, session-based, current dict-based)
  - Returns: {"discovery": [...], "validation": [...], "excluded": {...}}
  - Excluded dict maps subject_id → exclusion_reason

- `is_subject_in_sample(subject_id, samples)`: Check if subject in discovery/validation
  - Returns (in_sample, sample_name, is_excluded, exclusion_reason)

- Supports JSON config formats:
  - Legacy: `{"discovery": [...], "validation": [...]}`
  - Session-based: `{"sessions": [{"subject": "s03", "sample": "discovery"}, ...]}`
  - Current: `{"subjects": {"s03": {"sample": "discovery", "excluded": false}, ...}}`

#### normalize_filenames.py - Filename Normalization
**Purpose:** Standardize behavioral data filenames by type.

**Key Functions:**
- `normalize_mturk_filename(filename)`: Normalize mTurk data filenames
- `normalize_out_of_scanner_filename(filename)`: Normalize out-of-scanner behavioral filenames
- `normalize_survey_filename(filename)`: Normalize prescan survey filenames
- `normalize_demographics_filename(filename)`: Normalize demographics filenames

**Normalization Rules:** Replace special characters, standardize date formats, remove redundant prefixes

#### copy_utils.py - File Copy with Retry
**Purpose:** Reliable file copying with automatic retry on network failures.

**Key Functions:**
- `copy_file_with_retries(src, dst, max_retries=3, timeout=300)`:
  - Implements exponential backoff (1s, 2s, 4s)
  - Handles network timeouts, permission errors
  - Verifies file integrity (checksum/size)
  - Logs all attempts and failures

### Physiological Data Modules

#### physio.py - Physio Data Conversion
**Purpose:** Convert Flywheel gephysio analysis to BIDS physiological format.

**Key Functions:**
- `convert_physio_to_bids(gephysio_dir, bids_physio_dir, acquisition_label)`:
  - Reads gephysio CSV exports (cardiac, respiratory)
  - Validates data format and sampling rates
  - Creates BIDS _physio.tsv.gz files
  - Generates JSON sidecar with sampling rate metadata

- `export_physio_json_sidecar(physio_file, sampling_rate, columns)`:
  - Creates JSON metadata file
  - Documents sampling rate, column names
  - Maintains BIDS compatibility

**Format Handling:**
```
gephysio CSV (Flywheel export):
  cardiac,respiratory
  baseline_val_1,baseline_val_2
  ...
  ↓ convert_physio_to_bids()
  BIDS _physio.tsv.gz:
  cardiac respiratory
  baseline_val_1 baseline_val_2
  ...
```

#### physio_query.py - Gephysio Analysis Matching
**Purpose:** Match gephysio analyses to corresponding functional acquisitions.

**Key Functions:**
- `find_gephysio_analyses(session)`: Locate gephysio analyses in Flywheel session
- `match_analyses_to_acquisitions(acquisitions, gephysio_analyses)`:
  - Uses acquisition label matching to associate physio with BOLD
  - Handles multiple physio recordings per session
  - Returns dict mapping acquisition → analysis

**Matching Logic:**
```
Acquisition: "fMRI_task-goNogo_run-1"
    ↓ match to gephysio analysis with similar label
Gephysio analysis: "gephysio_task-goNogo_run-1"
    ↓
Match found: physio data synchronized with this acquisition
```

### Behavioral Archive Modules

#### create.py - Event File Generation
**Purpose:** Create BIDS-compatible events.tsv from behavioral data.

**Key Functions:**
- `create_events_from_behavioral(behavioral_csv, subject, session, task)`:
  - Parses behavioral CSV
  - Maps columns to BIDS event format (onset, duration, trial_type, response_time)
  - Creates events.tsv file in BIDS directory

**Event Format (events.tsv):**
```
onset     duration trial_type      response_time
0.531     1.234    goSignal        0.812
2.107     1.234    goSignal        0.645
...
```

#### trim.py - Event Timing Trimming
**Purpose:** Synchronize event onsets with trimmed BOLD timeline.

**Key Functions:**
- `trim_events(events_df, dummy_offset_s, behavioral_cutoff_s)`:
  - Adjusts onset times by dummy offset
  - Removes events outside behavioral window
  - Maintains event structure

#### qc.py - Event Quality Assurance
**Purpose:** Validate events.tsv structure and content.

**Key Functions:**
- `validate_events(events_df)`: Check required columns (onset, duration, trial_type)
- `check_event_timing(events_df)`: Verify onset/duration consistency
- `detect_response_issues(events_df)`: Identify missing or invalid response times

## Data Flow Diagrams

### Flywheel → BIDS Conversion Flow

```
Flywheel Project
    │
    ├─ query_project_subjects()
    │   ↓
    ├─ All Subjects (processed sequentially)
    │   │
    │   └─ For each canonical subject:
    │       ├─ collect_subject_sessions()
    │       │   ├─ Merge aliases
    │       │   ├─ Apply overrides
    │       │   └─ Sort by timestamp
    │       │   ↓
    │       ├─ Sessions List
    │       │   │
    │       │   ├─ Assign BIDS session numbers
    │       │   │
    │       │   └─ For each session:
    │       │       ├─ select_files() → acquisitions
    │       │       │
    │       │       ├─ find_gephysio_analyses()
    │       │       │   ↓
    │       │       ├─ match_analyses_to_acquisitions()
    │       │       │   ↓
    │       │       ├─ For each acquisition:
    │       │       │   ├─ download_and_place()
    │       │       │   ├─ Trim 7 dummy BOLD volumes (if BOLD)
    │       │       │   ├─ Assign run numbering for duplicates (run-01, run-02)
    │       │       │   └─ patch_sidecar()
    │       │       │
    │       │       └─ convert_physio_to_bids() [downloaded, not trimmed]
    │       │
    │       └─ build_reconciliation()
    │
    ↓
BIDS Output Directory
    ├─ sub-XXX/
    │   ├─ ses-YY/
    │   │   ├─ anat/ (duplicates get run-01, run-02, ...)
    │   │   ├─ func/
    │   │   │   ├─ *_bold.nii.gz (7 dummy vols trimmed)
    │   │   │   ├─ *_bold.json
    │   │   │   └─ *_physio.tsv.gz (not trimmed)
    │   │   └─ dwi/ (duplicates get run-01, run-02, ...)
    │   └─ ...
    ├─ sourcedata/
    │   ├─ reconciliation.json (subject/session mapping)
    │   ├─ session_timestamps.tsv (acquisition timestamps)
    │   └─ ...
    ├─ dataset_description.json
    └─ README.md
```

### Archive → Oak Data Migration Flow

```
Archive Directory
    │
    ├─ /mTurk/
    │   │
    │   └─ migrate_mturk_data()
    │       ├─ Copy all files (no filtering)
    │       ├─ Normalize filenames
    │       └─ Return stats
    │       ↓
    └─ Oak: /network_grant/mTurk/

Archive Directory
    │
    ├─ /out_of_scanner_behavior/
    │   │
    │   └─ migrate_out_of_scanner_data()
    │       ├─ load_samples_from_config()
    │       │   ↓
    │       ├─ For each subject:
    │       │   ├─ Check if excluded → excluded_dest_dir
    │       │   ├─ Else check if in sample → dest_dir
    │       │   └─ Else skip
    │       └─ Return stats
    │       ↓
    ├─ Oak: /network_grant/sourcedata/out_scanner_behavior/
    └─ Oak: /network_grant/excluded_sourcedata/out_scanner_behavior/

Archive Directory
    │
    ├─ /surveys/ + /demographics/
    │   │
    │   └─ migrate_survey_data() + migrate_demographics_data()
    │       ├─ load_samples_from_config()
    │       │   ↓
    │       ├─ For each file:
    │       │   ├─ convert_json_survey_to_csv() [if JSON]
    │       │   ├─ Check if excluded → excluded_dest_dir
    │       │   ├─ Else check if in sample → dest_dir
    │       │   └─ Else skip
    │       └─ Return stats
    │       ↓
    ├─ Oak: /network_grant/sourcedata/survey_data/
    └─ Oak: /network_grant/excluded_sourcedata/survey_data/
```

## Architectural Decisions

### 1. Sequential Processing
**Decision:** Process subjects and sessions sequentially (no parallelism).

**Rationale:**
- Simplest possible design; easy to debug and understand
- Avoids Flywheel API rate limiting entirely
- Earlier parallel approaches (4 and 16 workers) introduced complexity and intermittent failures
- Reliability is more important than speed for a pipeline that runs infrequently

**Impact:** Bidsify is slower but completely reliable; no concurrency-related failures

### 2. Session Merging via Aliases
**Decision:** Support multiple naming variants for same subject (e.g., "s03", "003", "subj03").

**Rationale:**
- Real-world Flywheel projects have inconsistent naming
- Avoids duplicating data for variants of same participant
- Reconciliation.json documents all sources
- One-way mapping (variant → canonical) prevents cycles

**Impact:** Discovery sample has 5 subjects from 9 variant labels; single canonical identity

### 3. Retry Logic with Exponential Backoff
**Decision:** Implement 3-attempt retry for JSON sidecar patching.

**Rationale:**
- JSON files occasionally corrupted during Flywheel extraction
- Network timeouts require backoff to avoid API flooding
- Silent failures in earlier version went undetected
- Retry logic with logging enables diagnosis

**Impact:** Recovers from transient errors; warnings logged for persistent failures

### 4. Inline Dummy Volume Trimming
**Decision:** Trim 7 dummy BOLD volumes directly during bidsify, immediately after NIfTI download. No separate trimming phase or orchestrator.

**Rationale:**
- Only one type of trimming is needed (7 dummy volumes)
- Inlining in run.py keeps the pipeline simple and avoids a separate post-processing step
- Physio data is downloaded but not trimmed (deferred to later stages if needed)

**Impact:** BOLD files are ready for preprocessing immediately after bidsify completes

### 5. Run Numbering for Duplicate Scans
**Decision:** Assign run labels (run-01, run-02, ...) to duplicate scans instead of excluding them via .bidsignore.

**Rationale:**
- Preserves all acquired data in the BIDS directory
- BIDS-compliant: run entity is the standard way to handle multiple acquisitions of the same type
- Avoids premature data exclusion decisions during conversion
- Curation decisions (which run to use) are deferred to analysis

**Impact:** No data loss during conversion; all scans accessible for QA and analysis

### 6. Sample-Based Filtering for Behavioral Data
**Decision:** Routes files to discovery/validation/excluded directories based on behavioral_session_mapping.json.

**Rationale:**
- Prevents accidental inclusion of excluded subjects in analyses
- Mirrors BIDS structure for consistency
- Allows researchers to easily access their sample
- Single source of truth for sample membership

**Impact:** No manual filtering needed; clean separation of subgroups

### 7. Format-Aware Survey Conversion
**Decision:** Convert JSON surveys to CSV while preserving metadata.

**Rationale:**
- JSON format not ideal for statistical analysis
- CSV maintains all information in standard format
- Metadata header (worker_id, experiment_id) preserved
- Multi-choice options stored as JSON strings (reversible)

**Impact:** Survey data immediately usable in R/Python without parsing

### 8. Lazy Reconciliation via Session Overrides
**Decision:** Handle subject merging/exclusion via JSON config rather than hardcoding.

**Rationale:**
- Configuration is transparent and version-controlled
- Easy to audit why subjects/sessions excluded
- No code changes needed for new subject mappings
- Supports reassignment (moving sessions between subjects)

**Impact:** Reproducible subject assignments; non-developers can modify config

### 9. NIfTI Affine Matrix Updates
**Decision:** Update affine matrix when trimming volumes to maintain spatial coordinates.

**Rationale:**
- Trimming changes time dimension, not spatial coordinates
- Affine matrix maps voxel indices to real-world space
- Outdated affine causes downstream processing errors
- nibabel handles affine update automatically on NIfTI construction

**Impact:** Trimmed data has correct spatial coordinates for fMRIPrep

## Testing Strategy

### Unit Tests
**Location:** `tests/`

**Coverage Areas:**
1. **Flywheel Query Tests** (`test_flywheel_query.py`)
   - Alias merging logic
   - Session override application
   - Timestamp-based sorting

2. **BIDS Writer Tests** (`test_bids_writer.py`)
   - Filename generation (BIDS compliance)
   - JSON sidecar creation
   - Required metadata fields

3. **Sample Validation Tests** (`test_sample_validation.py`)
   - JSON config format detection
   - Sample membership determination
   - Excluded subject identification

4. **Migration Tests** (`test_migrate.py`)
   - File copying and retry logic
   - Sample filtering
   - JSON-to-CSV conversion

### Integration Tests
**Tests:** End-to-end scenarios

1. **Full Bidsify Workflow**
   - Query Flywheel project
   - Convert to BIDS
   - Verify dummy volume trimming
   - Verify run numbering for duplicates
   - Check reconciliation.json and session_timestamps.tsv

2. **Behavioral Migration**
   - Copy all data types
   - Apply sample filtering
   - Verify directory structure
   - Check excluded subject routing

### Validation Tests
**Tests:** Output quality checks

1. **BIDS Validator Integration**
   - No critical errors
   - Required files present
   - Run numbering correct for duplicates

2. **Data Integrity**
   - File checksums match downloads
   - JSON valid and parseable
   - TSV files have correct columns
   - Dummy volumes trimmed (7 fewer volumes per BOLD)

### Running Tests
```bash
# All tests
uv run pytest tests/ -v

# Specific test suite
uv run pytest tests/bids_validation/ -v

# With coverage
uv run pytest tests/ --cov=src/neuro_workflow --cov-report=html
```

## Future Improvements

### 1. Support for Additional Modalities
**Current:** Anatomical, functional (BOLD), DWI, fieldmaps, physiological
**Future:** EEG, MEG, eye-tracking data with dedicated trimming modules

### 2. Dynamic TR Detection
**Current:** Hardcoded 1.49s or from reconciliation_config.json
**Future:** Auto-detect TR from NIfTI headers to eliminate configuration needs

### 3. Behavioral Data Validation
**Current:** Simple copying and format conversion
**Future:** Event counting, response time validation, consistency checks

### 4. Physiological Signal Quality Assessment
**Current:** Format conversion only
**Future:** Artifact detection, signal-to-noise analysis, automated flagging

### 5. Web Dashboard
**Current:** JSON logs and reconciliation files
**Future:** Interactive dashboard showing sample composition, trimming decisions, BIDS validation results

### 6. Incremental Updates
**Current:** Full re-download and re-conversion
**Future:** Track processed subjects; only download new/modified acquisitions

### 7. Pre-Processing Quality Control
**Current:** Trim and validate
**Future:** Integration with fMRIPrep outputs; feedback on preprocessing quality

### 8. Multi-Project Support
**Current:** Single Flywheel project per run
**Future:** Aggregate from multiple projects; handle cross-project subject merging

### 9. Version Tracking
**Current:** reconciliation.json, session_timestamps.tsv per directory
**Future:** Full version history with timestamps; ability to compare BIDS versions

## Dependency Architecture

### Core Dependencies
- **nibabel:** NIfTI file reading/writing
- **pandas:** CSV/TSV processing, dataframe operations
- **flywheel-sdk:** Flywheel API access
- **requests:** HTTP client for API calls

### Analysis Pipeline Dependencies
- **fMRIPrep:** Functional preprocessing
- **FSL/AFNI:** Analysis tools
- **Singularity/Apptainer:** Container execution

### Development Dependencies
- **pytest:** Unit and integration testing
- **pytest-cov:** Test coverage reporting
- **black:** Code formatting
- **isort:** Import sorting
- **flake8:** Linting

## Configuration Management

### Primary Configuration Files
1. **CLAUDE.md** - Development guidelines, execution instructions
2. **pyproject.toml** - Project metadata, dependencies, test configuration
3. **config/pipeline_config.json** - Subject merging, session overrides, sample definitions (replaces reconciliation_config.json)
4. **config/behavioral_session_mapping.json** - Subject-to-sample assignments

### Runtime Outputs
1. **reconciliation.json** - Subject/session mapping for BIDS directory
2. **session_timestamps.tsv** - Session and acquisition timestamps per dataset
3. **bidsify_log.json** - Download log with warnings/errors

## Conclusion

The neuro_workflow architecture emphasizes simplicity, auditability, and robustness. The pipeline uses sequential processing with inline dummy volume trimming, run numbering for duplicate scans, and configuration-driven session reconciliation. Each major component (Flywheel querying, BIDS writing, behavioral migration) is independently testable. Configuration-driven design via `config/pipeline_config.json` enables customization without code changes. Comprehensive logging provides full traceability of data transformations, essential for reproducible research.

The design decisions prioritize data integrity, simplicity, and researcher transparency, with careful attention to error handling and validation at each step.
