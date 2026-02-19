#!/usr/bin/env python3
"""Script to verify cache functionality is working correctly."""

import os
import sys
from pathlib import Path

# Add the backend src directory to the path so imports work
sys.path.insert(0, '../backend/src')

from services.analysis_cache import get_analysis_cache, AnalysisCache

def test_cache_paths():
    """Test that cache paths are resolving correctly."""

    print("Testing cache path resolution...")

    # Test default initialization
    cache_default = AnalysisCache()  # Should use workspace/dev/Analysis
    print(f"Default cache dir: {cache_default.cache_dir}")
    print(f"Default cache dir exists: {cache_default.cache_dir.exists()}")

    # Test getting via factory function
    cache_func = get_analysis_cache()
    print(f"Factory cache dir: {cache_func.cache_dir}")
    print(f"Factory cache dir exists: {cache_func.cache_dir.exists()}")

    # Test specific path
    cache_specific = AnalysisCache("../../workspace/dev/Analysis")
    print(f"Specific cache dir: {cache_specific.cache_dir}")
    print(f"Specific cache dir exists: {cache_specific.cache_dir.exists()}")

    # List files in the actual workspace Analysis directory
    actual_dir = Path("../../workspace/dev/Analysis")
    print(f"\nActual workspace Analysis dir: {actual_dir}")
    print(f"Actual workspace Analysis dir exists: {actual_dir.exists()}")

    if actual_dir.exists():
        files = list(actual_dir.iterdir())
        print(f"Files in actual dir: {len(files)}")
        for f in files:
            print(f"  - {f.name}")

if __name__ == "__main__":
    test_cache_paths()