# fMRIPrep 25.2.4 Rerun — Pipeline Visualization

**Companion to:** `2026-04-28-fmriprep-rerun-design.md` and `../plans/2026-04-28-fmriprep-rerun.md`

This document visualizes the data flow, phase sequencing, and triage logic of the fmriprep 25.2.4 rerun pipeline. Diagrams use Mermaid syntax and render natively in GitHub-flavored Markdown.

---

## 1. End-to-end pipeline overview

```mermaid
flowchart TD
    classDef preflight fill:#e8f4fd,stroke:#1565c0,stroke-width:1px,color:#000
    classDef phase1 fill:#fff4e1,stroke:#e65100,stroke-width:1px,color:#000
    classDef phase2 fill:#e8f5e9,stroke:#2e7d32,stroke-width:1px,color:#000
    classDef gate fill:#fce4ec,stroke:#c2185b,stroke-width:1px,color:#000
    classDef done fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px,color:#000

    P0["Phase 0: Pre-flight<br/>scripts/fmriprep_preflight.py<br/><i>Local, no SLURM, idempotent</i>"]:::preflight
    P0a["Build symlink BIDS view at<br/>bids_dir/derivatives/fmriprep_25.2.4_input/"]:::preflight
    P0b["Verify view: every subject ≥1 T1w<br/>+ multi-anat counts<br/>(s1351 has 2 T1w, s1399 has 2 T2w)"]:::preflight
    P0c["Wipe stale work dirs +<br/>partial fmriprep_25.2.4 derivatives"]:::preflight

    P1["Phase 1: s03 profile<br/>1 SLURM job, 7-day wall<br/>8 CPUs × 24 GB = 192 GB"]:::phase1
    G1{"Phase 1<br/>success<br/>gate"}:::gate
    PR["Write profile report<br/>2026-04-28-fmriprep-rerun-profile-report.md<br/>(captures peak RSS, runtime, calibration)"]:::phase1

    P2A["Phase 2A: Discovery production<br/>4 subjects (s03 already done)<br/>throttle 4, 7-day wall"]:::phase2
    P2B["Phase 2B: Validation production<br/>41 subjects, throttle 12<br/>--dependency=afterany on Phase 2A"]:::phase2

    DONE["46 / 46 subjects preprocessed<br/>1mm MNI + 2mm MNI152NLin6Asym +<br/>fsaverage6 + fsnative + T1w + func + CIFTI 91k"]:::done

    P0 --> P0a --> P0b --> P0c --> P1
    P1 --> G1
    G1 -->|"pass: validate +<br/>capture metrics"| PR
    G1 -->|"fail: triage,<br/>resubmit, retry"| P1
    PR --> P2A
    PR --> P2B
    P2A -.->|"afterany"| P2B
    P2A --> DONE
    P2B --> DONE
```

---

## 2. Pre-flight: `.bidsignore` → symlink view

The pre-flight script translates `.bidsignore` patterns (which pybids ignores) into a parallel symlink directory that fmriprep reads as if it were the BIDS dataset.

```mermaid
flowchart LR
    classDef src fill:#e3f2fd,stroke:#1565c0,color:#000
    classDef script fill:#fff8e1,stroke:#f57c00,color:#000
    classDef view fill:#e8f5e9,stroke:#2e7d32,color:#000
    classDef excl fill:#ffebee,stroke:#c62828,color:#000

    subgraph SRC["Original BIDS dir"]
        BIDS["bids_dir/"]:::src
        BIDSIG[".bidsignore<br/>(22 patterns)"]:::src
        SUBS["sub-*/ses-*/<br/>anat, func, fmap files"]:::src
        DERIVS["derivatives/<br/>(skipped)"]:::src
    end

    SCRIPT["fmriprep_preflight.py<br/><br/>parse_bidsignore<br/>path_matches_any<br/>build_view<br/>verify_view"]:::script

    subgraph VIEW["Symlink view (output)"]
        VPATH["bids_dir/derivatives/<br/>fmriprep_25.2.4_input/"]:::view
        VLINKS["sub-*/ses-*/...<br/>(symlinks to original)"]:::view
        VTOP["dataset_description.json<br/>README, .bidsignore<br/>(symlinks)"]:::view
    end

    EXCL["Excluded files:<br/>• T1w MPRAGEPromo (all)<br/>• T1w/T2w bad sessions<br/>• BOLD per (subject, session, task)<br/>• Run-1 of multi-run BOLDs<br/><br/>118 files (discovery)<br/>134 files (validation)"]:::excl

    BIDS --> SCRIPT
    BIDSIG --> SCRIPT
    SUBS --> SCRIPT
    DERIVS -.->|"NOT walked"| SCRIPT
    SCRIPT --> VPATH
    SCRIPT -.->|"omitted from view"| EXCL
    VPATH --> VLINKS
    VPATH --> VTOP
```

