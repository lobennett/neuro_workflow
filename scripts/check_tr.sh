#!/bin/bash
# Check for BOLD scans with unexpected TR counts.
# For each task, computes the expected (mode) TR count from all scans,
# then flags any scan that deviates.
#
# Usage: bash check_tr.sh [bids_dir ...]
# Default: discovery_bids and validation_bids

ml biology fsl

BIDS_DIRS=("$@")
if [ ${#BIDS_DIRS[@]} -eq 0 ]; then
    BIDS_DIRS=(
        /scratch/users/logben/discovery_bids
        /scratch/users/logben/validation_bids
    )
fi

shopt -s nullglob

# Collect task, dim4, filename for all echo-2 BOLD files
tmpfile=$(mktemp)
for bids_dir in "${BIDS_DIRS[@]}"; do
    for f in "$bids_dir"/sub-*/ses-*/func/*echo-2*bold.nii.gz; do
        dim4=$(fslinfo "$f" | awk '$1=="dim4"{print $2}')
        task=$(basename "$f" | sed 's/.*task-\([^_]*\).*/\1/')
        printf "%s\t%s\t%s\n" "$task" "$dim4" "$f" >> "$tmpfile"
    done
done

# Compute mode (most common TR count) per task
echo "=== Expected TR counts per task (mode) ==="
awk -F'\t' '{print $1, $2}' "$tmpfile" | sort | uniq -c | sort -k2,2 -k1,1rn | \
    awk '!seen[$2]++ {printf "  %-40s %s TRs (%d scans)\n", $2, $3, $1}' | sort

echo ""
echo "=== Scans with unexpected TR counts ==="

# For each task, find the mode and flag deviations
awk -F'\t' '{print $1, $2}' "$tmpfile" | sort | uniq -c | sort -k2,2 -k1,1rn | \
    awk '!seen[$2]++ {print $2, $3}' > /tmp/tr_modes.txt

while read -r task expected; do
    awk -F'\t' -v task="$task" -v expected="$expected" \
        '$1 == task && $2 != expected {printf "  %-40s expected=%s actual=%s %s\n", task, expected, $2, $3}' "$tmpfile"
done < /tmp/tr_modes.txt

echo ""
echo "=== Summary ==="
total=$(wc -l < "$tmpfile")
deviant=$(awk -F'\t' '{print $1, $2}' "$tmpfile" | sort | uniq -c | sort -k2,2 -k1,1rn | \
    awk '!seen[$2]++ {print $2, $3}' | while read -r task expected; do
    awk -F'\t' -v task="$task" -v expected="$expected" '$1 == task && $2 != expected' "$tmpfile"
done | wc -l)
echo "  Total echo-2 BOLD files: $total"
echo "  Scans matching expected TR count: $((total - deviant))"
echo "  Scans with unexpected TR count: $deviant"

rm -f "$tmpfile" /tmp/tr_modes.txt
