#!/usr/bin/env python3
import json

trace_id = 'b4d7a653-7860-4cde-8ed0-1009f376be29'

print("Analyzing LLM calls for trace:", trace_id)
print("=" * 80)

with open('logs/prompt-llm.log', 'r', encoding='utf-8') as f:
    count = 0
    for line in f:
        if trace_id in line:
            try:
                data = json.loads(line)
                response = data.get('response', '')
                if len(response) > 50:
                    count += 1
                    print(f"\n[Call {count}]")
                    print(f"Timestamp: {data['timestamp']}")
                    print(f"Success: {data.get('success')}")
                    print(f"Response preview ({len(response)} chars):")
                    print("-" * 80)
                    print(response[:300])
                    if len(response) > 300:
                        print(f"... ({len(response) - 300} more chars)")
                    
                    # Check if it's just text without tool calls
                    has_tool = any(tool in response for tool in ['read_file', 'write_file', 'run_in_terminal'])
                    if not has_tool and len(response) > 100:
                        print("⚠️  WARNING: Response appears to be text-only (no tool calls detected)")
                    print()
            except Exception as e:
                print(f"Error parsing line: {e}")

print(f"\nTotal LLM calls found: {count}")
