from __future__ import annotations

import json
from pathlib import Path


ENTITY_ORDER = ("task", "acq", "dir", "run", "echo")


def bids_filename(subject: str, session: str, **entities: str | int) -> str:
    suffix = entities.pop("suffix", None)
    parts = [f"sub-{subject}", session]
    for key in ENTITY_ORDER:
        if key in entities:
            parts.append(f"{key}-{entities[key]}")
    stem = "_".join(parts)
    if suffix:
        stem = f"{stem}_{suffix}"
    return stem


def patch_sidecar(
    sidecar_path: str | Path,
    b0_field_identifier: str | None = None,
    b0_field_source: str | None = None,
) -> None:
    sidecar_path = Path(sidecar_path)
    data = json.loads(sidecar_path.read_text())
    if b0_field_identifier is not None:
        data["B0FieldIdentifier"] = b0_field_identifier
    if b0_field_source is not None:
        data["B0FieldSource"] = b0_field_source
    sidecar_path.write_text(json.dumps(data, indent=2))


def write_dataset_description(output_dir: str | Path, name: str) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    desc = {
        "Name": name,
        "BIDSVersion": "1.10.0",
        "DatasetType": "raw",
        "Authors": ["Patrick Bissett", "Russell Poldrack", "Logan Bennett"],
        "GeneratedBy": [{"Name": "neuro-workflow bidsify", "Version": "0.2.0"}],
    }
    (output_dir / "dataset_description.json").write_text(json.dumps(desc, indent=2))


def download_and_place(acq, file_obj, dest_path: str | Path) -> dict:
    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    acq.download_file(file_obj.name, str(dest_path))
    return {
        "fw_filename": file_obj.name,
        "bids_path": str(dest_path),
        "size": file_obj.size,
        "created": file_obj.created,
    }
