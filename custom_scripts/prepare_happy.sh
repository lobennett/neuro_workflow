#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BIDS_DIR="/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402"
DERIV_DIR="${BIDS_DIR}/derivatives/happy"

FULL_LIST="${SCRIPT_DIR}/complete_scan_list.txt"
CLEAN_LIST="${SCRIPT_DIR}/clean_scan_list.txt"
PENDING_LIST="${SCRIPT_DIR}/pending_scan_list.txt"
MISSING_LOG="${SCRIPT_DIR}/missing_files.log"
SKIPPED_LOG="${SCRIPT_DIR}/skipped_complete.log"

# Initialize/Clear files
> "$FULL_LIST"
> "$CLEAN_LIST"
> "$PENDING_LIST"
> "$MISSING_LOG"
> "$SKIPPED_LOG"

# Counters
total=0
missing=0
complete=0
pending=0

# Loop through subjects and sessions
for sub_dir in "${BIDS_DIR}"/sub-s*; do
    [ -d "$sub_dir" ] || continue
    sub_id="$(basename "$sub_dir")"

    for ses_dir in "${sub_dir}"/ses-*; do
        [ -d "$ses_dir" ] || continue
        ses_id="$(basename "$ses_dir")"
        func_dir="${ses_dir}/func"

        [ -d "$func_dir" ] || continue

        # Output directory mirrors sub/ses structure in derivatives/happy
        output_func_dir="${DERIV_DIR}/${sub_id}/${ses_id}/func"

        for nifti in "${func_dir}"/*_task-rest_*_echo-*_bold.nii.gz; do
            [ -e "$nifti" ] || continue
            total=$((total + 1))

            # 1. Nifti
            row_nifti="$nifti"

            # 2. JSON for the echo
            json_path="${nifti%.nii.gz}.json"
            if [ -f "$json_path" ]; then
                row_json="$json_path"
            else
                row_json="MISSING"
            fi

            # Identify the run-level prefix for physio
            base_prefix="$(basename "$nifti" | sed 's/_echo-[0-9].*//')"

            # 3. Physio TSV
            phys_tsv="${func_dir}/${base_prefix}_recording-cardiac_physio.tsv.gz"
            if [ -f "$phys_tsv" ]; then
                row_tsv="$phys_tsv"
            else
                row_tsv="MISSING"
            fi

            # 4. Physio JSON
            phys_json="${func_dir}/${base_prefix}_recording-cardiac_physio.json"
            if [ -f "$phys_json" ]; then
                row_pjson="$phys_json"
            else
                row_pjson="MISSING"
            fi

            # 5. Output filepath
            filename="$(basename "$nifti")"
            row_output="${output_func_dir}/${filename}"

            # Construct the 5-column row
            current_row="${row_nifti} ${row_json} ${row_tsv} ${row_pjson} ${row_output}"

            # Always add to the master list
            echo "$current_row" >> "$FULL_LIST"

            # Check for missing data
            if [[ "$row_json" == "MISSING" || "$row_tsv" == "MISSING" || "$row_pjson" == "MISSING" ]]; then
                echo "MISSING DATA: $current_row" >> "$MISSING_LOG"
                missing=$((missing + 1))
                continue
            fi

            # Add to clean list (all inputs present)
            echo "$current_row" >> "$CLEAN_LIST"

            # Check if output already exists (skip if done)
            out_prefix="${row_output%.nii.gz}"
            if compgen -G "${out_prefix}_"* > /dev/null 2>&1; then
                echo "$current_row" >> "$SKIPPED_LOG"
                complete=$((complete + 1))
            else
                echo "$current_row" >> "$PENDING_LIST"
                pending=$((pending + 1))
            fi
        done
    done
done

echo "-----------------------------------------------"
echo "Processing Finished."
echo ""
echo "  Total scans found:   $total"
echo "  Missing data:        $missing"
echo "  Already complete:    $complete"
echo "  Pending processing:  $pending"
echo ""
echo "  Master List:     $FULL_LIST"
echo "  Clean List:      $CLEAN_LIST"
echo "  Pending List:    $PENDING_LIST"
echo "  Missing Log:     $MISSING_LOG"
echo "  Skipped Log:     $SKIPPED_LOG"
echo "-----------------------------------------------"

if [ "$pending" -gt 0 ]; then
    echo ""
    echo "To submit SLURM jobs, run:"
    echo "  sbatch --array=1-${pending} ${SCRIPT_DIR}/run_happy.sh ${PENDING_LIST}"
else
    echo ""
    echo "No pending scans to process."
fi
