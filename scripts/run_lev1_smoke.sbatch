#!/bin/bash
#SBATCH --job-name=lev1_smoke
#SBATCH --partition=russpold
#SBATCH --time=02:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/lev1_smoke_%x_%j.out
#SBATCH --error=logs/lev1_smoke_%x_%j.err

# Smoke-test lev1 on ONE subject × ONE base task in MNI space.
# Iterate by submitting per (subject, task) so failures are isolated and
# compute isn't wasted on cascades.
#
# Usage:
#   sbatch scripts/run_lev1_smoke.sbatch <subject> <task>
# Example:
#   sbatch scripts/run_lev1_smoke.sbatch sub-s10 cuedTS
#
# Prerequisite: compiled discovery exclusions must exist at
#   ~/.neuro_workflow/exclusions/discovery/compiled_exclusions.json
# Generate via: uv run neuro-run exclusions compile discovery
set -euo pipefail

cd /home/users/logben/neuro_workflow
mkdir -p logs

module load uv

if [[ $# -lt 2 ]]; then
  echo "Usage: sbatch $0 <subject> <task>" >&2
  echo "  subject: e.g. sub-s03, sub-s10, sub-s19, sub-s29, sub-s43" >&2
  echo "  task:    cuedTS|directedForgetting|flanker|goNogo|nBack|shapeMatching|spatialTS|stopSignal" >&2
  exit 1
fi
SUBJECT="$1"
TASK="$2"

BIDS_DIR="/scratch/users/logben/discovery_bids"
FMRIPREP_DIR="/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4"
LEV1_OUT="/scratch/users/logben/lev1_discovery"
EXCLUSIONS_FILE="${HOME}/.neuro_workflow/exclusions/discovery/compiled_exclusions.json"

if [[ ! -f "${EXCLUSIONS_FILE}" ]]; then
  echo "ERROR: compiled exclusions not found at ${EXCLUSIONS_FILE}" >&2
  echo "       Run 'uv run neuro-run exclusions compile discovery' first." >&2
  exit 1
fi

echo "===== ${SUBJECT} task=${TASK} space=MNI ====="
uv run python -m neuro_workflow.analysis.lev1.run \
  --subj-id "${SUBJECT}" \
  --task-name "${TASK}" \
  --bids-dir "${BIDS_DIR}" \
  --fmriprep-dir "${FMRIPREP_DIR}" \
  --results-dir "${LEV1_OUT}" \
  --exclusions-file "${EXCLUSIONS_FILE}" \
  --space MNI \
  --mni-template MNI152NLin6Asym \
  --mni-res 2 \
  --within-subject-threshold 1.0

echo "Done: ${SUBJECT} task=${TASK} space=MNI"
