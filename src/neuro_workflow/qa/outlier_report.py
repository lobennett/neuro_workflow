"""Outlier report QA command.

Ports run_network.py, run_report.py, and plotting_functions.py into the QA framework.
Generates VIF + outlier analysis figures and summary CSVs.
"""
from __future__ import annotations

import gc
import json
import logging
import os
import re
import shutil
from argparse import ArgumentParser, Namespace
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import img2pdf
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import seaborn as sns
    from matplotlib.cm import get_cmap
    from matplotlib.colorbar import ColorbarBase
    from matplotlib.colors import Normalize
    from matplotlib.gridspec import GridSpec
    from nilearn import datasets, plotting
    from nilearn.image import load_img
except ImportError:
    plt = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa

logger = logging.getLogger(__name__)


# --- BIDS parsing ---

def parse_bids_entities(path: str) -> Dict[str, Optional[str]]:
    filename = os.path.basename(path)
    patterns = {
        'subject': re.compile(r'sub-s([^_]+)'),
        'session': re.compile(r'ses-([^_]+)'),
        'run': re.compile(r'run-([^_]+)'),
        'task': re.compile(r'task-([^_]+)'),
        'contrast': re.compile(r'contrast-(.+?)_(?:rtmodel-[^_]+_)?stat-'),
    }
    entities: Dict[str, Optional[str]] = {key: None for key in patterns}
    entities['sub_ses_key'] = None
    for key, pattern in patterns.items():
        match = pattern.search(filename)
        if match:
            entities[key] = match.group(1)
    if entities['subject'] and entities['session']:
        entities['sub_ses_key'] = f'sub-s{entities["subject"]}_ses-{entities["session"]}'
    return entities


# --- Data collection ---

def load_exclusions(exclusions_file: str) -> Set[str]:
    if not os.path.exists(exclusions_file):
        raise FileNotFoundError(f'Exclusions file not found: {exclusions_file}')
    with open(exclusions_file) as f:
        data = json.load(f)
    excluded = set()
    for key in ('fmriprep_exclusions', 'behavioral_exclusions'):
        for exc in data.get(key, []):
            excluded.add(f"{exc['subject']}_{exc['session']}_{exc['task']}_{exc['run']}")
    return excluded


def is_scan_excluded(path: str, exclusions: Set[str]) -> bool:
    if not exclusions:
        return False
    ent = parse_bids_entities(path)
    if not all(ent.get(k) for k in ['subject', 'session', 'task', 'run']):
        return False
    key = f"sub-s{ent['subject']}_ses-{ent['session']}_task-{ent['task']}_run-{ent['run']}"
    return key in exclusions


def find_nifti_files(base_dirs: List[str]) -> List[str]:
    all_files = []
    for base_dir in base_dirs:
        pattern = os.path.join(base_dir, 'sub-s*', 'task-*', 'indiv_contrasts', '*stat-effect-size.nii.gz')
        from glob import glob as gglob
        all_files.extend(gglob(pattern))
    return sorted(all_files)


def extract_vif_from_csv(csv_path: str) -> Dict[str, float]:
    try:
        df = pd.read_csv(csv_path)
        return dict(zip(df['contrast'], df['VIF']))
    except Exception:
        return {}


def find_vif_files(base_dirs: List[str]) -> Dict[str, Dict[str, float]]:
    from glob import glob as gglob
    all_vif = {}
    for base_dir in base_dirs:
        pattern = os.path.join(base_dir, 'sub-s*', 'task-*', 'quality_control', '*_desc-contrastVIFs.csv')
        for vif_file in gglob(pattern):
            ent = parse_bids_entities(vif_file)
            if ent['sub_ses_key'] and ent['task']:
                if ent['run']:
                    key = f'{ent["sub_ses_key"]}_run-{ent["run"]}_{ent["task"]}'
                else:
                    key = f'{ent["sub_ses_key"]}_{ent["task"]}'
                all_vif[key] = extract_vif_from_csv(vif_file)
    return all_vif