### Multi-anat handling (per `docs/EXCLUSIONS.md`)

Two validation subjects intentionally retain multiple anatomical scans for fmriprep to average:

| Subject | T1w retained | T2w retained | Reason |
|---------|--------------|--------------|--------|
| s1351 | ses-01 + ses-08 | ses-01 only | Both T1w SagMPRAGE clean |
| s1399 | ses-02 only | ses-01 + ses-02 | Both T2w CubePromo decent |

The view contains both anat files for these subjects; fmriprep's default behavior averages them into a per-subject template. `verify_view` asserts the expected counts (`{"s1351": {"T1w": 2}, "s1399": {"T2w": 2}}`) so a regression in `.bidsignore` parsing would fail the pre-flight before any SLURM job is submitted.

---

## 3. fmriprep input / output topology with `--bids-dir-override`

`--bids-dir-override` binds the symlink view as `/data` (input) and binds the registered BIDS dir's `derivatives/` as `/out` (output). Without the override, `/data/derivatives` would point inside the view, causing nested output paths.

```mermaid
flowchart LR
    classDef host fill:#e3f2fd,stroke:#1565c0,color:#000
    classDef container fill:#fff8e1,stroke:#f57c00,color:#000
    classDef arg fill:#fce4ec,stroke:#c2185b,color:#000

    subgraph HOST["Host filesystem"]
        H1["bids_dir/<br/>(original BIDS)"]:::host
        H2["bids_dir/derivatives/<br/>fmriprep_25.2.4_input/<br/>(symlink view)"]:::host
        H3["bids_dir/derivatives/<br/>(write target)"]:::host
        H4["scratch/work/<br/>fmriprep_DS_25.2.4/<br/>(work dir)"]:::host
        H5["templateflow/<br/>(host)"]:::host
    end

    subgraph FLAG["neuro-run flags"]
        F1["--bids-dir-override<br/>= H2 path"]:::arg
        F2["--nthreads 8<br/>--mem-per-cpu-gb 24<br/>--time 7-00:00:00<br/>--array-throttle N"]:::arg
        F3["--output-spaces ...<br/>--fmriprep-args ..."]:::arg
    end

    subgraph CONTAINER["Apptainer container"]
        C1["/data<br/>(reads view)"]:::container
        C2["/out<br/>(writes derivatives)"]:::container
        C3["/work<br/>(intermediate state)"]:::container
        C4["/templateflow"]:::container
    end

    H2 -.->|"bind"| C1
    H3 -.->|"bind"| C2
    H4 -.->|"bind"| C3
    H5 -.->|"bind"| C4
    H1 -.->|"symlinks point back<br/>to original files"| H2
    F1 --> C1
    F2 --> CONTAINER
    F3 --> CONTAINER
    C1 -->|"fmriprep reads"| FMRIPREP["fmriprep 25.2.4<br/>(Apptainer .sif)"]
    FMRIPREP -->|"writes"| C2
    FMRIPREP -->|"resumes from"| C3
```

**Key invariant:** Even though fmriprep sees the view as its BIDS root, the original BIDS dir is never mutated — symlinks point back into it read-only, and outputs land at the registered BIDS dir's `derivatives/`, *not* under the view.

---

## 4. Per-subject SLURM job flow (Phase 1 + Phase 2)

Each subject's fmriprep job follows the same shape. Phase 1 is one job (s03); Phase 2A is an array of 4; Phase 2B is an array of 41.

