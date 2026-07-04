"""Orchestrate Flywheel -> BIDS conversion."""

import json
import logging
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from neuro_workflow.bidsify.bids_writer import (
    bids_filename,
    download_and_place,
    patch_sidecar,
    write_dataset_description,
    write_readme,
)
from neuro_workflow.bidsify.config import load_pipeline_config, map_acquisition
from neuro_workflow.bidsify.file_selector import select_files
from neuro_workflow.bidsify.flywheel_query import (
    build_session_timeline,
    collect_subject_sessions,
    query_project_subjects,
)
from neuro_workflow.bidsify.physio import convert_physio_to_bids
from neuro_workflow.bidsify.physio_query import (
    find_gephysio_analyses,
    match_analyses_to_acquisitions,
)

logger = logging.getLogger(__name__)


def build_reconciliation(canonical_label, sessions, fw_sources):
    """Build reconciliation record for a subject.

    Args:
        canonical_label: BIDS subject label
        sessions: List of session dicts with bids_session assigned
        fw_sources: List of FW subject labels that contributed

    Returns:
        Dict with reconciliation info for this subject
    """
    return {
        "flywheel_sources": sorted(set(fw_sources)),
        "total_sessions": len(sessions),
        "sessions": [
            {
                "bids_session": s["bids_session"],
                "fw_subject": s["fw_subject"].label,
                "fw_session_label": s["fw_session"].label,
                "timestamp": s["timestamp"].isoformat() if s["timestamp"] else None,
                "acquisitions": [a.label for a in s["acquisitions"]],
                "warnings": [],
            }
            for s in sessions
        ],
    }


def write_session_timestamps(rows, sourcedata_dir, suffix=""):
    """Write session_timestamps.tsv to sourcedata directory."""
    tsv_path = Path(sourcedata_dir) / f"session_timestamps{suffix}.tsv"
    header = "subject\tbids_session\tflywheel_session_label\tflywheel_timestamp"
    lines = [header]
    for row in sorted(rows, key=lambda r: (r["subject"], r["bids_session"])):
        lines.append(
            f"{row['subject']}\t{row['bids_session']}\t{row['flywheel_session_label']}\t{row['flywheel_timestamp']}"
        )
    tsv_path.write_text("\n".join(lines) + "\n")


def download_physio_analysis(analysis, dest_dir):
    """Download gephysio analysis CSV files to a local directory.

    Args:
        analysis: Flywheel analysis object.
        dest_dir: Path to download files into.

    Returns:
        Path to the directory containing downloaded files.
    """
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    for f in analysis.files:
        if f.name.endswith(".csv"):
            analysis.download_file(f.name, str(dest_dir / f.name))
    return dest_dir


