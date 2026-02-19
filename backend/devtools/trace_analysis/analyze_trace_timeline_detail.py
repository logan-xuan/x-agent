#!/usr/bin/env python3
"""Detailed timeline analysis of trace c80c57c5-73ff-42c5-b0ea-bb864ba0f572."""

import json
from pathlib import Path

log_file = Path('/Users/xuan.lx/Documents/x-agent/x-agent/backend/logs/x-agent.log')
trace_id = 'c80c57c5-73ff-42c5-b0ea-bb864ba0f572'

print("=" * 80)
print(f"详细时间线分析：{trace_id}")
print("=" * 80)

events = []

with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if trace_id in line:
            try:
                data = json.loads(line)
                msg_data = json.loads(data.get('message', '{}'))
                event = msg_data.get('event', '')
                timestamp = data.get('timestamp', '')
                
                # 收集所有关键事件
                if any(keyword in event.lower() for keyword in [
                    'install', 'pip', 'confirmation', 'high-risk', 
                    're-executing', 'milestone', 'replan', 'failed',
                    'tool_call', 'tool_result', 'react loop', 'user message'
                ]):
                    events.append({
                        'timestamp': timestamp,
                        'event': event,
                        'data': msg_data
                    })
            except:
                pass

# 按时间排序并显示
print(f"\n共找到 {len(events)} 个关键事件\n")

for i, item in enumerate(events, 1):
    ts = item['timestamp'][:22] if item['timestamp'] else 'N/A'
    event = item['event']
    
    print(f"{i:3}. [{ts}] {event}")
    
    # 显示额外信息
    if 'command' in item['data']:
        cmd = item['data']['command']
        if isinstance(cmd, str):
            if 'pip' in cmd or 'npm' in cmd:
                print(f"      Command: {cmd[:100]}")
    
    if 'error' in item['data'] and item['data']['error']:
        error = item['data']['error']
        print(f"      ERROR: {str(error)[:100]}")
    
    if 'content' in item['data']:
        content = item['data']['content']
        if isinstance(content, str) and len(content) < 200:
            print(f"      Content: {content[:100]}")
    
    if 'confirmation_id' in item['data']:
        print(f"      confirmation_id: {item['data']['confirmation_id']}")
    
    if 'tool_call_id' in item['data']:
        print(f"      tool_call_id: {item['data']['tool_call_id']}")
    
    print()

print("\n" + "=" * 80)
print("问题诊断")
print("=" * 80)

# 统计
milestone_failures = sum(1 for e in events if 'Milestone validation failed' in e['event'])
replans = sum(1 for e in events if 'Replan triggered' in e['event'])
confirmations = sum(1 for e in events if 'confirmation' in e['event'].lower())
high_risk = sum(1 for e in events if 'high-risk' in e['event'].lower())

print(f"\n里程碑验证失败：{milestone_failures}次")
print(f"重规划触发：{replans}次")
print(f"确认相关事件：{confirmations}次")
print(f"高危命令事件：{high_risk}次")

if milestone_failures > 0 or replans > 0:
    print("\n⚠️  检测到重规划循环！")
    print("\n可能的问题:")
    print("1. 等待用户确认耗时过长，触发超时")
    print("2. 系统误判为工具执行失败")
    print("3. 触发重规划后 LLM 再次尝试安装")
    print("4. 形成死循环")
else:
    print("\n✅ 未检测到明显的重规划问题")

print("\n" + "=" * 80)