def group_paths_by_filename_pattern(file_paths: List[str]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = defaultdict(list)
    for path in file_paths:
        filename = os.path.basename(path)
        pattern = re.sub(r'sub-s[^_]+', 'sub-sXXX', filename)
        pattern = re.sub(r'ses-[^_]+', 'ses-XX', pattern)
        pattern = re.sub(r'run-[^_]+', 'run-X', pattern)
        grouped[pattern].append(path)
    return dict(sorted(grouped.items()))


def get_contrast_vif_labels(vif_data, nifti_paths, contrast_name):
    labels = []
    for path in nifti_paths:
        ent = parse_bids_entities(path)
        label = '(vif=?)'
        if ent['sub_ses_key'] and ent['task'] and ent['run']:
            vif_key = f'{ent["sub_ses_key"]}_run-{ent["run"]}_{ent["task"]}'
            if vif_key not in vif_data:
                vif_key = f'{ent["sub_ses_key"]}_{ent["task"]}'
            if vif_key in vif_data:
                contrast_only = ent.get('contrast', '')
                if contrast_only in vif_data[vif_key]:
                    label = f'(vif={vif_data[vif_key][contrast_only]:.2f})'
        labels.append(label)
    return labels


# --- Outlier computation ---

def get_outlier_voxel_percentages(nifti_paths, n_std=2):
    try:
        data = np.array([load_img(p).get_fdata() for p in nifti_paths])
    except Exception:
        return [0.0] * len(nifti_paths)
    mean = np.mean(data, axis=0)
    std = np.std(data, axis=0)
    lower = mean - n_std * std
    upper = mean + n_std * std
    epsilon = 1e-6
    valid_mask = np.isfinite(std) & (std > epsilon)
    percentages = []
    for subj_data in data:
        mask = np.isfinite(subj_data) & valid_mask
        outliers = (subj_data < lower) | (subj_data > upper)
        valid = np.sum(mask)
        percentages.append(100 * np.sum(outliers & mask) / valid if valid > 0 else 0.0)
    return percentages


def get_symmetric_percentile_bounds(nifti_paths, percentile=98):
    all_data = np.concatenate([load_img(p).get_fdata().ravel() for p in nifti_paths])
    all_data = all_data[np.isfinite(all_data)]
    if len(all_data) == 0:
        return 1.0
    high = np.percentile(np.abs(all_data), percentile)
    return high if high > 0 else 1.0


# --- Plotting ---

def _plot_subject_grid(subject_labels, vif_labels, nifti_paths, outlier_pcts, mni_mask, contrast_name, vmax, vmin, cbar_title, n_std):
    subject_sessions = {}
    for i, label in enumerate(subject_labels):
        match = re.match(r'(sub-s[^_\s]+)', label)
        if match:
            sid = match.group(1)
            subject_sessions.setdefault(sid, []).append(i)
    unique = sorted(subject_sessions)
    nrows = len(unique)
    ncols = max(len(v) for v in subject_sessions.values()) if unique else 1
    fig = plt.figure(figsize=(ncols * 2.0, nrows * 1.6 + 1.5))
    gs = GridSpec(nrows, ncols, figure=fig, wspace=1.0, hspace=0.4)
    fs = 9 if nrows <= 20 else 7 if nrows <= 50 else 5
    for row, sid in enumerate(unique):
        for col, idx in enumerate(subject_sessions[sid]):
            ax = fig.add_subplot(gs[row, col])
            display = plotting.plot_stat_map(nifti_paths[idx], display_mode='z', cut_coords=[5], colorbar=False, vmax=vmax, vmin=vmin, title=None, axes=ax, bg_img=None, annotate=False)
            display.add_contours(mni_mask, colors='greenyellow', linewidths=1.5)
            ax.set_title(f'{subject_labels[idx]}\n({outlier_pcts[idx]:.1f}% > {n_std}SD)\n{vif_labels[idx]}', fontsize=fs, pad=4)
    cbar_ax = fig.add_axes([0.92, 0.25, 0.015, 0.5])
    norm = Normalize(vmin=vmin, vmax=vmax)
    ColorbarBase(cbar_ax, cmap=get_cmap('cold_hot'), norm=norm).set_label(cbar_title, fontsize=10)
    fig.suptitle(contrast_name, fontsize=14, y=0.95 if nrows <= 5 else 0.93 if nrows <= 15 else 0.91)
    return fig


def _build_outlier_df(labels, pcts, contrast, task=None, contrast_only=None, sessions=None, vif_labels=None):
    data = {'subject_label': labels, 'image_outlier_percentage': pcts, 'contrast_name': [contrast] * len(labels)}
    if task:
        data['task_name'] = [task] * len(labels)
    if contrast_only:
        data['contrast_only'] = [contrast_only] * len(labels)
    if sessions:
        data['session_id'] = sessions
    if vif_labels:
        vifs = []
        for vl in vif_labels:
            m = re.search(r'\(vif=([\d\.]+)\)', vl)
            vifs.append(float(m.group(1)) if m else np.nan)
        data['VIF'] = vifs
    return pd.DataFrame(data)


def combine_pngs_to_pdf(png_files, pdf_path):
    if not png_files:
        return
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, 'wb') as f:
        f.write(img2pdf.convert([str(p) for p in png_files]))


