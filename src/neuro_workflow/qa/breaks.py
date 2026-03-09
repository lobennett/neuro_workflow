from __future__ import annotations

import json
import logging
from argparse import ArgumentParser, Namespace
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment]

from neuro_workflow.qa.base import register_qa

logger = logging.getLogger(__name__)

FEEDBACK_TRIAL_IDS = frozenset([
    "test_feedback", "feedback_block",
    "practice-no-stop-feedback", "practice-stop-feedback",
])

PERFORMANCE_FEEDBACK_STRINGS = frozenset([
    "accuracy", "responding", "slowly", "Remember:", "simply",
])

TASK_NAME_MAPPING = {
    'stop_signal': 'stopSignal',
    'stop_signal_with_flanker': 'stopSignalWFlanker',
    'spatial_switching': 'spatialTS',
    'spatial_task_switching': 'spatialTS',
    'cued_task_switching': 'cuedTS',
    'n_back': 'nBack',
    'directed_forgetting': 'directedForgetting',
    'flanker': 'flanker',
    'go_nogo': 'goNogo',
    'shape_matching': 'shapeMatching',
    'stop_signal_with_directed_forgetting': 'stopSignalWDirectedForgetting',
    'directed_forgetting_with_flanker': 'directedForgettingWFlanker',
    'cued_switching': 'cuedTS',
    'directed_forgetting_with_cued_task_switching': 'directedForgettingWCuedTS',
    'cued_task_switching_with_directed_forgetting': 'directedForgettingWCuedTS',
    'spatial_task_switching_with_cued_task_switching': 'spatialTSWCuedTS',
    'flanker_with_shape_matching': 'flankerWShapeMatching',
    'cued_task_switching_with_flanker': 'cuedTSWFlanker',
    'spatial_task_switching_with_shape_matching': 'spatialTSWShapeMatching',
    'shape_matching_with_spatial_task_switching': 'spatialTSWShapeMatching',
    'n_back_with_shape_matching': 'nBackWShapeMatching',
    'n_back_with_spatial_task_switching': 'nBackWSpatialTS',
    'flanker_with_cued_task_switching': 'cuedTSWFlanker',
    'shape_matching_with_cued_task_switching': 'shapeMatchingWCuedTS',
}


def extract_task_name_from_filename(filename: str) -> Optional[str]:
    base_name = filename.split("__fmri")[0] if "__fmri" in filename else filename.rsplit('.', 1)[0]
    if "_single_task_network" in base_name:
        base_name = base_name.split("_single_task_network")[0]
    elif "task-" in base_name:
        for part in base_name.split('_'):
            if part.startswith("task-"):
                base_name = part.replace("task-", "").replace("-", "_")
                break
    return TASK_NAME_MAPPING.get(base_name, base_name)


def analyze_stimulus_for_performance_feedback(stimulus: Union[str, float, None]) -> tuple:
    if not isinstance(stimulus, str) or (isinstance(stimulus, float) and str(stimulus) == "nan"):
        return [], False
    try:
        if pd is not None and pd.isna(stimulus):
            return [], False
    except (TypeError, ValueError):
        pass
    if not isinstance(stimulus, str):
        return [], False
    indicators = [ind for ind in PERFORMANCE_FEEDBACK_STRINGS if ind.lower() in stimulus.lower()]
    return indicators, len(indicators) > 0


def _extract_feedback_data(file_path: Path) -> List[Dict[str, Any]]:
    subject = file_path.parent.parent.name
    session = file_path.parent.name
    filename = file_path.name

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        logger.error(f"Failed to read {file_path}: {e}")
        return []

    if not {'trial_id', 'stimulus'}.issubset(df.columns):
        return []

    test_mask = df['trial_id'] == 'test_trial'
    if test_mask.any():
        start_idx = test_mask.idxmax()
        df = df.iloc[df.index.get_loc(start_idx):]

    feedback_rows = df[df['trial_id'].isin(FEEDBACK_TRIAL_IDS)]
    if feedback_rows.empty:
        return []

    task_name = extract_task_name_from_filename(filename)

    # Dynamic block numbering
    block_counters: Dict[str, int] = {}
    block_numbers: Dict[int, int] = {}
    for idx, row in feedback_rows.iterrows():
        tid = row['trial_id']
        block_counters[tid] = block_counters.get(tid, 0) + 1
        block_numbers[idx] = block_counters[tid]

    results = []
    for idx, row in feedback_rows.iterrows():
        indicators, has_feedback = analyze_stimulus_for_performance_feedback(row['stimulus'])
        sub_prefix = subject if subject.startswith('sub-') else f"sub-{subject}"
        results.append({
            "subject": sub_prefix,
            "session": session,
            "filename": filename,
            "task_name": task_name,
            "row_index": int(idx),
            "trial_id": row['trial_id'],
            "block_number": block_numbers.get(idx),
            "stimulus_content": str(row['stimulus']) if pd.notna(row['stimulus']) else "",
            "performance_indicators": indicators,
            "has_performance_feedback": has_feedback,
        })
    return results


class BreaksQa:
    name = "breaks"
    description = "Analyze behavioral data for breaks with performance feedback"

    def add_cli_args(self, parser: ArgumentParser) -> None:
        parser.add_argument("--behavioral-dir", required=False, help="Path to behavioral data directory")
        parser.add_argument("--output-dir", default="data", help="Output directory for JSON results")

    def run(self, dataset_name: str, dataset_config: dict, args: Namespace) -> None:
        if pd is None:
            print("Error: 'pandas' required for 'breaks'. Install with: uv pip install -e \".[qa]\"")
            return

        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        beh_dir = Path(getattr(args, "behavioral_dir", None) or "")
        if not beh_dir.is_dir():
            print(f"Error: behavioral directory not found: {beh_dir}")
            return

        files = list(beh_dir.glob("s*/ses-*/*.csv"))
        if not files:
            print(f"No behavioral files found in {beh_dir}")
            return

        logger.info(f"Processing {len(files)} behavioral files...")
        all_results: List[Dict[str, Any]] = []
        for fp in files:
            all_results.extend(_extract_feedback_data(fp))

        if not all_results:
            print("No feedback data extracted")
            return

        output_dir = Path(getattr(args, "output_dir", "data"))
        output_dir.mkdir(parents=True, exist_ok=True)

        # Summary stats
        total_files = len({(r['subject'], r['session'], r['filename']) for r in all_results})
        perf_count = sum(r['has_performance_feedback'] for r in all_results)

        summary = {
            "total_files_processed": total_files,
            "total_feedback_rows": len(all_results),
            "rows_with_performance_feedback": perf_count,
        }

        master = {"break_feedback_analysis": all_results, "summary": summary}
        with open(output_dir / "break_analysis_master.json", "w") as f:
            json.dump(master, f, indent=2)

        perf_results = [r for r in all_results if r['has_performance_feedback']]
        filtered = {"break_with_performance_feedback": perf_results, "summary": summary}
        with open(output_dir / "break_analysis_with_performance_feedback.json", "w") as f:
            json.dump(filtered, f, indent=2)

        print(f"Saved results to {output_dir}")


register_qa(BreaksQa())
