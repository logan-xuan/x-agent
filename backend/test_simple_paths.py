#!/usr/bin/env python3
"""Simple script to verify cache path resolution."""

import sys
from pathlib import Path

def test_cache_paths_directly():
    """Test cache path resolution without imports."""

    print("Testing cache path resolution directly...")

    # Replicate the logic from AnalysisCache.__init__ with default path
    backend_dir = Path(__file__).parent / "src"  # Since we're in backend dir
    cache_dir = backend_dir.parent / "workspace" / "dev" / "Analysis"

    print(f"Backend dir: {backend_dir.resolve()}")
    print(f"Cache dir: {cache_dir.resolve()}")
    print(f"Cache dir exists: {cache_dir.exists()}")

    # Check the actual workspace directory
    actual_workspace_analysis = Path("../workspace/dev/Analysis")
    print(f"Actual workspace analysis dir: {actual_workspace_analysis.resolve()}")
    print(f"Actual workspace analysis dir exists: {actual_workspace_analysis.exists()}")

    if actual_workspace_analysis.exists():
        files = list(actual_workspace_analysis.iterdir())
        print(f"Files in actual dir: {len(files)}")
        for f in files:
            print(f"  - {f.name}")

if __name__ == "__main__":
    test_cache_paths_directly()