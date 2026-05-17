#!/bin/bash
#SBATCH -J synthstrip_recon
#SBATCH -p russpold
#SBATCH -t 14:00:00
#SBATCH --mem=16G
#SBATCH -c 4
#SBATCH -o %x-%j.out
#SBATCH -e %x-%j.err

# Required environment variables (pass via --export or sbatch ENV=...):
#   SUBJ            BIDS subject (e.g. sub-s03)
#   T1W_INPUT       absolute path to subject's preproc T1w NIfTI (1mm)
#   ORIG_SD         original FreeSurfer SUBJECTS_DIR (for fs_subject name lookup)
#   FIX_SD          target FreeSurfer SUBJECTS_DIR for the fixed recon
#                   (e.g. <bids>/derivatives/freesurfer_fix)
#
# Output:
#   $FIX_SD/${SUBJ}_fix/  — full FreeSurfer recon
#   $FIX_SD/${SUBJ}_fix/pre_fix_holes.txt — pre-fix Euler hole counts (.orig.nofix)
#   $FIX_SD/${SUBJ}_fix/post_fix_holes.txt — post-fix Euler hole counts (.orig)

set -euo pipefail
module load biology freesurfer/8.1.0

: "${SUBJ:?SUBJ is required}"
: "${T1W_INPUT:?T1W_INPUT is required}"
: "${FIX_SD:?FIX_SD is required}"

mkdir -p "$FIX_SD"
export SUBJECTS_DIR="$FIX_SD"

WORK=$(mktemp -d)
trap "rm -rf $WORK" EXIT

echo "=== mri_synthstrip on $T1W_INPUT ==="
mri_synthstrip -i "$T1W_INPUT" -o "$WORK/brain_synthstrip.nii.gz"

echo "=== recon-all (FreeSurfer 8.1.0) ==="
recon-all -all \
    -i "$WORK/brain_synthstrip.nii.gz" \
    -subjid "${SUBJ}_fix" \
    -sd "$FIX_SD"

OUT="$FIX_SD/${SUBJ}_fix"

echo "=== pre-fix Euler hole counts (.orig.nofix) ==="
for hemi in lh rh; do
    line=$(mris_euler_number "$OUT/surf/${hemi}.orig.nofix" 2>/dev/null | grep -oE '[0-9]+ holes')
    echo "$hemi $line"
done > "$OUT/pre_fix_holes.txt"

echo "=== post-fix Euler hole counts (.orig) ==="
for hemi in lh rh; do
    line=$(mris_euler_number "$OUT/surf/${hemi}.orig" 2>/dev/null | grep -oE '[0-9]+ holes')
    echo "$hemi $line"
done > "$OUT/post_fix_holes.txt"

echo "DONE: $OUT"
cat "$OUT/pre_fix_holes.txt"
echo "---"
cat "$OUT/post_fix_holes.txt"
