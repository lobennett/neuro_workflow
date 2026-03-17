# neuro_workflow Architecture

## Overview

The neuro_workflow package is a comprehensive neuroimaging analysis pipeline that orchestrates the conversion of Flywheel project data to BIDS format, trims physiological and behavioral data, performs quality assurance checks, and manages multi-level statistical analysis. The system is designed with modularity, robustness, and data integrity as core principles.

**Key Characteristics:**
- Parallel processing with controlled concurrency
- Comprehensive error handling and logging
- Multi-sample support (discovery, validation, excluded)
- Trimmed data management with audit trails
- BIDS-compliant outputs with validation
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
├── bidsify/                       # Flywheel → BIDS conversion and trimming
│   ├── behavioral_trimming.py    # CSV behavioral data trimming
│   ├── bids_writer.py            # BIDS file output and JSON patching
│   ├── bold_trimming.py          # NIfTI and events.tsv trimming
│   ├── config.py                 # BIDS mapping and reconciliation config
│   ├── exclusions_manifest.py    # Trimming decision tracking and reporting
│   ├── file_selector.py          # Acquisition file type selection
│   ├── flywheel_query.py         # Subject/session querying with alias merging
│   ├── integration.py            # BIDS validation integration
│   ├── physio.py                 # Physiological data conversion and export
│   ├── physio_query.py           # Gephysio analysis matching
│   ├── physio_trimming.py        # Cardiac/respiratory data trimming
│   ├── reconciliation_config.json# Session/subject overrides and exclusions
│   ├── run.py                    # Main orchestrator (entry point)
│   └── trimming_orchestrator.py  # Coordinates all trimming operations
│
├── bids_validation/               # BIDS-specific validation checks
│   └── bold_analyzer.py          # Task-specific TR-based BOLD analysis
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
│   ├── neg_events.py            # Negative event analysis
│   ├── outlier_report.py        # Outlier detection reporting
│   └── reliability.py           # Test-retest reliability analysis
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
**Purpose:** Primary entry point for Flywheel → BIDS conversion and trimming.

**Key Classes/Functions:**
- `build_reconciliation(canonical_label, sessions, fw_sources)`: Constructs reconciliation record mapping BIDS subject to Flywheel sources
- `_check_bold_4d(nifti_path)`: Validates BOLD NIfTI files are 4D; marks 3D files for .bidsignore
- `download_physio_analysis(analysis, dest_dir)`: Extracts gephysio CSV files from Flywheel
- `_safe_patch_sidecar(json_path, max_retries=3, **fields)`: Safely patches sidecar JSON with retry logic (handles corrupted files, API timeouts)
- `main_bidsify(...)`: Main orchestration function that:
  - Queries Flywheel for subjects and sessions
  - Merges aliased subject variants
  - Applies session overrides (exclusions, reassignments)
  - Downloads and places files in BIDS structure
  - Patches JSON sidecars with metadata
  - Handles physiological data conversion
  - Generates reconciliation.json
  - Integrates BOLD validation system
  - Coordinates trimming operations

**Key Design Decisions:**
- **Parallel workers: 4** (reduced from 16 to avoid Flywheel API rate limiting)
- **Retry logic:** 3 attempts for sidecar patching with backoff
- **Duplicate handling:** First occurrence kept, subsequent duplicates marked for .bidsignore
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

#### config.py - BIDS Mapping & Reconciliation
**Purpose:** Load and manage BIDS acquisition mapping and session/subject overrides.

**Key Functions:**
- `map_acquisition(acquisition, project_name)`: Maps Flywheel acquisition label to BIDS task/suffix
- `load_reconciliation_config()`: Loads reconciliation_config.json with:
  - Alias mappings (variant → canonical subject)
  - Session overrides (exclusions, reassignments)
  - Trimming criteria (which scans need behavioral cutoff)

