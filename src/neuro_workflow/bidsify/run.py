"""Orchestrate Flywheel -> BIDS conversion."""

import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from neuro_workflow.bidsify.config import map_acquisition, load_reconciliation_config
from neuro_workflow.bidsify.flywheel_query import (
    collect_subject_sessions,
    build_session_timeline,
    query_project_subjects,
)
from neuro_workflow.bidsify.file_selector import select_files
from neuro_workflow.bidsify.bids_writer import (
    bids_filename,
    patch_sidecar,
    write_dataset_description,
    write_readme,
    download_and_place,
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


def _check_bold_4d(nifti_path):
    """Check that a BOLD NIfTI is 4D. Returns True if valid."""
    try:
        import nibabel as nib
        img = nib.load(nifti_path)
        if len(img.shape) < 4:
            logger.warning("Non-4D BOLD (%dD), adding to .bidsignore: %s", len(img.shape), nifti_path)
            return False
        return True
    except ImportError:
        return True
    except Exception as e:
        logger.warning("Could not validate %s: %s", nifti_path, e)
        return True


def process_subject_session(
    subject_label, session_info, acq_objects, output_dir, log_entries,
    bidsignore_entries=None,
):
    """Process a single session: select files, download, rename, patch sidecars.

    Args:
        subject_label: BIDS subject label (e.g., "s03")
        session_info: Dict with bids_session, fw_session, acquisitions, etc.
        acq_objects: List of Flywheel acquisition objects for this session
        output_dir: BIDS root directory
        log_entries: List to append download log entries to
        bidsignore_entries: List to append .bidsignore patterns to

    Returns:
        List of warning strings for this session (for reconciliation).
    """
    if bidsignore_entries is None:
        bidsignore_entries = []
    bids_ses = session_info["bids_session"]
    sub_dir = Path(output_dir) / f"sub-{subject_label}" / bids_ses

    # Track fieldmap identifier for B0FieldSource patching
    fieldmap_id = None
    bold_sidecars = []
    task_run_counter = Counter()
    warnings = []
    bold_acq_count = 0
    bold_file_count = 0

    # Sort acquisitions by timestamp so duplicate tasks get correct run numbering
    acq_objects_sorted = sorted(acq_objects, key=lambda a: a.timestamp or "")

    for acq in acq_objects_sorted:
        acq = acq.reload()
        mapping = map_acquisition(acq.label)
        if mapping is None:
            if acq.label not in (
                "3Plane Loc SSFSE", "GE HOS FOV28", "GE HOS FOV28_1", "GE HOS FOV28_2"
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

            if not selected:
                logger.error(
                    "No echo files found for %s %s %s, skipping",
                    subject_label, bids_ses, acq.label,
                )
                continue

            bold_file_count += 1

            for echo_info in selected:
                stem = bids_filename(
                    subject_label, bids_ses,
                    task=task_name, run=run, echo=echo_info["echo"], suffix="bold",
                )
                dest_dir = sub_dir / "func"
                is_non4d = False
                if echo_info["nifti"]:
                    nifti_path = dest_dir / f"{stem}.nii.gz"
                    info = download_and_place(
                        acq, echo_info["nifti"], nifti_path
                    )
                    log_entries.append(info)
                    # Add non-4D BOLD to .bidsignore
                    if not _check_bold_4d(nifti_path):
                        rel = nifti_path.relative_to(output_dir)
                        bidsignore_entries.append(str(rel))
                        is_non4d = True
                if echo_info["json"]:
                    json_path = dest_dir / f"{stem}.json"
                    info = download_and_place(acq, echo_info["json"], json_path)
                    log_entries.append(info)
                    if is_non4d:
                        rel = json_path.relative_to(output_dir)
                        bidsignore_entries.append(str(rel))
                    else:
                        # Add TaskName to BOLD sidecar
                        patch_sidecar(json_path, TaskName=task_name)
                        bold_sidecars.append(json_path)

        elif modality == "fmap":
            run = 1  # one fieldmap per session
            fmap_id = bids_filename(
                subject_label, bids_ses, run=run, suffix="fieldmap"
            )
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
            stem = bids_filename(subject_label, bids_ses, acq=acq_label, suffix=suffix)

            if selected.get("nifti"):
                nifti_path = dest_dir / f"{stem}.nii.gz"
                info = download_and_place(
                    acq, selected["nifti"], nifti_path
                )
                log_entries.append(info)
                # MPRAGEPromo T1w files have extra dimensions — add to .bidsignore
                if acq_label and "MPRAGEPromo" in acq_label:
                    rel = nifti_path.relative_to(output_dir)
                    bidsignore_entries.append(str(rel))
                    logger.info("Adding MPRAGEPromo to .bidsignore: %s", rel)
            if selected.get("json"):
                json_path = dest_dir / f"{stem}.json"
                info = download_and_place(
                    acq, selected["json"], json_path
                )
                log_entries.append(info)
                if acq_label and "MPRAGEPromo" in acq_label:
                    rel = json_path.relative_to(output_dir)
                    bidsignore_entries.append(str(rel))

        elif modality == "dwi":
            dir_label = mapping.get("dir")
            acq_label = mapping.get("acq")
            dest_dir = sub_dir / "dwi"
            stem = bids_filename(
                subject_label, bids_ses, acq=acq_label, dir=dir_label, run=1, suffix="dwi"
            )

            for ext in ("nifti", "json", "bval", "bvec"):
                if selected.get(ext):
                    file_ext = {"nifti": ".nii.gz", "json": ".json", "bval": ".bval", "bvec": ".bvec"}[ext]
                    info = download_and_place(
                        acq, selected[ext], dest_dir / f"{stem}{file_ext}"
                    )
                    log_entries.append(info)

    # Patch all BOLD sidecars with B0FieldSource
    if fieldmap_id:
        for sidecar_path in bold_sidecars:
            if sidecar_path.exists():
                patch_sidecar(sidecar_path, b0_field_source=fieldmap_id)

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
    """Process a single subject: query sessions, download files, return results.

    Returns:
        Dict with keys: subject, reconciliation, log_entries, bidsignore_entries.
    """
    log_entries = []
    bidsignore_entries = []

    logger.info("Processing %s...", subject_label)
    sessions = collect_subject_sessions(
        subject_label, all_subjects, aliases, session_overrides=session_overrides,
    )
    sessions = build_session_timeline(sessions)

    fw_sources = [subject_label]
    for variant, canonical in aliases.items():
        if canonical == subject_label:
            fw_sources.append(variant)

    recon = build_reconciliation(subject_label, sessions, fw_sources)

    for i, session_info in enumerate(sessions):
        acq_objects = list(session_info["acquisitions"])

        session_warnings = process_subject_session(
            subject_label, session_info, acq_objects, output_dir, log_entries,
            bidsignore_entries=bidsignore_entries,
        )
        if session_warnings:
            recon["sessions"][i]["warnings"] = session_warnings

    logger.info("Finished %s: %d files", subject_label, len(log_entries))
    return {
        "subject": subject_label,
        "reconciliation": recon,
        "log_entries": log_entries,
        "bidsignore_entries": bidsignore_entries,
    }


def run_bidsify(sample_name, output_dir, subjects=None, flywheel_project=None, overwrite=False):
    """Main entry point for Flywheel -> BIDS conversion.

    Args:
        sample_name: "discovery" or "validation"
        output_dir: Path to BIDS output directory
        subjects: Optional list of subject labels to process (default: all in sample)
        flywheel_project: Flywheel project label (default from config)
        overwrite: Whether to overwrite existing output
    """
    import flywheel

    config = load_reconciliation_config()
    project_label = flywheel_project or config["flywheel_project"]
    aliases = config["subject_aliases"]
    skip = set(config["skip_subjects"])
    session_overrides = config.get("session_overrides", {})

    if subjects is None:
        subjects = config["samples"].get(sample_name, [])

    output_dir = Path(output_dir)
    if (output_dir / "dataset_description.json").exists() and not overwrite:
        raise FileExistsError(
            f"Output directory already contains BIDS data: {output_dir}. Use --overwrite to replace."
        )

    fw = flywheel.Client()
    all_subjects, project = query_project_subjects(fw, project_label)

    # Filter to subjects not in skip list
    subjects_to_process = [s for s in subjects if s not in skip]
    for s in subjects:
        if s in skip:
            logger.info("Skipping %s (in skip list)", s)

    # Process subjects in parallel
    max_workers = min(len(subjects_to_process), 16)
    reconciliation = {"generated": datetime.now(timezone.utc).isoformat(), "subjects": {}}
    all_log_entries = []
    all_bidsignore_entries = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_one_subject, subject_label, all_subjects, aliases, output_dir,
                session_overrides=session_overrides,
            ): subject_label
            for subject_label in subjects_to_process
        }
        for future in as_completed(futures):
            subject_label = futures[future]
            try:
                result = future.result()
                reconciliation["subjects"][result["subject"]] = result["reconciliation"]
                all_log_entries.extend(result["log_entries"])
                all_bidsignore_entries.extend(result["bidsignore_entries"])
            except Exception:
                logger.exception("Failed to process %s", subject_label)

    # Write .bidsignore for non-compliant files (non-4D BOLD, MPRAGEPromo)
    if all_bidsignore_entries:
        bidsignore_path = output_dir / ".bidsignore"
        bidsignore_path.write_text("\n".join(sorted(set(all_bidsignore_entries))) + "\n")
        logger.info("Wrote .bidsignore with %d entries", len(set(all_bidsignore_entries)))

    # Write dataset description
    dataset_names = {
        "discovery": "Network Discovery Sample",
        "validation": "Network Validation Sample",
    }
    ds_name = dataset_names.get(sample_name, sample_name)
    write_dataset_description(output_dir, ds_name)
    write_readme(output_dir, ds_name)

    # Write reconciliation and log
    sourcedata_dir = output_dir / "sourcedata"
    sourcedata_dir.mkdir(parents=True, exist_ok=True)

    with open(sourcedata_dir / "reconciliation.json", "w") as f:
        json.dump(reconciliation, f, indent=2)

    # Write sample notes
    sample_notes = config.get("notes", {}).get(sample_name, [])
    if sample_notes:
        notes_path = sourcedata_dir / "NOTES.txt"
        notes_path.write_text("\n".join(sample_notes) + "\n")
        logger.info("Wrote %d notes to %s", len(sample_notes), notes_path)

    log = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total_files": len(all_log_entries),
        "files": all_log_entries,
    }
    with open(sourcedata_dir / "bidsify_log.json", "w") as f:
        json.dump(log, f, indent=2)

    logger.info(
        "Done. %d subjects, %d files written to %s",
        len(subjects_to_process), len(all_log_entries), output_dir,
    )
