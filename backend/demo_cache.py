#!/usr/bin/env python3
"""Demonstration of trace analysis cache functionality."""

from pathlib import Path
import sys
import json
from datetime import datetime

# Add backend src to path
sys.path.insert(0, './src')

def demonstrate_cache_functionality():
    print("=== Trace Analysis Cache Demonstration ===\n")

    # Import after path modification
    from services.analysis_cache import AnalysisCache

    print("1. Initializing AnalysisCache...")
    cache = AnalysisCache()
    print(f"   Cache directory: {cache.cache_dir}")
    print(f"   Cache directory exists: {cache.cache_dir.exists()}")

    if not cache.cache_dir.exists():
        print(f"   Creating cache directory...")
        cache.cache_dir.mkdir(parents=True, exist_ok=True)

    print(f"   Cache directory now exists: {cache.cache_dir.exists()}")

    # Example trace ID
    trace_id = "demo-trace-123"
    focus_areas = ["performance", "error"]

    print(f"\n2. Testing cache for trace ID: {trace_id}")

    # Check if there's already a cached result
    cached_result = cache.get_cached_analysis(trace_id, focus_areas)
    if cached_result:
        print("   Found existing cached result")
        print(f"   Cached at: {cached_result.get('cached_at')}")
        print(f"   Analysis length: {len(cached_result.get('analysis', ''))} characters")
        print(f"   Insights count: {len(cached_result.get('insights', []))}")
        print(f"   Suggestions count: {len(cached_result.get('suggestions', []))}")
    else:
        print("   No existing cached result found (this is expected on first run)")

    # Create a sample analysis result
    sample_result = {
        "analysis": "# Performance Analysis Report\n\nThe trace shows some performance bottlenecks in the LLM calls.\n\n## Key Issues:\n- High latency in API calls\n- Excessive token usage\n\n## Recommendations:\n- Optimize prompt length\n- Consider caching for repeated operations",
        "insights": [
            {
                "type": "performance",
                "title": "High Latency Detected",
                "description": "LLM calls taking over 3 seconds",
                "location": "llm.router",
                "severity": "high"
            },
            {
                "type": "optimization",
                "title": "Token Usage Optimization",
                "description": "Consider shorter prompts to reduce costs",
                "location": "prompt.engineering",
                "severity": "medium"
            }
        ],
        "suggestions": [
            "Implement prompt caching for frequently used prompts",
            "Consider using a smaller model for initial screening"
        ]
    }

    print(f"\n3. Saving analysis result to cache...")
    success = cache.cache_analysis(trace_id, sample_result, focus_areas)
    print(f"   Cache save successful: {success}")

    # Now try to retrieve it
    print(f"\n4. Retrieving cached result...")
    retrieved_result = cache.get_cached_analysis(trace_id, focus_areas)

    if retrieved_result:
        print("   ✓ Retrieved cached result successfully!")
        print(f"   Analysis length: {len(retrieved_result.get('analysis', ''))} characters")
        print(f"   Insights count: {len(retrieved_result.get('insights', []))}")
        print(f"   Suggestions count: {len(retrieved_result.get('suggestions', []))}")
        print(f"   Retrieved cached_at: {retrieved_result.get('cached_at')}")

        # Verify content matches
        content_matches = (retrieved_result['analysis'] == sample_result['analysis'] and
                          len(retrieved_result['insights']) == len(sample_result['insights']) and
                          len(retrieved_result['suggestions']) == len(sample_result['suggestions']))
        print(f"   Content matches original: {content_matches}")
    else:
        print("   ✗ Failed to retrieve cached result")

    # Test with no focus areas
    print(f"\n5. Testing cache without focus areas...")
    success_no_focus = cache.cache_analysis("simple-trace", sample_result)
    retrieved_no_focus = cache.get_cached_analysis("simple-trace")

    if retrieved_no_focus:
        print("   ✓ Cached and retrieved result without focus areas successfully")
    else:
        print("   ✗ Failed to cache/retrieve result without focus areas")

    print(f"\n6. Testing cache filename generation...")
    filename_with_focus = cache._generate_filename(trace_id, focus_areas)
    filename_without_focus = cache._generate_filename("simple-trace")

    print(f"   With focus areas: {filename_with_focus}")
    print(f"   Without focus areas: {filename_without_focus}")
    print(f"   Filenames are different: {filename_with_focus != filename_without_focus}")

    # List files in cache directory
    print(f"\n7. Files in cache directory:")
    cache_files = list(cache.cache_dir.glob("analysis_*.md"))
    for file_path in cache_files:
        print(f"   - {file_path.name}")

    print(f"\n=== Cache functionality demonstrated successfully! ===")


if __name__ == "__main__":
    demonstrate_cache_functionality()