```mermaid
sequenceDiagram
    participant U as User (controller)
    participant N as neuro-run
    participant S as SLURM scheduler
    participant W as Compute node (russpold)
    participant V as View dir
    participant D as Derivatives dir

    U->>N: submit fmriprep <ds><br/>--bids-dir-override <view><br/>--nthreads 8 --mem-per-cpu-gb 24<br/>--time 7-00:00:00 --array-throttle N
    N->>N: render sbatch from template
    N->>S: sbatch <script>
    S->>U: Job ID assigned
    Note over S: Queue (PD) until 192 GB available

    S->>W: dispatch task<br/>(8 cores × 24 GB)
    W->>V: read symlinks (BIDS files)
    W->>W: anat workflow (FreeSurfer + ANTs)
    W->>W: BOLD workflow per session<br/>(STC, HMC, coreg, resample, CIFTI)
    W->>D: write derivatives
    W->>S: exit code 0 = COMPLETED

    Note over D: sub-XX/anat/*MNI*preproc_T1w.nii.gz<br/>sub-XX/ses-*/func/*preproc_bold.nii.gz<br/>sub-XX/ses-*/func/*den-91k_bold.dtseries.nii<br/>sub-XX/ses-*/func/*confounds_timeseries.tsv<br/>sub-XX.html (report)
```

---

## 5. Failure triage decision tree

If a SLURM task ends in any state other than COMPLETED, the operator follows this decision tree before resubmitting.

```mermaid
flowchart TD
    classDef state fill:#fff3e0,stroke:#e65100,color:#000
    classDef diag fill:#e8eaf6,stroke:#3949ab,color:#000
    classDef action fill:#e8f5e9,stroke:#2e7d32,color:#000
    classDef escalate fill:#ffebee,stroke:#c62828,color:#000

    SACCT["sacct -j JID --format=State,Elapsed,MaxRSS"]:::diag
    LOGS["Inspect derivatives/.../logs/*.err"]:::diag

    OOM{"State=<br/>OUT_OF_MEMORY?"}:::state
    TO{"State=<br/>TIMEOUT?"}:::state
    HASH{"Workflow log<br/>has FileNotFoundError<br/>on *.pklz early?"}:::state
    TAL{"recon-all.log<br/>has 'Talairach failed'?"}:::state
    OTHER{"Other CRITICAL<br/>workflow error?"}:::state

    BUMP["Bump --mem-per-cpu-gb<br/>by 25%, same work dir,<br/>resubmit single subject"]:::action
    RESUME["Resubmit same flags +<br/>same work dir.<br/>fmriprep resumes from cache"]:::action
    WIPE["Wipe that subject's work dir<br/>at scratch/work/.../sub-XX/<br/>then resubmit"]:::action
    ESC["Escalate: should NOT happen<br/>(view excludes bad T1ws).<br/>Investigate which T1w fmriprep<br/>used; check view filtering."]:::escalate
    INV["Investigate crashfile;<br/>fix root cause;<br/>wipe + resubmit"]:::escalate

    SACCT --> LOGS --> OOM
    OOM -->|yes| BUMP
    OOM -->|no| TO
    TO -->|yes| RESUME
    TO -->|no| HASH
    HASH -->|yes| WIPE
    HASH -->|no| TAL
    TAL -->|yes| ESC
    TAL -->|no| OTHER
    OTHER -->|yes| INV
    OTHER -->|no| OK["No retry needed"]
```

---

## 6. Resource and throttling map

