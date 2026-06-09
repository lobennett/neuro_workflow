#!/bin/bash
# Copy fMRIPrep 25.2.4 FS 7.3.2 recon into the iproc_fs7 FS tree under iProc's
# session-id name (09_009), so iProc uses the better surfaces for bbregister +
# projection. Usage: module load freesurfer first.
set -euo pipefail
SRC=/scratch/users/logben/discovery_bids/derivatives/fmriprep_25.2.4/sourcedata/freesurfer/sub-s10_ses-09
DST=/scratch/users/logben/discovery_bids/derivatives/iproc_fs7/fs/s10/09_009
mkdir -p "$(dirname "$DST")"
[ -e "$DST" ] || cp -a "$SRC" "$DST"
ln -sfn "$FREESURFER_HOME/subjects/fsaverage6" \
  /scratch/users/logben/discovery_bids/derivatives/iproc_fs7/fs/s10/fsaverage6
echo "ingested FS7.3.2 -> $DST"
