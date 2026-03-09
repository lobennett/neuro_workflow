#!/bin/bash
#SBATCH -J qsiprep_personal
#SBATCH --time=24:00:00
#SBATCH -n 1
#SBATCH --cpus-per-task=8
#SBATCH --mem-per-cpu=8G
#SBATCH -p russpold
#SBATCH -o /scratch/users/logben/personal_bids/code/log/%x-%j.out
#SBATCH -e /scratch/users/logben/personal_bids/code/log/%x-%j.err
#SBATCH --mail-user=logben@stanford.edu
#SBATCH --mail-type=END,FAIL

source /scratch/users/logben/personal_bids/config/setup_env.sh
set -euo pipefail

mkdir -p "${QSIPREP_DERIVS}"
mkdir -p "${WORK_DIR}/qsiprep"

echo "Running QSIPrep 1.1.1"
echo "  BIDS dir: ${BIDS_DIR}"
echo "  Output: ${QSIPREP_DERIVS}"

apptainer run \
    --cleanenv \
    -B "${BIDS_DIR}:/data" \
    -B "${QSIPREP_DERIVS}:/out" \
    -B "${WORK_DIR}/qsiprep:/work" \
    -B "${FS_LICENSE}:/opt/freesurfer/license.txt" \
    "${QSIPREP_IMG}" \
    /data /out participant \
    --participant-label sLogan \
    -w /work \
    --nthreads 8 \
    --mem-mb 64000 \
    --output-resolution 1.5 \
    --skip-bids-validation

exitcode=$?
echo "QSIPrep finished with exit code $exitcode"
exit $exitcode