**Configuration Format:**
```json
{
  "aliases": {"003": "s03", "subj03": "s03"},
  "overrides": {
    "s03": {
      "session_label": {"exclude": true, "reason": "..."}
    }
  },
  "trimming_criteria": {
    "s19-ses-07-goNogo": {"behavioral_cutoff_ms": 15000}
  }
}
```

#### file_selector.py - Acquisition Selection
**Purpose:** Filter and select appropriate acquisitions for BIDS conversion.

**Key Functions:**
- `select_files(acquisitions, file_types)`: Selects acquisition files based on type
- Handles multiple modalities: anatomical, functional, dwi, fmap, physio
- Implements modality-specific logic for file selection

### Trimming Modules

#### bold_trimming.py - NIfTI and Events Trimming
**Purpose:** Remove dummy scans and apply behavioral cutoffs to BOLD data.

**Key Functions:**
- `trim_bold_nifti(bold_file, dummy_scans=7, behavioral_cutoff_trs=None)`:
  - Removes dummy volumes from start of NIfTI
  - Applies behavioral cutoff if scan requires early termination
  - Updates affine matrix for trimmed data
  - Preserves NIfTI header and metadata
  - Returns True if trimming applied, False if file missing

- `trim_events_tsv(events_file, dummy_offset_s, behavioral_cutoff_s=None)`:
  - Adjusts event onsets by dummy offset
  - Removes events outside behavioral cutoff window
  - Maintains event column structure (trial_type, response_time, etc.)

**Algorithm:**
```
1. Load NIfTI image (4D: x, y, z, time)
2. Extract data array
3. Calculate start_idx = dummy_scans
4. Calculate end_idx = num_volumes or (dummy_scans + behavioral_cutoff_trs)
5. Extract trimmed_data = data[:,:,:,start_idx:end_idx]
6. Create new NIfTI with trimmed data
7. Save with original filename (overwrites)
```

#### physio_trimming.py - Physiological Data Trimming
**Purpose:** Synchronize cardiac and respiratory recordings with trimmed BOLD timeline.

**Key Functions:**
- `trim_physio_data(physio_file, dummy_offset_s, behavioral_cutoff_s, sampling_rate)`:
  - Removes cardiac/respiratory samples during dummy period
  - Synchronizes physio timeline with BOLD timeline
  - Handles variable sampling rates (cardiac ~100 Hz, respiratory ~25 Hz)
  - Updates _physio.tsv.gz file with trimmed samples

- `calculate_sample_ranges(num_samples, dummy_offset_ms, behavioral_cutoff_ms, sampling_rate)`:
  - Converts time offsets to sample indices for physiological data

**Data Handling:**
- Reads gzipped TSV files (Flywheel default export format)
- Maintains cardiac and respiratory column structure
- Preserves metadata in JSON sidecar
- Outputs in BIDS-compliant format

#### behavioral_trimming.py - Behavioral CSV Trimming
**Purpose:** Trim behavioral data CSV files to match BOLD acquisition timeline.

**Key Functions:**
- `trim_behavioral_csv(csv_file, dummy_offset_s, behavioral_cutoff_s)`:
  - Removes rows before dummy offset (behavior during dummies is invalid)
  - Removes rows after behavioral cutoff
  - Adjusts timing columns (trial_onset_ms, etc.) by dummy offset
  - Maintains row structure and data integrity

- `identify_timing_columns(df)`: Auto-detects columns containing timing information

**Format Handling:**
```
Input CSV: trial_onset_ms, response_time_ms, accuracy, ...
↓ trim_behavioral_csv(dummy_offset_s=10.43, behavioral_cutoff_s=600.0)
Output CSV: (adjusted times, only rows 10.43s to 600.0s)
```

#### trimming_orchestrator.py - Trimming Coordination
**Purpose:** Coordinate simultaneous trimming of BOLD, physio, and behavioral data.

**Key Classes:**
- `TrimContext`: Data class holding trim parameters
  - subject, session, task
  - dummy_scans (default 7)
  - tr (default 1.49s)
  - behavioral_cutoff_ms (optional)
  - Properties: dummy_offset_s, dummy_offset_ms, behavioral_cutoff_trs

