import sys
from pathlib import Path

# Add project root to sys.path so `from scripts.X import Y` works in tests
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
