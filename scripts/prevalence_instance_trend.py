"""Summarize the per-instance prevalence trend produced by
``prevalence_by_instance_run.py``.

For each (cohort, task, contrast) cell, reports the mean overall-prevalence
MAP within a 'signal ROI' for each session instance. The ROI is the top
decile of a reference prevalence map:

  * validation: the existing fixed-effects prevalence map under
    ``…/derivatives/prevalence/parametric/outputs`` (independent reference).
  * discovery: no fixed-effects prevalence outputs exist, so the ROI is the
    top decile of the cell's OWN across-instance mean map. This is
    self-referential (circular) and only indicates relative change across
    instances within the same vertices — labeled ``SELF`` in the output.

Writes a TSV (one row per cohort/task/contrast/instance) and prints a table.

Usage:
  uv run python scripts/prevalence_instance_trend.py \\
      --inst-root /scratch/users/logben/prevalence_by_instance \\
      --out-tsv /scratch/users/logben/prevalence_by_instance/instance_trend_summary.tsv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

import nibabel as nib
import numpy as np

from neuro_workflow.analysis.prevalence.aggregate import MAIN_CELLS as CELLS

FE_OUTPUTS = {
    'validation': '/scratch/users/logben/validation_bids/derivatives/prevalence/parametric/outputs',
    'discovery': '/scratch/users/logben/discovery_bids/derivatives/prevalence/parametric/outputs',
}
MAX_INSTANCE = 6


def _load(p: str) -> np.ndarray:
    return np.asarray(nib.load(p).darrays[0].data, dtype=np.float64)


def _inst_map(root, cohort, task, contrast, inst, hemi):
    p = os.path.join(
        root, cohort,
        f'{cohort}_task-{task}_instance-{inst}_hemi-{hemi}_contrast-{contrast}'
        f'_rtmodel-RTDur_direction-overall_stat-prevalence-map.func.gii')
    return _load(p) if os.path.exists(p) else None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inst-root', type=Path,
                    default=Path('/scratch/users/logben/prevalence_by_instance'))
    ap.add_argument('--out-tsv', type=Path, default=None)
    args = ap.parse_args(argv)
    root = str(args.inst_root)

    rows = []
    for cohort in ('discovery', 'validation'):
        print(f'\n========== {cohort.upper()} ==========')
        print(f'{"task":20s} {"contrast":24s} ROI  per-instance mean prevalence in signal ROI')
        for task, contrast in CELLS:
            avail = {}
            for hemi in ('L', 'R'):
                maps = {i: _inst_map(root, cohort, task, contrast, i, hemi)
                        for i in range(1, MAX_INSTANCE + 1)}
                maps = {i: m for i, m in maps.items() if m is not None}
                if maps:
                    avail[hemi] = maps
            if not avail:
                print(f'{task:20s} {contrast:24s} --   (no maps)')
                continue
            roi = {}
            src = 'FE'
            for hemi in avail:
                ref = None
                fe_dir = FE_OUTPUTS.get(cohort, '')
                fp = os.path.join(
                    fe_dir,
                    f'{cohort}_task-{task}_hemi-{hemi}_contrast-{contrast}'
                    f'_rtmodel-RTDur_stat-prevalence-map.func.gii')
                if fe_dir and os.path.exists(fp):
                    ref = _load(fp)
                if ref is None:
                    src = 'SELF'
                    ref = np.nanmean(np.vstack(list(avail[hemi].values())), axis=0)
                fin = ref[np.isfinite(ref)]
                thr = np.nanpercentile(fin, 90) if fin.size else np.inf
                roi[hemi] = (ref >= thr) & np.isfinite(ref)
            vals = []
            for i in range(1, MAX_INSTANCE + 1):
                man = os.path.join(
                    root, cohort,
                    f'{cohort}_task-{task}_instance-{i}_contrast-{contrast}_manifest.json')
                n = None
                if os.path.exists(man):
                    d = json.load(open(man))
                    n = d.get('L', d.get('R', {})).get('n_subjects')
                parts = [avail[h][i][roi[h]][np.isfinite(avail[h][i][roi[h]])]
                         for h in avail if i in avail[h]]
                if parts:
                    roi_mean = float(np.concatenate(parts).mean())
                    vals.append((i, n, roi_mean))
                    rows.append({
                        'cohort': cohort, 'task': task, 'contrast': contrast,
                        'instance': i, 'n_subjects': n,
                        'roi_source': src, 'roi_mean_prevalence': round(roi_mean, 4),
                    })
            trend = '  '.join(f'i{i}(n{n}):{v:.2f}' for i, n, v in vals)
            print(f'{task:20s} {contrast:24s} {src:4s} {trend}')

    if args.out_tsv:
        args.out_tsv.parent.mkdir(parents=True, exist_ok=True)
        with args.out_tsv.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=[
                'cohort', 'task', 'contrast', 'instance', 'n_subjects',
                'roi_source', 'roi_mean_prevalence'], delimiter='\t')
            w.writeheader()
            w.writerows(rows)
        print(f'\nTSV written: {args.out_tsv} ({len(rows)} rows)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