- `TrimOrchestrator`: Main coordination class
  - `trim_scan(context)`: Orchestrates trimming of all associated files
  - `trim_bids_directory(bids_dir, trimming_specs)`: Batch trimming across BIDS directory
  - Returns detailed results dict with trimmed file list and errors

**Workflow:**
```
TrimContext(subject="s19", session="07", task="goNogo", behavioral_cutoff_ms=15000)
    ↓
TrimOrchestrator.trim_scan(context)
    ├─ trim_bold_nifti() → sub-s19/ses-07/func/sub-s19_ses-07_task-goNogo_bold.nii.gz
    ├─ trim_events_tsv() → sub-s19/ses-07/func/sub-s19_ses-07_task-goNogo_events.tsv
    ├─ trim_behavioral_csv() → sourcedata/behavioral_data/sub-s19/ses-07/beh/...
    └─ trim_physio_data() → sub-s19/ses-07/func/sub-s19_ses-07_task-goNogo_physio.tsv.gz
    ↓
results = {
    "subject": "s19",
    "session": "07",
    "task": "goNogo",
    "trimmed": [file_paths...],
    "errors": [...]
}
```

#### exclusions_manifest.py - Trimming Decision Tracking
**Purpose:** Generate authoritative record of all trimming decisions and quality flags.

**Key Functions:**
- `ExclusionsManifest`: Class managing trimming decision tracking
  - `record_trimming(subject, session, task, reason, details)`: Log trimming decision
  - `record_quality_flag(subject, session, task, flag, reason)`: Log quality issues
  - `to_json()`: Serialize manifest to JSON
  - `save(path)`: Write manifest to file

- Schema tracks:
  - Dummy scan removal (standard 7 volumes)
  - Behavioral cutoff trimming (with ms offset)
  - 3D BOLD detection (marked for .bidsignore)
  - Short scans (below task-specific TR thresholds)
  - Missing physiological data
  - Behavioral data reconciliation issues

**Output Format:**
```json
{
  "subject": "s19",
  "session": "07",
  "task": "goNogo",
  "trimming": {
    "type": "behavioral_cutoff",
    "dummy_scans": 7,
    "behavioral_cutoff_ms": 15000,
    "timestamp": "2026-03-16T14:32:00Z"
  },
  "quality_flags": ["diagnostic_run_detected"],
  "notes": "Participant reported stopped responding after 15s"
}
```

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

### BIDS Validation Modules

#### bold_analyzer.py - Task-Specific BOLD Analysis
**Purpose:** Analyze BOLD data quality with task-specific TR thresholds.

**Key Functions:**
- `analyze_bold_files(bids_dir, config_path)`:
  - Loads task-specific TR counts from config
  - Scans all BOLD files in BIDS directory
  - Identifies short scans, missing metadata
  - Generates analysis.json with detailed results

- `is_short_scan(actual_trs, expected_trs, tolerance=0.1)`:
  - Compares actual TR count to task expectation
  - Tolerance allows 10% variance for timing jitter

- Schema detects:
  - 3D BOLD files (marked for .bidsignore)
  - Missing TR metadata
  - Short scans (task-specific detection)
  - Missing JSON sidecars

**Dual-Mode Analysis:**
1. Primary: Task-specific TR thresholds (config/task_tr_counts.json)
2. Fallback: Duration-based detection (3.0 min minimum)

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
    ├─ All Subjects
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
    │       │       │   ├─ patch_sidecar()
    │       │       │   └─ Check for issues (3D, missing metadata)
    │       │       │
    │       │       ├─ convert_physio_to_bids() [if gephysio found]
    │       │       │
    │       │       └─ create_events_from_behavioral() [if behavioral data found]
    │       │
    │       └─ build_reconciliation()
    │
    ↓
