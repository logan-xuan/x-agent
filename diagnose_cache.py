#!/usr/bin/env python3
"""Diagnostic script to check cache functionality."""

import sys
from pathlib import Path

def diagnose_paths():
    """Diagnose the path resolution issue."""

    print("=== Path Diagnosis ===")

    # Get current working directory (where script would run from)
    cwd = Path.cwd()
    print(f"Current working directory: {cwd}")

    # The cache file is located at backend/src/services/analysis_cache.py
    # From there, going up 4 levels should get us to project root
    cache_file_path = Path("../backend/src/services/analysis_cache.py").resolve()
    print(f"Resolved cache file path: {cache_file_path}")

    # Calculate where cache_dir should be from the cache file location
    calculated_cache_dir = cache_file_path.parent.parent.parent.parent / "workspace" / "dev" / "Analysis"
    print(f"Calculated cache directory: {calculated_cache_dir}")
    print(f"Calculated cache directory exists: {calculated_cache_dir.exists()}")

    # Check if workspace directory exists at project root
    project_root = cache_file_path.parent.parent.parent.parent
    workspace_dir = project_root / "workspace"
    print(f"Workspace directory: {workspace_dir}")
    print(f"Workspace directory exists: {workspace_dir.exists()}")

    # List files in workspace/dev if it exists
    dev_dir = workspace_dir / "dev"
    if dev_dir.exists():
        print(f"Dev directory exists: {dev_dir}")
        analysis_dir = dev_dir / "Analysis"
        print(f"Analysis directory exists: {analysis_dir}")
        if analysis_dir.exists():
            print("Files in Analysis directory:")
            for f in analysis_dir.iterdir():
                print(f"  - {f.name}")
        else:
            print("Analysis directory does not exist")
    else:
        print("Dev directory does not exist")

    # Check the actual structure around current directory
    print(f"\nFiles in current directory ({cwd}):")
    for item in cwd.iterdir():
        print(f"  - {item.name} ({'dir' if item.is_dir() else 'file'})")


if __name__ == "__main__":
    diagnose_paths()