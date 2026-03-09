#!/bin/bash
##
#SBATCH -J freesurfer_8.1.0
#SBATCH --array=1-4
#SBATCH --time=4-00:00:00
#SBATCH -n 1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH -p russpold
# Outputs ---------------------------------
#SBATCH -o ./log/%x-%A-%a.out
#SBATCH -e ./log/%x-%A-%a.err
#SBATCH --mail-user=logben@stanford.edu
#SBATCH --mail-type=END
# ------------------------------------------

SINGULARITY_IMG="/home/groups/russpold/singularity_images/freesurfer_8.1.0.sif"

# Set FreeSurfer license
export FS_LICENSE=$HOME/license.txt

BIDS="/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402"

# Read subject info from subs_discovery.txt based on array task ID
# Format: subject_id,ses_t1,run_t1,ses_t2,run_t2
line=$(sed -n "${SLURM_ARRAY_TASK_ID}p" subs_discovery.txt)
IFS=',' read -r subject_id ses_t1 run_t1 ses_t2 run_t2 <<< "$line"
subject="sub-${subject_id}"

# Construct T1w path
t1w_path="${BIDS}/${subject}/${ses_t1}/anat/${subject}_${ses_t1}_run-${run_t1}_T1w.nii.gz"

# Compose the command line
if [ -n "$ses_t2" ]; then
    # T2w scan exists
    t2w_path="${BIDS}/${subject}/${ses_t2}/anat/${subject}_${ses_t2}_run-${run_t2}_T2w.nii.gz"
    cmd="singularity exec --bind ${BIDS}:${BIDS},${FS_LICENSE}:${FS_LICENSE} \
${SINGULARITY_IMG} recon-all \
-i ${t1w_path} \
-T2 ${t2w_path} \
-s ${subject} \
-sd ${BIDS}/derivatives/freesurfer_8.1.0 \
-all"
else
    # No T2w scan available
    cmd="singularity exec --bind ${BIDS}:${BIDS},${FS_LICENSE}:${FS_LICENSE} \
${SINGULARITY_IMG} recon-all \
-i ${t1w_path} \
-s ${subject} \
-sd ${BIDS}/derivatives/freesurfer_8.1.0 \
-all"
fi

mkdir -p ${BIDS}/derivatives/freesurfer_8.1.0

# Setup done, run the command
echo Running task ${SLURM_ARRAY_TASK_ID}: ${subject}
echo Commandline: $cmd
eval $cmd
exitcode=$?