def summarize_outlier_percentages(df_list, output_dir, temp_dir=None):
    if not df_list:
        return []
    if temp_dir is None:
        temp_dir = output_dir
    os.makedirs(output_dir, exist_ok=True)
    combined = pd.concat(df_list, ignore_index=True)

    fig1, ax1 = plt.subplots(figsize=(8, 5))
    sns.histplot(combined['image_outlier_percentage'], bins=30, kde=False, ax=ax1)
    ax1.set_title('Distribution of Outlier Percentages (All)')
    path1 = os.path.join(temp_dir, 'outlier_percentage_dist_all.png')
    fig1.savefig(path1, dpi=300)
    plt.close(fig1)

    g = sns.displot(combined, x='image_outlier_percentage', col='contrast_name', col_wrap=5, bins=20, facet_kws={'sharex': False, 'sharey': False}, height=3, aspect=1.2)
    path2 = os.path.join(temp_dir, 'outlier_percentage_dist_by_image.png')
    g.savefig(path2, dpi=300)
    plt.close(g.fig)

    combined.to_csv(os.path.join(output_dir, 'percent_outlier_data.csv'), index=False)
    return [path1, path2]


# --- Main pipeline ---

def make_input_dicts(base_dirs, exclusions):
    nifti_files = find_nifti_files(base_dirs)
    if exclusions:
        nifti_files = [f for f in nifti_files if not is_scan_excluded(f, exclusions)]
    vif_data = find_vif_files(base_dirs)
    grouped = group_paths_by_filename_pattern(nifti_files)
    result = []
    for pattern, paths in grouped.items():
        if not paths:
            continue
        ent = parse_bids_entities(paths[0])
        task, contrast = ent.get('task'), ent.get('contrast')
        if not task or not contrast:
            continue
        sorted_paths = sorted(paths)
        vif_labels = get_contrast_vif_labels(vif_data, sorted_paths, contrast)
        path_ents = [parse_bids_entities(p) for p in sorted_paths]
        image_labels = [f'sub-s{e["subject"]}_ses-{e["session"]}_run-{e["run"]}' for e in path_ents]
        result.append({
            'main_title': f'{task}_{contrast}',
            'nifti_paths': sorted_paths,
            'image_labels': image_labels,
            'vif_labels': vif_labels,
            'data_type_label': 'Contrast Estimate',
            'task_name': task,
            'contrast_name': contrast,
            'session_ids': [e.get('session') for e in path_ents],
        })
    return result


def process_contrasts(base_dirs, output_dir, exclusions_file, n_std=3):
    exclusions = load_exclusions(exclusions_file) if exclusions_file else set()
    dicts_list = make_input_dicts(base_dirs, exclusions)
    if not dicts_list:
        print('No data found')
        return

    temp_dir = os.path.join(output_dir, 'temp')
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(temp_dir)

    png_files = []
    outlier_dfs = []
    mni_mask = datasets.load_mni152_brain_mask()

    for d in dicts_list:
        try:
            pcts = get_outlier_voxel_percentages(d['nifti_paths'], n_std=n_std)
            vmax = get_symmetric_percentile_bounds(d['nifti_paths'])
            fig = _plot_subject_grid(d['image_labels'], d['vif_labels'], d['nifti_paths'], pcts, mni_mask, d['main_title'], vmax, -vmax, d['data_type_label'], n_std)
            png_path = os.path.join(temp_dir, f'{d["main_title"]}_slice_grid.png')
            fig.savefig(png_path, dpi=300, bbox_inches='tight')
            plt.close(fig)
            del fig
            gc.collect()
            png_files.append(png_path)
            outlier_dfs.append(_build_outlier_df(d['image_labels'], pcts, d['main_title'], d.get('task_name'), d.get('contrast_name'), d.get('session_ids'), d['vif_labels']))
        except Exception as e:
            print(f'{d["main_title"]} error: {e}')

    summary_paths = summarize_outlier_percentages(outlier_dfs, output_dir, temp_dir)
    combine_pngs_to_pdf(summary_paths + sorted(png_files), os.path.join(output_dir, 'outlier_analysis.pdf'))
    shutil.rmtree(temp_dir)
    print(f'Outlier report saved to {output_dir}')


class OutlierReportQa:
    name = "outlier-report"
    description = "VIF + outlier analysis with figures and summary CSVs"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--lev1-dirs", nargs="+", help="First-level analysis output directories")
        parser.add_argument("--exclusions-file", default=None, help="JSON file with scan exclusions")
        parser.add_argument("--output-dir", default=None, help="Output directory for report")
        parser.add_argument("--n-std", type=float, default=3, help="Number of SDs for outlier threshold")

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if plt is None:
            print("Error: QA dependencies required. Install with: uv pip install -e \".[qa]\"")
            return
        base_dirs = getattr(args, "lev1_dirs", None) or []
        if not base_dirs:
            print("Error: --lev1-dirs is required for outlier-report")
            return
        output_dir = getattr(args, "output_dir", None) or f"{dataset_config['bids_dir']}/derivatives/outlier_report"
        exclusions_file = getattr(args, "exclusions_file", None)
        n_std = getattr(args, "n_std", 3)
        process_contrasts(base_dirs, output_dir, exclusions_file, n_std)


register_qa(OutlierReportQa())