```mermaid
flowchart LR
    classDef partition fill:#e3f2fd,stroke:#1565c0,color:#000
    classDef job fill:#fff8e1,stroke:#f57c00,color:#000
    classDef calc fill:#e8f5e9,stroke:#2e7d32,color:#000

    subgraph PART["russpold partition"]
        P1["16 nodes<br/>448 CPUs total<br/>3.4 TB memory total"]:::partition
        NODE_BIG["9 × 256 GB nodes<br/>(32 CPU each)"]:::partition
        NODE_SM["7 × 192 GB nodes<br/>(24 CPU each)"]:::partition
    end

    subgraph TASK["Per-task envelope"]
        T1["8 CPUs<br/>24 GB/CPU (profile)<br/>22 GB/CPU (production)"]:::job
        T2["7-day wall<br/>(russpold max)"]:::job
        T3["Single-subject array task"]:::job
    end

    subgraph FOOTPRINT["Throttle 12 footprint at peak"]
        F1["12 × 8 = 96 CPUs<br/>(21% of partition)"]:::calc
        F2["12 × 176 GB = 2,112 GB<br/>(62% of partition memory)"]:::calc
        F3["Aggressive but not<br/>partition-dominating"]:::calc
    end

    PART --> NODE_BIG
    PART --> NODE_SM
    NODE_BIG -.->|"profile fits any node"| TASK
    NODE_SM -.->|"production: 22 GB × 8 = 176 GB<br/>fits all 16 nodes"| TASK
    TASK --> FOOTPRINT
```

---

## 7. Wall-time projection

| Phase | Job count | Wall (per job) | Throttle | Cumulative wall (worst case) |
|-------|-----------|----------------|----------|------------------------------|
| Phase 0 (pre-flight) | n/a (local) | minutes | n/a | day 0 |
| Phase 1 (s03 profile) | 1 | ≤7 days | n/a | day 0–7 |
| Phase 2A (discovery) | 4 | ≤7 days | 4 | day 7–14 |
| Phase 2B (validation) | 41 | ≤7 days | 12 | day 14–35 |

**Best case:** ~2-3 weeks total (typical subjects finish in 3-5 days).
**Worst case:** ~5 weeks (multiple subjects need 7-day resume).
**Most likely:** 3-4 weeks total.

Phase 2B starts via `--dependency=afterany:$DISCOVERY_JID`, so validation queues immediately when Phase 2A's array task IDs all reach a terminal state (success or failure). `afterany` (not `afterok`) means a single discovery failure does not block the validation phase — that subject is triaged manually while the rest of the work proceeds.

---

## 8. Status as of 2026-04-29 09:55

```mermaid
flowchart TD
    classDef done fill:#c8e6c9,stroke:#2e7d32,stroke-width:2px,color:#000
    classDef active fill:#fff59d,stroke:#f57c00,stroke-width:2px,color:#000
    classDef pending fill:#ffffff,stroke:#9e9e9e,stroke-width:1px,color:#000

    PRE["Pre-flight script + tests<br/>20/20 passing<br/>fmriprep_preflight.py"]:::done
    NEU["neuro-run extension<br/>16/16 passing<br/>--bids-dir-override added"]:::done
    SMOKE["Real-data smoke test<br/>2272 + 26704 files linked<br/>Multi-anat verified"]:::done
    WIPE["Stale dirs wiped<br/>(prior failed-run state cleared)"]:::done
    P1J["Phase 1: Job 23138312<br/>RUNNING since 2026-04-29 09:54<br/>7-day wall, 192 GB"]:::active
    P10["Phase 1 validation +<br/>profile report"]:::pending
    P2A["Phase 2A: discovery (4 subj)"]:::pending
    P2B["Phase 2B: validation (41 subj)"]:::pending
    FINAL["Final validation"]:::pending

    PRE --> NEU --> SMOKE --> WIPE --> P1J --> P10 --> P2A --> P2B --> FINAL
```

| Task | Status | Detail |
|------|--------|--------|
| 1–5: Pre-flight script | ✅ | TDD; 20 tests passing |
| 6: neuro-run `--bids-dir-override` | ✅ | TDD; 16 tests passing |
| 7: Real-data smoke test | ✅ | Both views built and verified |
| 8: Wipe stale dirs | ✅ | Done after `sqlb` confirmed no active jobs |
| 9: Submit Phase 1 (s03 profile) | ✅ | Job 23138312 running on `sh03-06n11` |
| 10: Phase 1 validation + profile report | ⏳ | Waits for Job 23138312 to complete |
| 11: Phase 2A (discovery production) | ⏳ | Pending Phase 1 success |
| 12: Phase 2B (validation production) | ⏳ | Pending Phase 2A submission |
| 13: Daily monitoring + triage | ⏳ | Ongoing during production |
| 14: Final validation | ⏳ | After all 46 subjects complete |
