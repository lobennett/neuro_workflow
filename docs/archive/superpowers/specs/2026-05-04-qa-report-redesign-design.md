# QA Report Redesign — action-oriented HTML cohort dashboard

**Date:** 2026-05-04
**Author:** Logan Bennett (with brainstorming assist)
**Replaces:** existing `src/neuro_workflow/qa/report.py` (PDF, ~169 pages per subject)

## Goal

Replace the current PDF QA report with an action-oriented HTML cohort dashboard that surfaces what's bad, hides what's not, supports filtering, and embeds bold-reliability-movies output. Make per-subject manual QC of fmriprep derivatives a 30-minute task instead of a 4-hour task.

## Why redesign

The current PDF (`scripts/qa_report.py`) generates ~169 pages per subject by embedding every coregistration, SDC, and fieldmap SVG fmriprep produces. For a 46-subject cohort, that's ~8000 pages to skim. Most pages show passing scans the user didn't need to inspect. There's no way to filter, sort, or correlate metrics across subjects. FreeSurfer surface QC (Euler / hole count) is absent. Bold-reliability-movies (Kendrick Kay style cycling per-session videos) are not produced.

## Design principles

1. **Action-oriented**: every flag has a clear action (exclude / review / accept).
2. **Surface the bad**: by default, only show details for flagged scans.
3. **Self-contained**: each HTML file works offline; no broken links if moved.
4. **Decisions as data**: user decisions live in a version-controlled TSV, not in the browser.
5. **Numeric flags trustworthy, visual flags require human eyes**: don't pretend a script can grade coregistration.
6. **Healthy adults**: cohort-relative outliers, not literature thresholds.

## Architecture

```
fmriprep_<version>/
  └── (derivatives — read-only inputs)

config/manifests/qc_decisions.tsv  (optional, read-only input)

scripts/qa_report.py
   │
   ├── extract metrics (pure functions, per metric class)
   ├── invoke brm (cached mean images; one mp4 per subject)
   └── render Jinja2 templates
   │
   ▼
qa_html/
├── cohort.html          # filterable cohort table; ~200 KB
├── cohort.tsv           # same data, machine-readable
├── decisions.tsv        # copy of input (or empty stub if not provided)
├── movies/
│   └── sub-<X>.mp4      # per-subject reliability movie
└── subjects/
    └── sub-<X>.html     # ~5-10 MB self-contained
```

### CLI

```bash
uv run python scripts/qa_report.py \
  --fmriprep-dir <path> \
  [--output-dir <path>]            # default: <fmriprep-dir>/qa_html
  [--subjects sub-X sub-Y]         # default: all
  [--decisions <path>]             # default: config/manifests/qc_decisions.tsv if present
  [--no-reliability-movies]        # opt-out of brm step
  [--euler-n-sigma 2.0]            # cohort outlier threshold (default 2 MAD)
```

### Module structure

`src/neuro_workflow/qa/` becomes:

```
qa/
├── report.py                 # orchestrator (replaces current report.py contents)
├── metrics/
│   ├── __init__.py
│   ├── motion.py             # FD/DVARS/spikes per scan
│   ├── freesurfer.py         # Euler, holes, recon-all status, runtime, volumes
│   └── outputs.py             # presence check across expected output spaces
├── decisions.py              # load/validate qc_decisions.tsv
├── cohort.py                 # MAD-based outlier detection
├── reliability_movies.py     # thin wrapper around bold_reliability_movies API
└── templates/
    ├── cohort.html.j2
    ├── subject.html.j2
    └── static/
        ├── datatables.min.js
        ├── datatables.min.css
        └── style.css
```

Each metric extractor is a pure function: `(fmriprep_dir, subject, ...) → MetricResult dataclass`. Easy to unit-test.

### Decision flow

User opens `cohort.html`, filters / sorts to find flagged subjects, drills into `subjects/sub-X.html`, looks at figures, decides. Records decision by editing `config/manifests/qc_decisions.tsv` in their text editor. Re-runs `qa_report.py` → HTML re-renders with decisions baked in (cell colored, marked excluded, etc.). Decisions TSV is the source of truth for downstream `.bidsignore` / lev1 input.

## Cohort table (`cohort.html`)

One row per subject. Columns:

| Column | Type | Source |
|---|---|---|
| Subject | string (link) | dir name |
| Sessions | int | count |
| Scans | int | count of non-`.bidsignore`d BOLDs |
| FS Euler (mean L+R) | int | `mris_euler_number` on `?h.orig.nofix`, fallback to `recon-all.log` |
| FS holes (mean L+R) | int | `(2 - euler) / 2` |
| FS status | enum | `recon-all-status.log` (OK / FAILED / INCOMPLETE) |
| Scans flagged: motion | int | count of scans hitting motion thresholds |
| Scans flagged: outputs | int | count of scans missing expected outputs |
| Scan flags total | int | sum of motion + outputs flags |
| Decision | enum | from `decisions.tsv` (pass / exclude / review / unset) |
| Decision note | string | from `decisions.tsv` |