BIDS Output Directory
    ├─ sub-XXX/
    │   ├─ ses-YY/
    │   │   ├─ anat/
    │   │   ├─ func/
    │   │   │   ├─ *_bold.nii.gz
    │   │   │   ├─ *_bold.json
    │   │   │   ├─ *_events.tsv
    │   │   │   └─ *_physio.tsv.gz
    │   │   └─ dwi/
    │   └─ ...
    ├─ sourcedata/
    │   ├─ reconciliation.json (subject/session mapping)
    │   ├─ behavioral_data/sub-XXX/ses-YY/beh/
    │   └─ ...
    ├─ dataset_description.json
    ├─ README.md
    └─ .bidsignore (3D BOLD, short scans, etc.)
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

### BIDS → Trimmed BIDS Flow

```
BIDS Directory
    │
    ├─ For each scan requiring trimming:
    │
    └─ TrimOrchestrator.trim_scan(TrimContext)
        │
        ├─ Calculate offsets:
        │   ├─ dummy_offset_s = dummy_scans * TR (e.g., 7 * 1.49 = 10.43s)
        │   └─ behavioral_cutoff_s = behavioral_cutoff_ms / 1000
        │
        ├─ trim_bold_nifti()
        │   └─ sub-XXX/ses-YY/func/*_bold.nii.gz
        │       ├─ Remove first 7 volumes
        │       ├─ Apply behavioral cutoff (if specified)
        │       └─ Update affine matrix
        │
        ├─ trim_events_tsv()
        │   └─ sub-XXX/ses-YY/func/*_events.tsv
        │       ├─ Adjust onset times by -10.43s
        │       └─ Remove events outside [0, behavioral_cutoff_s]
        │
        ├─ trim_behavioral_csv()
        │   └─ sourcedata/behavioral_data/sub-XXX/ses-YY/beh/*
        │       ├─ Remove rows < 10.43s
        │       ├─ Remove rows > behavioral_cutoff_s
        │       └─ Adjust timing columns
        │
        ├─ trim_physio_data()
        │   └─ sub-XXX/ses-YY/func/*_physio.tsv.gz
        │       ├─ Remove samples during dummy period (7 * 1.49s)
        │       └─ Truncate to behavioral cutoff
        │
        └─ exclusions_manifest.record_trimming()
            └─ exclusions.json (append trimming decision)
                ↓
Trimmed BIDS Directory
    ├─ Fewer volumes per BOLD scan
    ├─ Synchronized event/physio/behavioral timing
    ├─ Updated reconciliation files
    └─ exclusions.json with complete audit trail
```

## Architectural Decisions

### 1. Parallel Processing with Controlled Concurrency
**Decision:** Use ThreadPoolExecutor with 4 workers for Flywheel downloads.

**Rationale:**
- Balances speed (parallel I/O) with API stability
- Reduces rate-limiting from Flywheel API
- Earlier attempts with 16 workers caused timeouts
- 4 workers provide ~4x speedup without instability

**Impact:** Bidsify takes ~2-4 hours per sample vs. 30 min for 16 workers, but completes reliably

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

### 4. Modular Trimming Pipeline
**Decision:** Separate modules for BOLD, physio, and behavioral trimming; coordinated via TrimOrchestrator.

**Rationale:**
- Each data type has distinct format and timing considerations
- Allows independent unit testing per module
- Future extensions (e.g., EEG, eye-tracking) fit naturally
- Orchestrator ensures consistency across types

**Impact:** Trimming decisions atomic and auditable; extensible design

### 5. Exclusions Manifest for Audit Trail
**Decision:** Generate exclusions.json documenting all trimming and quality decisions.

**Rationale:**
- Preprocessing teams need to know why scans were trimmed/excluded
- Reproducibility requires documenting all transformations
- Enables reconstruction of decisions (vs. guessing from file size)
- Facilitates future quality audits

**Impact:** Complete provenance for all modified data

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

