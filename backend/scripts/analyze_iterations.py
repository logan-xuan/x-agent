#!/usr/bin/env python3
"""Analyze ReAct loop iteration statistics from logs.

This script parses the x-agent.log file and extracts statistics about:
- Average iterations used per request
- Iteration utilization rate (actual vs max)
- Tool calls per iteration
- Success/failure rates

Usage:
    python scripts/analyze_iterations.py [log_file]
    
Examples:
    python scripts/analyze_iterations.py logs/x-agent.log
    tail -n 10000 logs/x-agent.log | python scripts/analyze_iterations.py
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def parse_log_line(line: str) -> dict[str, Any] | None:
    """Parse a JSON log line."""
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


def extract_iteration_stats(log_lines: list[str]) -> list[dict[str, Any]]:
    """Extract iteration statistics from log lines."""
    stats = []
    
    for line in log_lines:
        log_data = parse_log_line(line)
        if not log_data:
            continue
        
        # Look for "ReAct loop reached max iterations" warnings
        if log_data.get("event") == "ReAct loop reached max iterations":
            extra = log_data.get("extra", {})
            stats.append({
                "session_id": extra.get("session_id"),
                "trace_id": log_data.get("trace_id"),
                "actual_iterations": extra.get("actual_iterations", 0),
                "max_iterations": extra.get("max_iterations", 0),
                "utilization_rate": extra.get("utilization_rate", "0%"),
                "total_tool_calls": extra.get("total_tool_calls", 0),
                "completed_early": extra.get("completed_early", False),
                "timestamp": log_data.get("timestamp"),
            })
        
        # Also look for successful completions
        elif log_data.get("event") == "ReAct loop completed":
            extra = log_data.get("extra", {})
            stats.append({
                "session_id": log_data.get("session_id"),
                "trace_id": log_data.get("trace_id"),
                "actual_iterations": extra.get("iterations", 0),
                "max_iterations": "N/A (completed early)",
                "utilization_rate": "N/A",
                "total_tool_calls": "N/A",
                "completed_early": True,
                "timestamp": log_data.get("timestamp"),
            })
    
    return stats


def analyze_stats(stats: list[dict[str, Any]]) -> None:
    """Analyze and display statistics."""
    if not stats:
        print("❌ No iteration statistics found in logs")
        return
    
    print("\n" + "=" * 80)
    print("📊 ReAct Loop Iteration Statistics")
    print("=" * 80)
    
    # Separate completed early vs max iterations reached
    completed_early = [s for s in stats if s.get("completed_early")]
    max_reached = [s for s in stats if not s.get("completed_early")]
    
    print(f"\n📈 Total Requests Analyzed: {len(stats)}")
    print(f"   ✅ Completed Early: {len(completed_early)} ({len(completed_early)/len(stats)*100:.1f}%)")
    print(f"   ⚠️  Max Iterations Reached: {len(max_reached)} ({len(max_reached)/len(stats)*100:.1f}%)")
    
    # Analyze max iteration cases
    if max_reached:
        print(f"\n🔴 Max Iterations Analysis ({len(max_reached)} cases)")
        print("-" * 80)
        
        iterations = [s["actual_iterations"] for s in max_reached]
        avg_iterations = sum(iterations) / len(iterations)
        min_iterations = min(iterations)
        max_iterations = max(iterations)
        
        print(f"   Average Iterations: {avg_iterations:.2f}")
        print(f"   Min Iterations: {min_iterations}")
        print(f"   Max Iterations: {max_iterations}")
        
        # Utilization rates
        utilization_rates = []
        for s in max_reached:
            rate_str = s.get("utilization_rate", "0%")
            if isinstance(rate_str, str) and "%" in rate_str:
                try:
                    utilization_rates.append(float(rate_str.replace("%", "")))
                except ValueError:
                    pass
        
        if utilization_rates:
            avg_utilization = sum(utilization_rates) / len(utilization_rates)
            print(f"   Average Utilization Rate: {avg_utilization:.1f}%")
        
        # Tool calls
        tool_calls = [s.get("total_tool_calls", 0) for s in max_reached]
        if any(isinstance(tc, int) for tc in tool_calls):
            valid_tool_calls = [tc for tc in tool_calls if isinstance(tc, int)]
            if valid_tool_calls:
                avg_tool_calls = sum(valid_tool_calls) / len(valid_tool_calls)
                print(f"   Average Tool Calls: {avg_tool_calls:.2f}")
        
        # Distribution
        print(f"\n   Iteration Distribution:")
        iteration_counts = defaultdict(int)
        for s in max_reached:
            iteration_counts[s["actual_iterations"]] += 1
        
        for iters in sorted(iteration_counts.keys()):
            count = iteration_counts[iters]
            bar = "█" * count
            print(f"      {iters:2d} iterations: {count:3d} {bar}")
    
    # Analyze early completions
    if completed_early:
        print(f"\n✅ Early Completion Analysis ({len(completed_early)} cases)")
        print("-" * 80)
        
        iterations = [s["actual_iterations"] for s in completed_early]
        if iterations:
            avg_iterations = sum(iterations) / len(iterations)
            min_iterations = min(iterations)
            max_iterations = max(iterations)
            
            print(f"   Average Iterations Used: {avg_iterations:.2f}")
            print(f"   Min Iterations: {min_iterations}")
            print(f"   Max Iterations: {max_iterations}")
            
            # Distribution
            print(f"\n   Iteration Distribution:")
            iteration_counts = defaultdict(int)
            for s in completed_early:
                iteration_counts[s["actual_iterations"]] += 1
            
            for iters in sorted(iteration_counts.keys()):
                count = iteration_counts[iters]
                bar = "█" * count
                print(f"      {iters:2d} iterations: {count:3d} {bar}")
    
    # Recommendations
    print("\n" + "=" * 80)
    print("💡 Recommendations")
    print("=" * 80)
    
    if max_reached:
        avg_max_iters = sum(s["actual_iterations"] for s in max_reached) / len(max_reached)
        
        if avg_max_iters > 9:
            print(f"\n⚠️  WARNING: Average iterations ({avg_max_iters:.1f}) is very high!")
            print(f"   → Consider increasing max_iterations to {int(avg_max_iters * 1.5)}")
            print(f"   → Or optimize task planning to reduce steps needed")
        elif avg_max_iters > 7:
            print(f"\n⚠️  CAUTION: Average iterations ({avg_max_iters:.1f}) is approaching limit")
            print(f"   → Current max_iterations setting may be too low")
            print(f"   → Monitor for task failures")
        else:
            print(f"\n✅ Average iterations ({avg_max_iters:.1f}) is within safe range")
    
    if completed_early:
        avg_early_iters = sum(s["actual_iterations"] for s in completed_early) / len(completed_early)
        print(f"\n✅ Tasks completing early use average {avg_early_iters:.1f} iterations")
        print(f"   → This indicates efficient execution for simpler tasks")
    
    print()


def main():
    """Main entry point."""
    # Determine log source
    if len(sys.argv) > 1:
        log_file = Path(sys.argv[1])
        if not log_file.exists():
            print(f"❌ Log file not found: {log_file}")
            sys.exit(1)
        print(f"📖 Reading log file: {log_file}")
        with open(log_file, "r", encoding="utf-8") as f:
            log_lines = f.readlines()
    else:
        # Read from stdin
        print("📖 Reading from stdin...")
        log_lines = sys.stdin.readlines()
    
    # Extract statistics
    stats = extract_iteration_stats(log_lines)
    
    # Analyze and display
    analyze_stats(stats)


if __name__ == "__main__":
    main()