**Filter UX** (DataTables):
- Per-column search inputs (column header).
- Global search box.
- Dropdown filters for enum columns.
- Numeric range filters for Euler, holes, flag counts.
- Default sort: `Scan flags total` desc.

**Visual cues**:
- Subject name strikethrough if `Decision == exclude`; yellow background if `review`.
- Euler cell color gradient (red = cohort-worst 5%, green = cohort-best 5%).
- Top-of-page banner: total subjects, total flagged, links to flagged subjects.

## Per-subject HTML (`subjects/sub-<X>.html`)

Sections, top to bottom:

### Header
Subject ID, fmriprep version, sessions, total scans, status pills (FS / motion / outputs), decision-from-tsv if any.

### FreeSurfer card (always visible)
- recon-all status + elapsed time
- Euler L / R / mean, hole count
- Inline cohort-distribution bar showing where this subject falls
- Cortical/subcortical volumes from `aseg.stats` (collapsed `<details>`)
- fmriprep's `*_desc-reconall_T1w.svg` embedded inline

### Anatomical alignment card (always visible)
Three SVGs: T1w↔MNI152NLin2009c, T1w↔MNI152NLin6Asym, T1w dseg overlay. "Mark for review" button populates clipboard text.

### Reliability movie card (always visible)
`<video controls>` referencing `../movies/sub-<X>.mp4`. One-line description.

### Scan-level table (filterable)
Columns: `session, task, run, n_vols, FD mean, %FD>0.5, DVARS mean, %DVARS>1.5, motion outliers, output spaces complete, flagged, decision`. Default sort: flagged on top.

### Per-scan figure blocks (collapsed; auto-expand on flag)
For each scan, a `<details>` containing: carpet plot, coreg, SDC, CompCor variance, confound correlation, t2scomp, t2starhist (if multi-echo). "Mark for review" button.

## Metrics

### Motion (`metrics/motion.py`)

```python
@dataclass
class MotionMetrics:
    n_vols: int
    fd_mean: float
    fd_max: float
    fd_prop_over_05: float
    dvars_mean: float
    dvars_max: float
    dvars_prop_over_15: float
    n_motion_outliers: int      # count of motion_outlier_NN columns
    fd_series: pd.Series         # for sparkline
    dvars_series: pd.Series      # for sparkline

def compute_motion(confounds_tsv: Path) -> MotionMetrics: ...
```

Flag thresholds (existing):
- rest scan: `fd_mean > 0.2`
- task scan: `fd_prop_over_05 > 0.20`
- any scan: `dvars_prop_over_15 > 0.20`

### FreeSurfer (`metrics/freesurfer.py`)

```python
@dataclass
class FreeSurferMetrics:
    status: Literal["OK", "FAILED", "INCOMPLETE", "MISSING"]
    elapsed_hours: float | None
    euler_lh: int | None
    euler_rh: int | None
    euler_mean: float | None
    holes_lh: int | None
    holes_rh: int | None
    holes_mean: float | None
    brain_vol: float | None
    gm_vol: float | None
    wm_vol: float | None
    csf_vol: float | None
    etiv: float | None

def compute_freesurfer(fs_subject_dir: Path) -> FreeSurferMetrics: ...
```

Euler extraction:
1. Try `mris_euler_number lh.orig.nofix` (and rh).
2. Fall back to `grep "lheno" recon-all.log` (FreeSurfer prints it).
3. If both fail: status reflects partial data; numeric cells show "—".

### Outputs (`metrics/outputs.py`)

```python
@dataclass
class OutputCheckResult:
    complete: bool
    missing: list[str]   # filenames

def check_expected_outputs(fmriprep_dir: Path, subject: str, scan: ScanID) -> OutputCheckResult: ...
```

Expected per scan (depends on `--output-spaces` configured for the run):
- `desc-preproc_bold.nii.gz`
- `space-MNI152NLin2009cAsym_res-1_desc-preproc_bold.nii.gz`
- `space-MNI152NLin6Asym_res-2_desc-preproc_bold.nii.gz`
- `space-T1w_desc-preproc_bold.nii.gz`
- `hemi-L_space-fsaverage6_bold.func.gii`
- `hemi-R_space-fsaverage6_bold.func.gii`
- `hemi-L_space-fsnative_bold.func.gii`
- `hemi-R_space-fsnative_bold.func.gii`
- `space-fsLR_den-91k_bold.dtseries.nii`
- `desc-confounds_timeseries.tsv`

Flag if any are missing.

### Cohort outlier detection (`cohort.py`)

```python
def cohort_euler_outliers(
    metrics: dict[str, FreeSurferMetrics],
    n_sigma: float = 2.0
) -> set[str]:
    """
    MAD-based outlier detection on euler_mean.
    Flags subjects with euler_mean < median - n_sigma * MAD.
    Default n_sigma=2 (~5% one-sided in normal distribution).
    """
```