### 8. Task-Specific TR-Based Short Scan Detection
**Decision:** Use task-specific expected TR counts from config rather than global duration threshold.

**Rationale:**
- Different tasks have different optimal durations
- Global 3-minute threshold too simplistic
- Config allows per-task customization
- Fallback to duration-based if task not in config

**Impact:** Precise short scan detection; fewer false positives/negatives

### 9. Lazy Reconciliation via Session Overrides
**Decision:** Handle subject merging/exclusion via JSON config rather than hardcoding.

**Rationale:**
- Configuration is transparent and version-controlled
- Easy to audit why subjects/sessions excluded
- No code changes needed for new subject mappings
- Supports reassignment (moving sessions between subjects)

**Impact:** Reproducible subject assignments; non-developers can modify config

### 10. NIfTI Affine Matrix Updates
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

3. **Trimming Module Tests** (`test_bold_trimming.py`, etc.)
   - Volume/sample removal
   - Index calculations
   - Edge cases (no trimming needed, all trimming)

4. **Sample Validation Tests** (`test_sample_validation.py`)
   - JSON config format detection
   - Sample membership determination
   - Excluded subject identification

5. **Migration Tests** (`test_migrate.py`)
   - File copying and retry logic
   - Sample filtering
   - JSON-to-CSV conversion

### Integration Tests
**Tests:** End-to-end scenarios

1. **Full Bidsify Workflow**
   - Query Flywheel project
   - Convert to BIDS
   - Verify output structure
   - Check reconciliation.json

2. **Trimming Pipeline**
   - Load BIDS directory
   - Apply trimming specifications
   - Verify file modifications
   - Validate exclusions.json

3. **Behavioral Migration**
   - Copy all data types
   - Apply sample filtering
   - Verify directory structure
   - Check excluded subject routing

### Validation Tests
**Tests:** Output quality checks

1. **BIDS Validator Integration**
   - No critical errors
   - .bidsignore patterns applied correctly
   - Required files present

2. **Data Integrity**
   - File checksums match downloads
   - JSON valid and parseable
   - TSV files have correct columns

3. **Trimming Verification**
   - Volume counts match expectations
   - Event/physio timing synchronized
   - Behavioral cutoff applied correctly

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

### 5. Parallel Trimming
**Current:** Sequential trimming across scans
**Future:** Parallel trimming with progress bars and error recovery

### 6. Web Dashboard
**Current:** JSON logs and reconciliation files
**Future:** Interactive dashboard showing sample composition, trimming decisions, BIDS validation results

### 7. Incremental Updates
**Current:** Full re-download and re-conversion
**Future:** Track processed subjects; only download new/modified acquisitions

### 8. Pre-Processing Quality Control
**Current:** Trim and validate
**Future:** Integration with fMRIPrep outputs; feedback on preprocessing quality

### 9. Multi-Project Support
**Current:** Single Flywheel project per run
**Future:** Aggregate from multiple projects; handle cross-project subject merging

### 10. Version Tracking
**Current:** reconciliation.json, exclusions.json per directory
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
3. **reconciliation_config.json** - Subject merging, session overrides, trimming specs
4. **behavioral_session_mapping.json** - Subject-to-sample assignments
5. **task_tr_counts.json** - Task-specific TR thresholds for short scan detection

### Runtime Outputs
1. **reconciliation.json** - Subject/session mapping for BIDS directory
2. **exclusions.json** - Trimming and quality decisions
3. **bidsify_log.json** - Download log with warnings/errors
4. **analysis.json** - BOLD validation results

## Conclusion

The neuro_workflow architecture emphasizes modularity, auditability, and robustness. Each major component (Flywheel querying, BIDS writing, trimming, behavioral migration) is independently testable while being coordinated by orchestrator classes. Configuration-driven design enables customization without code changes. Comprehensive logging and decision manifests provide full traceability of data transformations, essential for reproducible research.

The design decisions prioritize data integrity and researcher transparency over raw speed, with careful attention to error handling and validation at each step.
