#!/usr/bin/env python3
"""Test script to verify trace analysis caching functionality."""

import asyncio
import tempfile
import os
from pathlib import Path

# Add the backend src directory to the path so imports work
import sys
sys.path.insert(0, '../backend/src')

from services.trace_analyzer import TraceAnalyzer
from services.analysis_cache import AnalysisCache
from services.llm.router import LLMRouter
from config.config_manager import ConfigManager


async def test_cache_functionality():
    """Test the trace analysis cache functionality."""

    print("Testing trace analysis caching functionality...")

    # Create temporary log directory for testing
    with tempfile.TemporaryDirectory() as temp_log_dir:
        # Create a minimal config manager
        config_path = Path("../backend/x-agent.yaml")
        if not config_path.exists():
            # Create a minimal config file for testing
            config_content = """
llm:
  providers:
    openai:
      enabled: false
      api_key: ""
    bailian:
      enabled: false
      api_key: ""
  default_provider: "openai"
  timeout: 30
  max_retries: 3
  fallback_enabled: true
"""
            config_path.write_text(config_content)

        config_manager = ConfigManager(config_path=str(config_path))
        llm_router = LLMRouter(config_manager)

        # Initialize the trace analyzer with cache enabled
        analyzer = TraceAnalyzer(llm_router=llm_router, log_dir=temp_log_dir, cache_enabled=True)
        cache = analyzer.cache

        print("✓ Trace analyzer initialized with cache")

        # Test 1: Verify cache directory exists
        assert cache.cache_dir.exists(), f"Cache directory does not exist: {cache.cache_dir}"
        print("✓ Cache directory exists")

        # Test 2: Try to get non-existent cache
        result = cache.get_cached_analysis("non_existent_trace")
        assert result is None, "Expected None for non-existent cache"
        print("✓ Correctly returns None for non-existent cache")

        # Test 3: Store and retrieve a sample result
        sample_result = {
            "analysis": "# Sample Analysis\nThis is a sample analysis result.",
            "insights": [
                {
                    "type": "performance",
                    "title": "Sample Insight",
                    "description": "This is a sample insight",
                    "location": "test.location",
                    "severity": "medium"
                }
            ],
            "suggestions": ["Sample suggestion"]
        }

        success = cache.cache_analysis("sample_trace", sample_result)
        assert success, "Failed to cache analysis"
        print("✓ Successfully cached analysis")

        # Test 4: Retrieve cached result
        retrieved_result = cache.get_cached_analysis("sample_trace")
        assert retrieved_result is not None, "Failed to retrieve cached result"
        assert retrieved_result['analysis'] == sample_result['analysis'], "Analysis content mismatch"
        assert len(retrieved_result['insights']) == len(sample_result['insights']), "Insights count mismatch"
        print("✓ Successfully retrieved cached analysis")

        # Test 5: Delete cached result
        success = cache.delete_cached_analysis("sample_trace")
        assert success, "Failed to delete cached analysis"
        print("✓ Successfully deleted cached analysis")

        # Verify deletion
        result = cache.get_cached_analysis("sample_trace")
        assert result is None, "Cache still exists after deletion"
        print("✓ Cache properly deleted")

        print("\n✓ All cache functionality tests passed!")


if __name__ == "__main__":
    asyncio.run(test_cache_functionality())