#!/usr/bin/env python3
"""Analyze trace 76fdd8ed-4ac3-4583-9b09-c789b26f409b"""
import json
from collections import Counter

trace_id = "76fdd8ed-4ac3-4583-9b09-c789b26f409b"
tools = []
events = []

with open('/Users/xuan.lx/Documents/x-agent/x-agent/backend/logs/x-agent.log', 'r') as f:
    for line in f:
        if trace_id in line:
            try:
                data = json.loads(line)
                msg = json.loads(data['message'])
                event = msg.get('event', '')
                
                # Track tool executions
                if 'Executing tool' in event:
                    tool_name = msg['extra']['tool_name']
                    tools.append(tool_name)
                
                # Track key events
                if any(x in event for x in ['Plan', 'ReAct', 'current_step', 'Tool constraint', 'final_answer', 'TASK_ANALYSIS']):
                    events.append({
                        'event': event,
                        'timestamp': data.get('timestamp', ''),
                        'extra': msg.get('extra', {})
                    })
            except:
                pass

print("=" * 80)
print(f"Trace Analysis: {trace_id}")
print("=" * 80)

print("\n1. Task Analysis:")
for e in events:
    if 'TASK_ANALYSIS' in e['event']:
        print(f"   {e['event']}: {e['extra']}")

print("\n2. Tool Execution Statistics:")
if tools:
    counts = Counter(tools)
    for tool, count in counts.most_common():
        print(f"   {count:4d} x {tool}")
else:
    print("   No tools executed!")

print("\n3. Key Events Timeline:")
for e in events[:10]:  # Show first 10 events
    print(f"   - {e['event']}")

if len(events) > 10:
    print(f"   ... and {len(events) - 10} more events")

print("\n4. Conclusion:")
if not tools:
    print("   ❌ No Plan was generated (needs_plan=False)")
    print("   ⚠️  This appears to be a simple task that bypassed planning")
else:
    print(f"   ✓ Generated plan with {len(tools)} tool calls")
