#!/usr/bin/env python3
"""Test the corrected path resolution."""

from pathlib import Path

def test_corrected_path():
    print("Testing corrected path resolution...")

    # Simulate from backend/src/services/analysis_cache.py
    backend_dir = Path("src/services/analysis_cache.py").parent.parent.parent  # Go to backend dir (relative to backend/)
    project_root = backend_dir.parent  # Go to parent of backend (relative to project root)
    cache_dir = project_root / "workspace" / "dev" / "Analysis"

    print(f"Backend dir calculation: {backend_dir}")  # This would be '..' when run from backend dir
    print(f"Project root calculation: {project_root}")  # This would be '.' when run from backend dir
    print(f"Cache dir calculation: {cache_dir}")  # This would be './workspace/dev/Analysis' when run from backend dir

    # If we run this from the backend directory, backend_dir would be '..', project_root would be '..'/'..' = parent of backend
    actual_backend_dir = Path(__file__).parent  # We're in backend now
    actual_project_root = actual_backend_dir.parent  # Go up from backend to project root
    actual_cache_dir = actual_project_root / "workspace" / "dev" / "Analysis"

    print(f"\nActual from this location:")
    print(f"Current dir (backend): {actual_backend_dir}")
    print(f"Project root: {actual_project_root}")
    print(f"Cache dir: {actual_cache_dir}")
    print(f"Cache dir exists: {actual_cache_dir.exists()}")

    if actual_cache_dir.exists():
        files = list(actual_cache_dir.iterdir())
        print(f"Files in cache dir: {len(files)}")
        for f in files:
            print(f"  - {f.name}")

if __name__ == "__main__":
    test_corrected_path()