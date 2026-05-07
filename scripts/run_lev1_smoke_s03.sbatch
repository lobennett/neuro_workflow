#!/bin/bash
#SBATCH --job-name=lev1_smoke_s03
#SBATCH --partition=russpold
#SBATCH --time=06:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --output=logs/lev1_smoke_s03-%j.out
#SBATCH --error=logs/lev1_smoke_s03-%j.err

# Smoke-test lev1 on sub-s03 across 8 base tasks x 3 spaces (MNI, T1w, fsaverage6).
#
# Prerequisite: compiled discovery exclusions must exist at
#   data/exclusions/discovery/compiled_exclusions.json
# Generate via: uv run neuro-run exclusions compile discovery
set -euo pipefail

cd /home/users/logben/neuro_workflow
mkdir -p logs

module load uv

BIDS_DIR="/scratch/users/logben/discovery_bids"
FMRIPREP_DIR="/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4"
LEV1_OUT="/scratch/users/logben/lev1_discovery"
EXCLUSIONS_FILE="/home/users/logben/neuro_workflow/data/exclusions/discovery/compiled_exclusions.json"

if [[ ! -f "${EXCLUSIONS_FILE}" ]]; then
  echo "ERROR: compiled exclusions not found at ${EXCLUSIONS_FILE}" >&2
  echo "       Run 'uv run neuro-run exclusions compile discovery' first." >&2
  exit 1
fi

TASKS=(cuedTS directedForgetting flanker goNogo nBack shapeMatching spatialTS stopSignal)
# run.py --space choices are {T1w, MNI, surface, fsaverage6, fsLR}; use the
# audit's three-space matrix (MNI volumetric, T1w volumetric, fsaverage6 GIFTI).
SPACES=(MNI T1w fsaverage6)

for task in "${TASKS[@]}"; do
  for space in "${SPACES[@]}"; do
    echo "===== task=${task} space=${space} ====="
    uv run python -m neuro_workflow.analysis.lev1.run \
      --subj-id sub-s03 \
      --task-name "${task}" \
      --bids-dir "${BIDS_DIR}" \
      --fmriprep-dir "${FMRIPREP_DIR}" \
      --results-dir "${LEV1_OUT}" \
      --exclusions-file "${EXCLUSIONS_FILE}" \
      --space "${space}" \
      --within-subject-threshold 1.0 \
      || { echo "FAILED: task=${task} space=${space}"; exit 1; }
  done
done

echo "Smoke run done."
