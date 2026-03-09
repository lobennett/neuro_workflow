#!/usr/bin/env python3
"""
Identifies event files with non-monotonically increasing onset columns
and finds the index where they become monotonic for trimming purposes.
"""

from pathlib import Path
import pandas as pd
from typing import Optional

# PATHS
DISCOVERY_BIDS = Path("/oak/stanford/groups/russpold/data/network_grant/discovery_BIDS_20250402/")
VALIDATION_BIDS = Path("/oak/stanford/groups/russpold/data/network_grant/validation_BIDS/")


def find_monotonic_point(onset_series: pd.Series) -> Optional[int]:
    """
    Find the index where the onset series becomes monotonically increasing.
    
    Args:
        onset_series: Pandas series of onset times
        
    Returns:
        Index where series becomes monotonic, or None if never monotonic
    """
    for i in range(len(onset_series)):
        # Check if the series from index i onwards is monotonically increasing
        if onset_series.iloc[i:].is_monotonic_increasing:
            return i
    return None

def main() -> int:
    """
    Main function to identify non-monotonic event files and find trim points.
    
    Returns:
        Exit code (0 for success)
    """
    # Collect all behavioral files
    discovery_files = list(DISCOVERY_BIDS.glob("sub-s*/ses-*/func/*event*.tsv"))
    validation_files = list(VALIDATION_BIDS.glob("sub-s*/ses-*/func/*event*.tsv"))
    all_files = discovery_files + validation_files

    print(f"Found {len(all_files)} event files total")
    print("\nNon-monotonic event files and their trim points:")
    print("=" * 60)
    
    non_monotonic_files = []
    
    for file_path in all_files:
        try:
            df = pd.read_csv(file_path, sep='\t')
            
            # Check if onset column exists
            if 'onset' not in df.columns:
                print(f"WARNING: {file_path.name} - no 'onset' column found")
                continue
                
            # Check if monotonically increasing
            if not df['onset'].is_monotonic_increasing:
                monotonic_index = find_monotonic_point(df['onset'])
                non_monotonic_files.append({
                    'file': file_path.name,
                    'path': str(file_path),
                    'trim_index': monotonic_index,
                    'total_rows': len(df)
                })
                
                print(f"{file_path.name}")
                print(f"  Path: {file_path}")
                print(f"  Trim index: {monotonic_index}")
                print(f"  Total rows: {len(df)}")
                if monotonic_index is not None:
                    print(f"  Rows to keep: {len(df) - monotonic_index}")
                print()
                
        except Exception as e:
            print(f"ERROR reading {file_path.name}: {e}")
    
    print(f"\nSummary: {len(non_monotonic_files)} files with non-monotonic onsets")
    
    return 0


if __name__ == '__main__':
    exit(main())