"""Audit every T1w-like acquisition for a subject across Flywheel sessions.

Walks all sessions for the canonical subject (merging aliases), lists every
acquisition whose label looks anatomical (T1w/MPRAGE/SagMPRAGE/Promo), and
for each acquisition prints every contained file with metadata (size,
classification, BIDS info, file-level info like SeriesNumber).

Designed for forensic comparison against existing BIDS T1ws when the rescue
strategy needs another candidate.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _is_anat_label(label: str) -> bool:
    L = (label or '').lower()
    if 't2w' in L or 't2_' in L or 't2*' in L or 't2star' in L:
        return False
    return any(k in L for k in ('t1w', 'mprage', 'promo', 'anat', 'sagittal'))


def _is_anat_file(fname: str) -> bool:
    L = (fname or '').lower()
    if not (L.endswith('.nii') or L.endswith('.nii.gz') or L.endswith('.dicom.zip') or L.endswith('.zip')):
        return False
    return any(k in L for k in ('t1', 'mprage', 'promo', 'anat'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--subject', required=True, help='Canonical subject label (e.g., s03)')
    parser.add_argument('--config', type=Path,
                        default=Path('config/pipeline_config.json'),
                        help='Path to pipeline_config.json')
    parser.add_argument('--output-json', type=Path, default=None,
                        help='Write full audit to JSON here (default: stdout pretty-print)')
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    fw_cfg = config['flywheel']
    aliases = fw_cfg.get('subject_aliases', {})

    import flywheel
    from neuro_workflow.bidsify.flywheel_query import query_project_subjects

    fw = flywheel.Client()
    all_subjects, _project = query_project_subjects(fw, fw_cfg['project'])

    matching_labels = {args.subject}
    for variant, canon in aliases.items():
        if canon == args.subject:
            matching_labels.add(variant)

    audit: list[dict[str, Any]] = []
    for subj in all_subjects:
        if subj.label not in matching_labels:
            continue
        for sess in subj.sessions():
            ts = sess.timestamp.isoformat() if sess.timestamp else ''
            for acq in sess.acquisitions():
                if not _is_anat_label(acq.label):
                    continue
                acq = fw.get_acquisition(acq.id)  # reload for full metadata
                for f in acq.files:
                    if not _is_anat_file(f.name):
                        continue
                    info = getattr(f, 'info', {}) or {}
                    classif = getattr(f, 'classification', {}) or {}
                    audit.append({
                        'fw_subject': subj.label,
                        'fw_session': sess.label,
                        'fw_session_timestamp': ts,
                        'fw_acquisition': acq.label,
                        'fw_acquisition_id': acq.id,
                        'file_name': f.name,
                        'file_size_bytes': getattr(f, 'size', None),
                        'file_type': getattr(f, 'type', None),
                        'classification': classif,
                        'SeriesNumber': info.get('SeriesNumber'),
                        'SeriesDescription': info.get('SeriesDescription'),
                        'ProtocolName': info.get('ProtocolName'),
                        'AcquisitionTime': info.get('AcquisitionTime'),
                        'AcquisitionDateTime': info.get('AcquisitionDateTime'),
                        'EchoTime': info.get('EchoTime'),
                        'RepetitionTime': info.get('RepetitionTime'),
                        'InversionTime': info.get('InversionTime'),
                        'FlipAngle': info.get('FlipAngle'),
                        'PixelSpacing': info.get('PixelSpacing'),
                        'SliceThickness': info.get('SliceThickness'),
                    })

    audit.sort(key=lambda r: (r['fw_session_timestamp'], r['fw_acquisition'], r['file_name']))

    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(audit, indent=2))
        print(f'Wrote {len(audit)} rows to {args.output_json}')
    else:
        print(json.dumps(audit, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
