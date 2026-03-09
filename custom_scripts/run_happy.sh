#!/bin/bash
#SBATCH --job-name=happy
#SBATCH --output=./logs/happy_%A_%a.out
#SBATCH --error=./logs/happy_%A_%a.err
#SBATCH --time=00:10:00
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem-per-cpu=2G
#SBATCH --partition=russpold,normal

set -euo pipefail

# Ensure logs directory exists
mkdir -p "./logs"

# --- Input validation ---
LIST_FILE="${1:?ERROR: Provide the scan list file as the first argument}"

if [ ! -f "$LIST_FILE" ]; then
    echo "ERROR: List file not found: $LIST_FILE" >&2
    exit 1
fi

if [ -z "${SLURM_ARRAY_TASK_ID:-}" ]; then
    echo "ERROR: SLURM_ARRAY_TASK_ID is not set. Submit with sbatch --array=..." >&2
    exit 1
fi

LINE="$(sed -n "${SLURM_ARRAY_TASK_ID}p" "$LIST_FILE")"

if [ -z "$LINE" ]; then
    echo "ERROR: No data at line ${SLURM_ARRAY_TASK_ID} in ${LIST_FILE}" >&2
    exit 1
fi

# --- Parse columns ---
# PHYS_JSON (column 4) is parsed but not passed to happy;
# rapidtide reads the physio JSON sidecar automatically from the TSV path.
read -r BOLD_FILE BOLD_JSON PHYS_TSV PHYS_JSON OUT_FILE <<< "$LINE"

OUT_PREFIX="${OUT_FILE%.nii.gz}"

# --- Runtime skip check ---
if compgen -G "${OUT_PREFIX}_"* > /dev/null 2>&1; then
    echo "SKIPPED: Output already exists for ${BOLD_FILE}"
    echo "  Output prefix: ${OUT_PREFIX}"
    exit 0
fi

# --- Setup ---
mkdir -p "$(dirname "$OUT_PREFIX")"

CONTAINER="/home/groups/russpold/singularity_images/rapidtide_3.1.8"

if [ ! -e "$CONTAINER" ]; then
    echo "ERROR: Singularity container not found: $CONTAINER" >&2
    exit 1
fi

# --- Run ---
echo "========================================"
echo "Task ID:    ${SLURM_ARRAY_TASK_ID}"
echo "Input BOLD: ${BOLD_FILE}"
echo "Output:     ${OUT_PREFIX}"
echo "Start time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

START_SECONDS=$SECONDS

set +e
singularity exec "$CONTAINER" happy \
    --cardiacfile "${PHYS_TSV}:cardiac" \
    --temporalregression \
    "$BOLD_FILE" \
    "$BOLD_JSON" \
    "$OUT_PREFIX"
EXIT_CODE=$?
set -e
ELAPSED=$(( SECONDS - START_SECONDS ))

echo "========================================"
if [ "$EXIT_CODE" -eq 0 ]; then
    echo "SUCCESS: ${BOLD_FILE}"
else
    echo "FAILED (exit code ${EXIT_CODE}): ${BOLD_FILE}"
fi
echo "Elapsed:    $(( ELAPSED / 3600 ))h $(( (ELAPSED % 3600) / 60 ))m $(( ELAPSED % 60 ))s"
echo "End time:   $(date '+%Y-%m-%d %H:%M:%S')"
echo "========================================"

exit "$EXIT_CODE"
