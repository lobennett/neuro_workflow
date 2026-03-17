# Integrate compare_fw_oak.py Corrections into Bidsify — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Integrate all Flywheel data corrections from the deprecated `compare_fw_oak.py` script into the bidsify config and query layer.

**Architecture:** Config-driven session overrides in `reconciliation_config.json` processed by `collect_subject_sessions` in `flywheel_query.py`. Two override actions: `exclude` (skip session) and `reassign_to` (move session to different subject). Sample-specific notes written to `sourcedata/NOTES.txt`.

**Tech Stack:** Python, pytest, JSON config

---

## Background

The deprecated script `/home/groups/russpold/code/network_fmri/BIDS_scripts/compare_fw_oak.py` contains hard-coded corrections for Flywheel data issues (mislabeled sessions, duplicate sessions from aliases, subject aliases). These corrections need to be integrated into the bidsify system in a maintainable, config-driven way.

### Corrections from the old script

1. **`ex26207` is actually `s297`** -- currently incorrectly in `skip_subjects`; should be a subject alias
2. **Session `22752` (s03)** -- mislabeled on Flywheel, actually belongs to `s10`
3. **Session exclusions** -- `s03/25210`, `s19-2/22542`, `s29-2/20210305`, `s43-2/20201112` are duplicates or empty
4. **Split sessions (validation)** -- s321, s968, s1326, s1292, s1189, s1391 have sessions split across multiple FW entries; these naturally get separate `ses-NN` labels (correct BIDS behavior)

## Design

### Config schema changes (`reconciliation_config.json`)

Add three new fields:

```json
{
    "subject_aliases": {
        "ex26207": "s297",  // MOVED from skip_subjects
        ...existing...
    },
    "skip_subjects": ["n01"],  // REMOVED ex26207
    "session_overrides": {
        "s03": {
            "22752": {
                "reassign_to": "s10",
                "reason": "Session 22752 (2021-02-12) labeled under s03 on Flywheel but belongs to s10"
            },
            "25210": {
                "exclude": true,
                "reason": "Empty/test session -- no usable imaging data"
            }
        },
        "s19-2": {
            "22542": {
                "exclude": true,
                "reason": "Duplicate of s19 session -- already captured under canonical label"
            }
        },
        "s29-2": {
            "20210305": {
                "exclude": true,
                "reason": "Duplicate of s29 session -- already captured under canonical label"
            }
        },
        "s43-2": {
            "20201112": {
                "exclude": true,
                "reason": "Duplicate of s43 session -- already captured under canonical label"
            }
        }
    },
    "notes": {
        "discovery": [
            "s03/session 22752 was mislabeled on Flywheel -- reassigned to s10 based on scan content and timeline",
            "s29/ses-01 used single-echo BOLD protocol -- no multi-echo func data extracted (protocol mismatch)"
        ],
        "validation": [
            "ex26207 is an alias for s297 on Flywheel",
            "Split sessions exist for s321, s968, s1326, s1292, s1189, s1391 -- these are merged chronologically"
        ]
    }
}
```

Override actions:
- `"exclude": true` -- skip session entirely during collection
- `"reassign_to": "<subject>"` -- remove from source subject, add to target subject

### `flywheel_query.py` changes

`collect_subject_sessions` gains a `session_overrides` parameter:

1. When iterating sessions for a subject, check `session_overrides[fw_subject_label][session_label]`
2. If override has `exclude: true` -- skip with log message
3. If override has `reassign_to` -- skip (collected by target subject)
4. After collecting own sessions, scan all overrides for any `reassign_to == canonical_label` and collect those sessions from their source subjects

### Notes output

`run_bidsify` writes `sourcedata/NOTES.txt` with the sample-specific notes from config after writing reconciliation.json.

### Split sessions

No special handling needed. Flywheel split sessions appear as separate entries and get sequential `ses-NN` labels, which is correct BIDS behavior.

## Files to modify

1. `src/neuro_workflow/bidsify/reconciliation_config.json` -- add session_overrides, notes; fix aliases/skip
2. `src/neuro_workflow/bidsify/flywheel_query.py` -- handle session_overrides in collect_subject_sessions
3. `src/neuro_workflow/bidsify/config.py` -- load session_overrides and notes from config
4. `src/neuro_workflow/bidsify/run.py` -- pass session_overrides to collect_subject_sessions; write NOTES.txt
5. `tests/bidsify/test_flywheel_query.py` -- test override/reassignment/exclusion logic

---

## Implementation Tasks

