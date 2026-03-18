#!/bin/bash
# Verify BIDS generation completion and prepare for next phases

set -e

BIDS_DIRS=(
  "/scratch/users/logben/discovery_bids"
  "/scratch/users/logben/validation_bids"
  "/scratch/users/logben/excluded_bids"
)

EXPECTED_SUBJECTS=(
  "5"    # discovery
  "41"   # validation
  "11"   # excluded
)

echo "=== BIDS Completion Verification ==="
echo ""

for i in 0 1 2; do
  BIDS_DIR="${BIDS_DIRS[$i]}"
  EXPECTED="${EXPECTED_SUBJECTS[$i]}"
  SAMPLE=$(basename "$BIDS_DIR" | sed 's/_bids//')

  if [ ! -d "$BIDS_DIR" ]; then
    echo "✗ $SAMPLE: Directory not found"
    continue
  fi

  # Count subjects
  ACTUAL=$(ls -d "$BIDS_DIR"/sub-* 2>/dev/null | wc -l)

  if [ "$ACTUAL" -eq "$EXPECTED" ]; then
    echo "✓ $SAMPLE: $ACTUAL subjects complete"

    # Check for old duration-based .bidsignore entries
    if grep -iq "non-4D\|below threshold\|scan duration\|3D" "$BIDS_DIR/.bidsignore" 2>/dev/null; then
      echo "  ⚠ WARNING: Found old duration-based .bidsignore entries"
    else
      echo "  ✓ No old duration-based .bidsignore entries"
    fi

    # Count .bidsignore entries
    BIDSIGNORE_COUNT=$(wc -l < "$BIDS_DIR/.bidsignore" 2>/dev/null || echo "0")
    echo "  ✓ .bidsignore entries: $BIDSIGNORE_COUNT"

  elif [ "$ACTUAL" -lt "$EXPECTED" ]; then
    echo "⏳ $SAMPLE: In progress ($ACTUAL/$EXPECTED subjects)"
  else
    echo "⚠ $SAMPLE: More subjects than expected ($ACTUAL vs $EXPECTED)"
  fi
done

echo ""
echo "=== Next Steps ==="
echo "1. Wait for validation_bids to complete (41/41 subjects)"
echo "2. Run: uv run python scripts/rename_behavioral_to_sourcedata.py ... (discovery)"
echo "3. Run: uv run python scripts/rename_behavioral_to_sourcedata.py ... (validation)"
echo "4. Run: uv run python scripts/migrate_archive_behavioral_data.py ..."
echo "5. Run: uv run python scripts/check_bids_sourcedata_correspondence.py"
echo "6. Run: chmod -R a-w /scratch/users/logben/{discovery,validation,excluded}_bids/"
echo "7. Final commit"
