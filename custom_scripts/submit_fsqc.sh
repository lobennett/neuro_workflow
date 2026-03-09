#!/bin/bash
#SBATCH --job-name=fsqc_validation
#SBATCH --output=logs/fsqc_validation_%j.out
#SBATCH --error=logs/fsqc_validation_%j.err
#SBATCH --time=2-00:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=4
#SBATCH --partition=russpold,normal

# --- CONFIGURATION ---

# 1. INPUT: The PARENT directory containing the 'sub-sXX' folders
SUBJECTS_DIR="/oak/stanford/groups/russpold/data/network_grant/validation_BIDS/derivatives/fmriprep_24.1.0rc2/sourcedata/freesurfer"

# 2. OUTPUT: Where to save the QC reports
OUTPUT_DIR="/oak/stanford/groups/russpold/data/network_grant/validation_BIDS/derivatives/fsqc"

# 3. SUBJECTS LIST
SUBJECTS_FILE="/home/users/logben/network_glm/data/subs_validation.txt"

# 4. CONTAINER IMAGE
IMG="/home/groups/russpold/singularity_images/fsqcdocker_2.1.4.sif"

# --- PREPARATION ---

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Parse subject list and ensure 'sub-' prefix matches directory structure
# This reads your text file (e.g., "s03") and converts it to "sub-s03" for the command
SUBJECTS_LIST=""
while read -r line; do
    # Strip whitespace
    clean_sub=$(echo "$line" | xargs)

    # If line is not empty
    if [[ ! -z "$clean_sub" ]]; then
        # Check if it already has 'sub-' prefix, if not, add it
        if [[ "$clean_sub" != sub-* ]]; then
            clean_sub="sub-$clean_sub"
        fi
        SUBJECTS_LIST="$SUBJECTS_LIST $clean_sub"
    fi
done < "$SUBJECTS_FILE"

echo "Running fsqc on the following subjects:"
echo "$SUBJECTS_LIST"

# --- EXECUTION ---

# 1. Clear display variables to avoid conflicts
export SINGULARITYENV_DISPLAY=""
export SINGULARITYENV_LIBGL_ALWAYS_INDIRECT=1
export SINGULARITYENV_MESA_GL_VERSION_OVERRIDE=3.3

# 2. Run Singularity
# ADDED: --writable-tmpfs to allow Xvfb to create sockets in /tmp
singularity exec \
    --cleanenv \
    --writable-tmpfs \
    -B "$SUBJECTS_DIR":/data \
    -B "$OUTPUT_DIR":/out \
    "$IMG" \
    xvfb-run -a -s "-screen 0 1024x768x24 -ac +extension GLX +render -noreset" \
    /app/fsqc/run_fsqc \
    --subjects_dir /data \
    --output_dir /out \
    --subjects $SUBJECTS_LIST \
    --screenshots-html \
    --surfaces-html \
    --skullstrip-html \
    --fornix-html \
    --outlier

echo "Done!"