### Task 1: Update reconciliation_config.json

**Files:**
- Modify: `src/neuro_workflow/bidsify/reconciliation_config.json`

**Step 1: Update the config file**

Move `ex26207` from `skip_subjects` to `subject_aliases`, add `session_overrides` and `notes`:

```json
{
    "flywheel_project": "r01network",
    "subject_aliases": {
        "s19-2": "s19",
        "s29-2": "s29",
        "s43-2": "s43",
        "ex26207": "s297"
    },
    "skip_subjects": ["n01"],
    "session_overrides": {
        "s03": {
            "22752": {
                "reassign_to": "s10",
                "reason": "Session 22752 (2021-02-12) labeled under s03 on Flywheel but belongs to s10"
            },
            "25210": {
                "exclude": true,
                "reason": "Empty/test session -- no usable imaging data"
            }
        },
        "s19-2": {
            "22542": {
                "exclude": true,
                "reason": "Duplicate of s19 session -- already captured under canonical label"
            }
        },
        "s29-2": {
            "20210305": {
                "exclude": true,
                "reason": "Duplicate of s29 session -- already captured under canonical label"
            }
        },
        "s43-2": {
            "20201112": {
                "exclude": true,
                "reason": "Duplicate of s43 session -- already captured under canonical label"
            }
        }
    },
    "notes": {
        "discovery": [
            "s03/session 22752 was mislabeled on Flywheel -- reassigned to s10 based on scan content and timeline",
            "s29/ses-01 used single-echo BOLD protocol -- no multi-echo func data extracted (protocol mismatch)"
        ],
        "validation": [
            "ex26207 is an alias for s297 on Flywheel",
            "Split sessions exist for s321, s968, s1326, s1292, s1189, s1391 -- these are merged chronologically"
        ]
    },
    "samples": {
        "discovery": ["s03", "s10", "s19", "s29", "s43"],
        "validation": [
            "s76", "s247", "s214", "s216", "s222", "s250", "s286", "s295",
            "s297", "s300", "s320", "s321", "s336", "s373", "s394", "s415",
            "s432", "s480", "s180", "s599", "s645", "s823", "s874", "s956",
            "s968", "s1035", "s1057", "s1058", "s1127", "s1134", "s1165",
            "s1175", "s1178", "s1189", "s1258", "s1266", "s1267", "s1270",
            "s1273", "s1292", "s1314", "s1320", "s1326", "s1338", "s1351",
            "s1391", "s1399", "s1402", "s1408", "s1445", "s1481", "s1486"
        ]
    }
}
```

**Step 2: Verify JSON is valid**

Run: `python -c "import json; json.load(open('src/neuro_workflow/bidsify/reconciliation_config.json'))"`
Expected: No output (success)

**Step 3: Commit**

```bash
git add src/neuro_workflow/bidsify/reconciliation_config.json
git commit -m "feat(bidsify): add session_overrides and notes to reconciliation config

Integrates corrections from deprecated compare_fw_oak.py:
- Move ex26207 from skip_subjects to subject_aliases (alias for s297)
- Add session_overrides for cross-subject reassignment and exclusions
- Add per-sample notes for documentation"
```

---

### Task 2: Write tests for session override logic

**Files:**
- Modify: `tests/bidsify/test_flywheel_query.py`

**Step 1: Write failing tests for exclude, reassign, and no-override cases**

Add to `TestCollectSubjectSessions` in `tests/bidsify/test_flywheel_query.py`:

```python
def test_exclude_override_skips_session(self):
    """Sessions with exclude override are not collected."""
    sess1 = _mock_session("22752", datetime(2024, 1, 1), ["bold"])
    sess2 = _mock_session("25210", datetime(2024, 2, 1), ["t1w"])
    sess3 = _mock_session("good", datetime(2024, 3, 1), ["bold"])
    subj = _mock_subject("s03", [sess1, sess2, sess3])

    overrides = {
        "s03": {
            "25210": {"exclude": True, "reason": "Empty session"},
        },
    }
    result = collect_subject_sessions("s03", [subj], {}, session_overrides=overrides)

    assert len(result) == 2
    labels = [r["fw_session"].label for r in result]
    assert "25210" not in labels
    assert "22752" in labels
    assert "good" in labels

def test_reassign_override_removes_from_source(self):
    """Sessions with reassign_to override are not collected for source subject."""
    sess1 = _mock_session("22752", datetime(2024, 1, 1), ["bold"])
    sess2 = _mock_session("good", datetime(2024, 3, 1), ["bold"])
    subj = _mock_subject("s03", [sess1, sess2])

    overrides = {
        "s03": {
            "22752": {"reassign_to": "s10", "reason": "Mislabeled"},
        },
    }
    result = collect_subject_sessions("s03", [subj], {}, session_overrides=overrides)

    assert len(result) == 1
    assert result[0]["fw_session"].label == "good"

def test_reassign_override_adds_to_target(self):
    """Sessions reassigned to a subject appear in that subject's collection."""
    sess_s03 = _mock_session("22752", datetime(2024, 1, 1), ["bold"])
    sess_s10 = _mock_session("own_sess", datetime(2024, 2, 1), ["t1w"])
    subj_s03 = _mock_subject("s03", [sess_s03])
    subj_s10 = _mock_subject("s10", [sess_s10])

    overrides = {
        "s03": {
            "22752": {"reassign_to": "s10", "reason": "Mislabeled"},
        },
    }
    result = collect_subject_sessions(
        "s10", [subj_s03, subj_s10], {}, session_overrides=overrides
    )

    assert len(result) == 2
    labels = [r["fw_session"].label for r in result]
    assert "22752" in labels
    assert "own_sess" in labels
    # 22752 is earlier so should come first
    assert result[0]["fw_session"].label == "22752"

def test_no_overrides_backward_compatible(self):
    """Without session_overrides, behavior is unchanged."""
    sess = _mock_session("ses1", datetime(2024, 1, 1))
    subj = _mock_subject("s43", [sess])

    result = collect_subject_sessions("s43", [subj], {})
    assert len(result) == 1

def test_override_on_alias_subject(self):
    """Overrides keyed by alias label (e.g. s19-2) work correctly."""
    sess_alias = _mock_session("22542", datetime(2024, 1, 1), ["bold"])
    sess_main = _mock_session("good", datetime(2024, 2, 1), ["bold"])
    subj_alias = _mock_subject("s19-2", [sess_alias])
    subj_main = _mock_subject("s19", [sess_main])

    overrides = {
        "s19-2": {
            "22542": {"exclude": True, "reason": "Duplicate"},
        },
    }
    result = collect_subject_sessions(
        "s19", [subj_main, subj_alias], {"s19-2": "s19"},
        session_overrides=overrides,
    )

    assert len(result) == 1
    assert result[0]["fw_session"].label == "good"
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/users/logben/neuro_workflow && python -m pytest tests/bidsify/test_flywheel_query.py -v -k "override or reassign or backward" 2>&1 | tail -20`
Expected: FAIL — `collect_subject_sessions` does not accept `session_overrides` keyword

**Step 3: Commit test stubs**

```bash
git add tests/bidsify/test_flywheel_query.py
git commit -m "test(bidsify): add tests for session override logic in collect_subject_sessions"
```

---

### Task 3: Implement session overrides in flywheel_query.py

**Files:**
- Modify: `src/neuro_workflow/bidsify/flywheel_query.py`

**Step 1: Update collect_subject_sessions to accept and process overrides**

Replace the `collect_subject_sessions` function:

```python
def collect_subject_sessions(
    canonical_label: str,
    all_subjects: list[Any],
    aliases: dict[str, str],
    session_overrides: dict[str, dict] | None = None,
) -> list[dict[str, Any]]:
    """Collect all sessions for a canonical subject, merging aliased labels.

    Args:
        canonical_label: The canonical subject label (e.g. "s10").
        all_subjects: All FW subject objects in the project.
        aliases: Mapping of variant label -> canonical label.
        session_overrides: Optional dict keyed by FW subject label, then
            session label. Each value is a dict with either
            ``{"exclude": true}`` or ``{"reassign_to": "<subject>"}``
            plus an optional ``"reason"`` string.

    Returns list of dicts sorted by timestamp:
        {fw_subject, fw_session, timestamp, acquisitions}
    """
    overrides = session_overrides or {}

    # Build set of FW labels that map to this canonical label
    matching_labels = {canonical_label}
    for variant, canon in aliases.items():
        if canon == canonical_label:
            matching_labels.add(variant)

    # Index all_subjects by label for reassignment lookups
    subjects_by_label: dict[str, Any] = {s.label: s for s in all_subjects}

    sessions: list[dict[str, Any]] = []
    for subj in all_subjects:
        if subj.label not in matching_labels:
            continue
        subj_overrides = overrides.get(subj.label, {})
        for sess in subj.sessions():
            ovr = subj_overrides.get(sess.label, {})
            if ovr.get("exclude"):
                logger.info(
                    "Excluding %s/%s: %s",
                    subj.label, sess.label, ovr.get("reason", ""),
                )
                continue
            if ovr.get("reassign_to"):
                logger.info(
                    "Skipping %s/%s (reassigned to %s): %s",
                    subj.label, sess.label,
                    ovr["reassign_to"], ovr.get("reason", ""),
                )
                continue
            sessions.append(
                {
                    "fw_subject": subj,
                    "fw_session": sess,
                    "timestamp": sess.timestamp,
                    "acquisitions": sess.acquisitions(),
                }
            )

    # Collect sessions reassigned TO this canonical subject from other subjects
    for src_label, src_overrides in overrides.items():
        for ses_label, ovr in src_overrides.items():
            if ovr.get("reassign_to") != canonical_label:
                continue
            src_subj = subjects_by_label.get(src_label)
            if src_subj is None:
                logger.warning(
                    "Reassign source subject '%s' not found in project",
                    src_label,
                )
                continue
            for sess in src_subj.sessions():
                if sess.label == ses_label:
                    logger.info(
                        "Reassigning %s/%s -> %s: %s",
                        src_label, ses_label,
                        canonical_label, ovr.get("reason", ""),
                    )
                    sessions.append(
                        {
                            "fw_subject": src_subj,
                            "fw_session": sess,
                            "timestamp": sess.timestamp,
                            "acquisitions": sess.acquisitions(),
                        }
                    )
                    break

    sessions.sort(key=lambda s: s["timestamp"])
    return sessions
```

**Step 2: Run tests to verify they pass**

Run: `cd /home/users/logben/neuro_workflow && python -m pytest tests/bidsify/test_flywheel_query.py -v 2>&1 | tail -20`
Expected: All tests PASS

**Step 3: Commit**

```bash
git add src/neuro_workflow/bidsify/flywheel_query.py
git commit -m "feat(bidsify): implement session overrides in collect_subject_sessions

Supports two override actions:
- exclude: skip session entirely
- reassign_to: move session to a different subject's timeline"
```

---

### Task 4: Wire overrides and notes through run.py

**Files:**
- Modify: `src/neuro_workflow/bidsify/run.py`

**Step 1: Load session_overrides from config and pass to collect_subject_sessions**

In `_process_one_subject`, add `session_overrides` parameter and pass it through. In `run_bidsify`, load overrides from config and pass to the executor.

In `_process_one_subject`, change signature:

```python
def _process_one_subject(subject_label, all_subjects, aliases, output_dir, session_overrides=None):
```

And update the `collect_subject_sessions` call:

```python
    sessions = collect_subject_sessions(subject_label, all_subjects, aliases, session_overrides=session_overrides)
```

In `run_bidsify`, after loading config, extract overrides:

```python
    session_overrides = config.get("session_overrides", {})
```

And pass to executor:

```python
            executor.submit(
                _process_one_subject, subject_label, all_subjects, aliases, output_dir,
                session_overrides=session_overrides,
            ): subject_label
```

**Step 2: Write NOTES.txt from config notes**

After writing reconciliation.json in `run_bidsify`, add:

```python
    # Write sample notes
    sample_notes = config.get("notes", {}).get(sample_name, [])
    if sample_notes:
        notes_path = sourcedata_dir / "NOTES.txt"
        notes_path.write_text("\n".join(sample_notes) + "\n")
        logger.info("Wrote %d notes to %s", len(sample_notes), notes_path)
```

**Step 3: Run full test suite**

Run: `cd /home/users/logben/neuro_workflow && python -m pytest tests/bidsify/ -v -k "not test_download_and_place" 2>&1 | tail -20`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add src/neuro_workflow/bidsify/run.py
git commit -m "feat(bidsify): wire session_overrides through run pipeline and write NOTES.txt

- _process_one_subject passes session_overrides to collect_subject_sessions
- run_bidsify writes sourcedata/NOTES.txt from config notes"
```

---

### Task 5: Run existing tests and verify nothing broke

**Step 1: Run all bidsify tests**

Run: `cd /home/users/logben/neuro_workflow && python -m pytest tests/bidsify/ -v -k "not test_download_and_place" 2>&1 | tail -30`
Expected: All PASS

**Step 2: Run pipeline tests**

Run: `cd /home/users/logben/neuro_workflow && python -m pytest tests/bidsify/test_pipeline.py -v 2>&1 | tail -20`
Expected: All PASS