MAD chosen over percentiles because 46 subjects is too small for stable percentile estimates.

### Decisions TSV (`decisions.py`)

```tsv
subject  session  task              run  action   reason
sub-s03  ses-11   stopSignalWDF     1    exclude  non-monotonic onsets
sub-s1258 ses-01  rest              1    review   FSL bet was flaky on retry
sub-s1351 -       -                 -    pass     visually inspected: T1w pair averaged correctly
```

`action ∈ {pass, exclude, review}`. Empty session/task/run = subject-level decision (applies to all scans).

```python
def load_decisions(path: Path) -> dict[ScanID | str, Decision]:
    """Returns dict keyed by ScanID for scan-level decisions, by subject for subject-level."""
```

Validates: each row references a real scan or subject (warns if not). Returns empty dict if path missing.

## BRM integration (`reliability_movies.py`)

```python
from bold_reliability_movies import FmriprepFrameSource, make_videos
from bold_reliability_movies.renderers import get_renderer

def render_reliability_movies(
    fmriprep_dir: Path,
    output_movies_dir: Path,
    subjects: list[str],
) -> dict[str, MovieResult]:
    """
    One mp4 per subject (group_by="subject"). Returns dict of subject → result
    (path or error). Catches exceptions per subject so one failure doesn't kill
    the cohort run.
    """
```

Caching: brm's `mean_cache.py` already caches the mean image of each BOLD file; lives in `<output_movies_dir>/.cache/`. First cohort run takes ~5-10 min/subject; subsequent runs are seconds.

Optional via `--no-reliability-movies`. Per-subject HTML still references `<video>` but src links to a stub message if the movie failed.

## Error handling

| Scenario | Behavior |
|---|---|
| Missing FreeSurfer dir | `FS status: MISSING`. Subject HTML still generated. |
| `mris_euler_number` not on PATH | Fall back to `recon-all.log` parsing. If both fail: cells show "—", subject still renders. |
| Confounds TSV missing | Scan row marked `motion: unparsable`. |
| `decisions.tsv` references unknown scan | Warning to stderr, skip row, continue. |
| brm fails for one subject | Per-subject `<video>` shows "reliability movie unavailable: <reason>". Cohort continues. |
| ffmpeg / cairo modules not loaded | brm fails (see above). HTML still produced. |
| Multi-anat subject (s1351, s1399) | Pick FS dir matching the highest-quality T1w session. List all FS dirs in subject HTML if multiple exist. |

## Testing

### Unit tests (`tests/qa/`)

- `test_motion.py` — synthetic confounds TSVs; thresholds, edge cases (empty, NaN, missing columns).
- `test_freesurfer.py` — fixture FS dir with hand-crafted `recon-all.log` and `aseg.stats`.
- `test_outputs.py` — synthetic file tree; verify completeness check.
- `test_cohort.py` — synthetic Euler distribution; verify MAD outlier detection.
- `test_decisions.py` — TSV parsing + validation, malformed rows.

### Integration tests (`tests/scripts/`)

- `test_qa_report_html.py` — runs `qa_report.py` against a tiny pre-baked fmriprep fixture. Asserts: file structure correct, cohort.html contains DataTables, subject HTML contains FS card + motion table, decisions render correctly.

### Out of scope

- Browser visual rendering (would need Playwright; deferred).
- brm itself (has its own test suite).

## Performance targets

- Cohort regen with cached movies: < 2 min for 46 subjects.
- First cohort run with brm computation: ~1 hour (limited by brm mean computation).
- Per-subject HTML generation: < 5 s after metrics computed.
- Cohort HTML page weight: < 1 MB.

## Out of scope for this design

- Coregistration auto-grading (visual; manual review only).
- SDC quality auto-grading (visual; manual review only).
- Parcellation segmentation visualizations (not currently in fmriprep output).
- Per-task or longitudinal cross-cohort comparison views.
- Live server / Streamlit dashboard.

## Open risks

1. **`mris_euler_number` requires FreeSurfer module loaded** — if cluster modules aren't loaded, fallback to `recon-all.log` parsing kicks in. Worth verifying the fallback path on a real FS dir.
2. **brm wall time** for 46 subjects ~5-10 min/subject = ~4-8 hours first run. User must accept this is mostly-async.
3. **HTML page weight** for subjects with 60+ scans could hit 15-20 MB if all SVGs inline. Acceptable given they're usually loaded one at a time.
4. **DataTables vendoring**: ~50 KB inline JS per HTML file. Acceptable.

## Out-of-scope follow-ups (potentially future specs)

- Cross-cohort QC comparison (e.g., compare discovery vs validation sample distributions).
- TSNR computation per scan.
- Slice-timing correction quality metrics.
- Automated coregistration quality scoring (e.g., mutual information).
