#!/usr/bin/env python3
"""Test path resolution for cache directory."""

from pathlib import Path

def test_path_resolution():
    # Simulate the path resolution from analysis_cache.py
    # File is at: backend/src/services/analysis_cache.py
    # We want to get to project root (where workspace/ is)

    # If this file is __file__, then from analysis_cache.py:
    current_file_path = Path("backend/src/services/analysis_cache.py").resolve()
    print(f"Simulated current file path: {current_file_path}")

    # Go up 4 levels from analysis_cache.py to get project root
    project_root = Path(__file__).parent  # Current directory (project root)
    print(f"Project root: {project_root}")

    # The actual cache dir should be
    cache_dir = project_root / "workspace" / "dev" / "Analysis"
    print(f"Cache directory: {cache_dir}")
    print(f"Cache directory exists: {cache_dir.exists()}")

    # If running from backend directory context:
    backend_file_path = Path("src/services/analysis_cache.py")  # Relative to backend
    simulated_backend_based_project_root = Path("..").resolve()  # One level up from backend
    print(f"\nSimulated backend-based project root: {simulated_backend_based_project_root}")

    cache_dir_from_backend_context = simulated_backend_based_project_root / "workspace" / "dev" / "Analysis"
    print(f"Cache dir from backend context: {cache_dir_from_backend_context}")
    print(f"Cache dir from backend context exists: {cache_dir_from_backend_context.exists()}")


if __name__ == "__main__":
    test_path_resolution()