def process_subject_session(
    subject_label,
    session_info,
    acq_objects,
    output_dir,
    log_entries,
):
    """Process a single session: select files, download, rename, patch sidecars.

    Args:
        subject_label: BIDS subject label (e.g., "s03")
        session_info: Dict with bids_session, fw_session, acquisitions, etc.
        acq_objects: List of Flywheel acquisition objects for this session
        output_dir: BIDS root directory
        log_entries: List to append download log entries to

    Returns:
        List of warning strings for this session (for reconciliation).
    """
    bids_ses = session_info["bids_session"]
    sub_dir = Path(output_dir) / f"sub-{subject_label}" / bids_ses

    # Track fieldmap identifier for B0FieldSource patching
    fieldmap_id = None
    bold_sidecars = []
    task_run_counter = Counter()
    anat_run_counter = Counter()
    dwi_run_counter = Counter()
    warnings = []
    bold_acq_count = 0
    bold_file_count = 0
    acq_id_to_task = {}

    # Sort acquisitions by timestamp so duplicate tasks get correct run numbering
    acq_objects_sorted = sorted(acq_objects, key=lambda a: a.timestamp or "")

    for acq in acq_objects_sorted:
        acq = acq.reload()
        mapping = map_acquisition(acq.label)
        if mapping is None:
            if acq.label not in (
                "3Plane Loc SSFSE",
                "GE HOS FOV28",
                "GE HOS FOV28_1",
                "GE HOS FOV28_2",
            ):
                logger.warning("Unknown acquisition '%s', skipping", acq.label)
            continue

        modality = mapping["modality"]
        selected = select_files(acq.files, modality)

        if modality == "func":
            task_name = mapping["task"]
            task_run_counter[task_name] += 1
            run = task_run_counter[task_name]
            bold_acq_count += 1

            # Track acq ID for physio matching
            acq_id_to_task[acq.id] = {"task": task_name, "run": run}

            if not selected:
                logger.error(
                    "No echo files found for %s %s %s, skipping",
                    subject_label,
                    bids_ses,
                    acq.label,
                )
                continue

            bold_file_count += 1

            for echo_info in selected:
                stem = bids_filename(
                    subject_label,
                    bids_ses,
                    task=task_name,
                    run=run,
                    echo=echo_info["echo"],
                    suffix="bold",
                )
                dest_dir = sub_dir / "func"
                if echo_info["nifti"]:
                    nifti_path = dest_dir / f"{stem}.nii.gz"
                    info = download_and_place(acq, echo_info["nifti"], nifti_path)
                    log_entries.append(info)

                if echo_info["json"]:
                    json_path = dest_dir / f"{stem}.json"
                    info = download_and_place(acq, echo_info["json"], json_path)
                    log_entries.append(info)
                    # Add TaskName to BOLD sidecar
                    patch_sidecar(json_path, TaskName=task_name)
                    bold_sidecars.append(json_path)

        elif modality == "fmap":
            run = 1  # one fieldmap per session
            fmap_id = bids_filename(subject_label, bids_ses, run=run, suffix="fieldmap")
            fieldmap_id = fmap_id
            dest_dir = sub_dir / "fmap"

            if selected.get("fieldmap_nifti"):
                stem = bids_filename(subject_label, bids_ses, run=run, suffix="fieldmap")
                info = download_and_place(
                    acq, selected["fieldmap_nifti"], dest_dir / f"{stem}.nii.gz"
                )
                log_entries.append(info)
            if selected.get("fieldmap_json"):
                stem = bids_filename(subject_label, bids_ses, run=run, suffix="fieldmap")
                json_path = dest_dir / f"{stem}.json"
                info = download_and_place(acq, selected["fieldmap_json"], json_path)
                log_entries.append(info)
                patch_sidecar(json_path, b0_field_identifier=fmap_id, Units="Hz")
            if selected.get("magnitude_nifti"):
                stem = bids_filename(subject_label, bids_ses, run=run, suffix="magnitude")
                info = download_and_place(
                    acq, selected["magnitude_nifti"], dest_dir / f"{stem}.nii.gz"
                )
                log_entries.append(info)

        elif modality == "anat":
            suffix = mapping["suffix"]
            acq_label = mapping.get("acq")
            dest_dir = sub_dir / "anat"

            anat_key = (suffix, acq_label)
            anat_run_counter[anat_key] += 1
            run = anat_run_counter[anat_key]

            stem = bids_filename(subject_label, bids_ses, acq=acq_label, run=run, suffix=suffix)

            if selected.get("nifti"):
                info = download_and_place(acq, selected["nifti"], dest_dir / f"{stem}.nii.gz")
                log_entries.append(info)
            if selected.get("json"):
                info = download_and_place(acq, selected["json"], dest_dir / f"{stem}.json")
                log_entries.append(info)

        elif modality == "dwi":
            dir_label = mapping.get("dir")
            acq_label = mapping.get("acq")
            dest_dir = sub_dir / "dwi"

            dwi_key = (dir_label, acq_label)
            dwi_run_counter[dwi_key] += 1
            run = dwi_run_counter[dwi_key]

            stem = bids_filename(
                subject_label, bids_ses, acq=acq_label, dir=dir_label, run=run, suffix="dwi"
            )

            for ext in ("nifti", "json", "bval", "bvec"):
                if selected.get(ext):
                    file_ext = {
                        "nifti": ".nii.gz",
                        "json": ".json",
                        "bval": ".bval",
                        "bvec": ".bvec",
                    }[ext]
                    info = download_and_place(acq, selected[ext], dest_dir / f"{stem}{file_ext}")
                    log_entries.append(info)

    # Patch all BOLD sidecars with B0FieldSource
    if fieldmap_id:
        for sidecar_path in bold_sidecars:
            if sidecar_path.exists():
                patch_sidecar(sidecar_path, b0_field_source=fieldmap_id)

    # Process physio data from gephysio analyses
    if acq_id_to_task:
        try:
            fw_session = session_info["fw_session"].reload()
            physio_analyses = find_gephysio_analyses(fw_session)
            if physio_analyses:
                matched = match_analyses_to_acquisitions(physio_analyses, acq_id_to_task)
                func_dir = sub_dir / "func"
                for match in matched:
                    with tempfile.TemporaryDirectory() as tmpdir:
                        dl_dir = download_physio_analysis(match["analysis"], tmpdir)
                        for channel in ("cardiac", "respiratory"):
                            convert_physio_to_bids(
                                input_dir=dl_dir,
                                output_dir=func_dir,
                                subject=subject_label,
                                session=bids_ses,
                                task=match["task"],
                                run=match["run"],
                                channel=channel,
                            )
        except Exception as e:
            logger.exception(
                "Failed to process physio for %s %s: %s", subject_label, bids_ses, str(e)
            )
            warnings.append(f"Failed to process physiological data: {str(e)}")

    # Generate session warnings for reconciliation
    if bold_acq_count == 0:
        warnings.append("No BOLD acquisitions in session")
    elif bold_file_count == 0:
        warnings.append(
            "BOLD acquisitions present but no multi-echo files found"
            " — possible protocol mismatch"
        )

    return warnings


