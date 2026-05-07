#!/bin/bash
#SBATCH --job-name=lev1_smoke_s03
#SBATCH --partition=russpold
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/lev1_smoke_s03-%j.out
#SBATCH --error=logs/lev1_smoke_s03-%j.err

# Smoke-test lev1 on sub-s03 for ONE base task in MNI space.
# Iterate alphabetically through tasks, gating each on the prior succeeding,
# rather than running 24 combos at once and burning compute on cascading failures.
#
# Usage:
#   sbatch scripts/run_lev1_smoke_s03.sbatch <task-name>
# Example:
#   sbatch scripts/run_lev1_smoke_s03.sbatch cuedTS
#
# Prerequisite: compiled discovery exclusions must exist at
#   ~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json
# Generate via: uv run neuro-run exclusions compile discovery
set -euo pipefail

cd /home/users/logben/neuro_workflow
mkdir -p logs

module load uv

if [[ $# -lt 1 ]]; then
  echo "Usage: sbatch $0 <task-name>" >&2
  echo "Tasks: cuedTS directedForgetting flanker goNogo nBack shapeMatching spatialTS stopSignal" >&2
  exit 1
fi
TASK="$1"

BIDS_DIR="/scratch/users/logben/discovery_bids"
FMRIPREP_DIR="/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4"
LEV1_OUT="/scratch/users/logben/lev1_discovery"
EXCLUSIONS_FILE="${HOME}/.neuro_workflow/exclusions/discovery/compiled_exclusions.json"

if [[ ! -f "${EXCLUSIONS_FILE}" ]]; then
  echo "ERROR: compiled exclusions not found at ${EXCLUSIONS_FILE}" >&2
  echo "       Run 'uv run neuro-run exclusions compile discovery' first." >&2
  exit 1
fi

echo "===== sub-s03 task=${TASK} space=MNI ====="
uv run python -m neuro_workflow.analysis.lev1.run \
  --subj-id sub-s03 \
  --task-name "${TASK}" \
  --bids-dir "${BIDS_DIR}" \
  --fmriprep-dir "${FMRIPREP_DIR}" \
  --results-dir "${LEV1_OUT}" \
  --exclusions-file "${EXCLUSIONS_FILE}" \
  --space MNI \
  --mni-template MNI152NLin6Asym \
  --mni-res 2 \
  --within-subject-threshold 1.0

echo "Done: sub-s03 task=${TASK} space=MNI"
