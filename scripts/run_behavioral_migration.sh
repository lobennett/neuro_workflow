#!/bin/bash
# Complete behavioral migration workflow
# Run this once all BIDS generation is complete

set -e
cd /home/users/logben/neuro_workflow

RAW_CLEANED="/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data/raw_cleaned"
SOURCEDATA_OAK="/oak/stanford/groups/russpold/data/network_grant/sourcedata"
EXCLUDED_SOURCEDATA_OAK="/oak/stanford/groups/russpold/data/network_grant/excluded_sourcedata"
ARCHIVE_DIR="/oak/stanford/groups/russpold/data/network_grant/_archive_someone_plz_clean/behavioral_data"
MTURK_OAK="/oak/stanford/groups/russpold/data/network_grant/mTurk"

echo "=== Phase 1: Discovery In-Scanner Behavioral ==="
echo "Source: $RAW_CLEANED"
echo "Target: $SOURCEDATA_OAK/behavioral_data"
echo ""
uv run python scripts/rename_behavioral_to_sourcedata.py \
  --input-dir "$RAW_CLEANED" \
  --output-dir "$SOURCEDATA_OAK/behavioral_data" \
  --excluded-output-dir "$EXCLUDED_SOURCEDATA_OAK/behavioral_data" \
  --sample discovery \
  --bids-dir /scratch/users/logben/discovery_bids \
  -v 2>&1 | tee logs/bidsify_logs/behavioral_discovery_$(date +%Y%m%d_%H%M).log

echo ""
echo "=== Phase 2: Validation In-Scanner Behavioral ==="
echo "Source: $RAW_CLEANED"
echo "Target: $SOURCEDATA_OAK/behavioral_data (+ excluded routing)"
echo ""
uv run python scripts/rename_behavioral_to_sourcedata.py \
  --input-dir "$RAW_CLEANED" \
  --output-dir "$SOURCEDATA_OAK/behavioral_data" \
  --excluded-output-dir "$EXCLUDED_SOURCEDATA_OAK/behavioral_data" \
  --sample validation \
  --bids-dir /scratch/users/logben/validation_bids \
  -v 2>&1 | tee logs/bidsify_logs/behavioral_validation_$(date +%Y%m%d_%H%M).log

echo ""
echo "=== Verify irreconcilable entries added to .bidsignore ==="
echo "Expected: 3 entries (s29/ses-01/cuedTS, s300/ses-08/flanker, s1292/ses-04/nBack)"
grep -c "irreconcilable\|s29.*ses-01.*cuedTS\|s300.*ses-08.*flanker\|s1292.*ses-04.*nBack" \
  /scratch/users/logben/validation_bids/.bidsignore 2>/dev/null || echo "Verification failed - check manually"

echo ""
echo "=== Phase 3: Archive Data Migration (mTurk, Out-of-Scanner, Survey) ==="
echo "Archive: $ARCHIVE_DIR"
echo "Targets: mTurk, sourcedata/, excluded_sourcedata/"
echo ""
uv run python scripts/migrate_archive_behavioral_data.py \
  --archive-dir "$ARCHIVE_DIR" \
  --sourcedata-dir "$SOURCEDATA_OAK" \
  --mturk-dir "$MTURK_OAK" \
  --config config/behavioral_session_mapping.json \
  --excluded-sourcedata-dir "$EXCLUDED_SOURCEDATA_OAK" \
  -v 2>&1 | tee logs/bidsify_logs/archive_migration_$(date +%Y%m%d_%H%M).log

echo ""
echo "=== Phase 4: Correspondence Verification ==="
uv run python scripts/check_bids_sourcedata_correspondence.py \
  2>&1 | tee logs/bidsify_logs/correspondence_check_$(date +%Y%m%d_%H%M).log

echo ""
echo "=== Phase 5: Set Directories Read-Only ==="
chmod -R a-w /scratch/users/logben/discovery_bids/
chmod -R a-w /scratch/users/logben/validation_bids/
chmod -R a-w /scratch/users/logben/excluded_bids/

echo "✓ Verified read-only:"
for dir in /scratch/users/logben/discovery_bids /scratch/users/logben/validation_bids /scratch/users/logben/excluded_bids; do
  touch "$dir/.test" 2>&1 | grep -q "Permission denied" && echo "  ✓ $(basename $dir)" || echo "  ✗ $(basename $dir) still writable"
  rm -f "$dir/.test"
done

echo ""
echo "=== All phases complete! ==="
echo "Status:"
ls -lh /scratch/users/logben/discovery_bids/ | head -1
ls -lh /scratch/users/logben/validation_bids/ | head -1
ls -lh /scratch/users/logben/excluded_bids/ | head -1