def _process_one_subject(subject_label, all_subjects, aliases, output_dir, session_overrides=None):
    """Process a single subject: query sessions, download files, return results."""
    log_entries = []

    logger.info("Processing %s...", subject_label)
    sessions = collect_subject_sessions(
        subject_label,
        all_subjects,
        aliases,
        session_overrides=session_overrides,
    )
    sessions = build_session_timeline(sessions)

    fw_sources = [subject_label]
    for variant, canonical in aliases.items():
        if canonical == subject_label:
            fw_sources.append(variant)

    recon = build_reconciliation(subject_label, sessions, fw_sources)

    timestamp_rows = []
    for i, session_info in enumerate(sessions):
        acq_objects = list(session_info["acquisitions"])

        session_warnings = process_subject_session(
            subject_label,
            session_info,
            acq_objects,
            output_dir,
            log_entries,
        )
        if session_warnings:
            recon["sessions"][i]["warnings"] = session_warnings

        timestamp_rows.append(
            {
                "subject": subject_label,
                "bids_session": session_info["bids_session"],
                "flywheel_session_label": session_info["fw_session"].label,
                "flywheel_timestamp": session_info["timestamp"].isoformat()
                if session_info["timestamp"]
                else "",
            }
        )

    logger.info("Finished %s: %d files", subject_label, len(log_entries))
    return {
        "subject": subject_label,
        "reconciliation": recon,
        "log_entries": log_entries,
        "timestamp_rows": timestamp_rows,
    }


def run_bidsify(sample_name, output_dir, subjects=None, flywheel_project=None, overwrite=False):
    """Main entry point for Flywheel -> BIDS conversion."""
    import flywheel

    config = load_pipeline_config()
    fw_config = config["flywheel"]
    project_label = flywheel_project or fw_config["project"]
    aliases = fw_config["subject_aliases"]
    skip = set(fw_config["skip_subjects"])
    session_overrides = fw_config.get("session_overrides", {})

    # When --subjects targets a subset, suffix metadata files to avoid
    # overwriting the original full-run logs (preserves provenance).
    rerun_suffix = ""
    if subjects is not None:
        rerun_suffix = f"_rerun-{'-'.join(subjects)}"

    if subjects is None:
        sample_data = config["samples"].get(sample_name, [])
        subjects = list(sample_data.keys()) if isinstance(sample_data, dict) else sample_data

    output_dir = Path(output_dir)
    if (output_dir / "dataset_description.json").exists() and not overwrite:
        raise FileExistsError(
            f"Output directory already contains BIDS data: {output_dir}. Use --overwrite to replace."
        )

    fw = flywheel.Client()
    all_subjects, project = query_project_subjects(fw, project_label)

    subjects_to_process = [s for s in subjects if s not in skip]
    for s in subjects:
        if s in skip:
            logger.info("Skipping %s (in skip list)", s)

    reconciliation = {"generated": datetime.now(UTC).isoformat(), "subjects": {}}
    all_log_entries = []
    all_timestamp_rows = []

    logger.info("Processing %d subjects sequentially", len(subjects_to_process))

    for subject_label in subjects_to_process:
        try:
            result = _process_one_subject(
                subject_label,
                all_subjects,
                aliases,
                output_dir,
                session_overrides=session_overrides,
            )
            reconciliation["subjects"][result["subject"]] = result["reconciliation"]
            all_log_entries.extend(result["log_entries"])
            all_timestamp_rows.extend(result["timestamp_rows"])
            logger.info("Processed %s: %d files", subject_label, len(result["log_entries"]))
        except Exception:
            logger.exception("Failed to process %s", subject_label)

    dataset_names = {
        "discovery": "Network Discovery Sample",
        "validation": "Network Validation Sample",
        "excluded": "Network Excluded Sample",
    }
    ds_name = dataset_names.get(sample_name, sample_name)
    write_dataset_description(output_dir, ds_name)
    write_readme(output_dir, ds_name)

    sourcedata_dir = output_dir / "sourcedata"
    sourcedata_dir.mkdir(parents=True, exist_ok=True)

    with open(sourcedata_dir / f"reconciliation{rerun_suffix}.json", "w") as f:
        json.dump(reconciliation, f, indent=2)

    write_session_timestamps(all_timestamp_rows, sourcedata_dir, suffix=rerun_suffix)

    sample_notes = config.get("notes", {}).get(sample_name, [])
    if sample_notes:
        notes_path = sourcedata_dir / "NOTES.txt"
        notes_path.write_text("\n".join(sample_notes) + "\n")

    log = {
        "generated": datetime.now(UTC).isoformat(),
        "total_files": len(all_log_entries),
        "files": all_log_entries,
    }
    with open(sourcedata_dir / f"bidsify_log{rerun_suffix}.json", "w") as f:
        json.dump(log, f, indent=2)

    logger.info(
        "Done. %d subjects, %d files written to %s",
        len(subjects_to_process),
        len(all_log_entries),
        output_dir,
    )
