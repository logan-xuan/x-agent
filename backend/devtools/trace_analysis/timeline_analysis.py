#!/usr/bin/env python3
"""Timeline analysis of trace 804f02a0-a84d-4e1b-9954-5fca7de47aba."""

import json
from pathlib import Path
from datetime import datetime

log_file = Path('logs/x-agent.log')
trace_id = '804f02a0-a84d-4e1b-9954-5fca7de47aba'

print("=" * 80)
print("时间线分析：为什么一直在重新安装依赖包")
print("=" * 80)

events_timeline = []

with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if trace_id in line:
            try:
                data = json.loads(line)
                timestamp = data.get('timestamp')
                msg_data = json.loads(data.get('message', '{}'))
                event = msg_data.get('event', '')
                
                # 只收集关键事件
                if any(keyword in event.lower() for keyword in [
                    'install', 'pip', 'confirmation', 'high-risk', 
                    're-executing', 'milestone', 'replan', 'failed',
                    'tool_call', 'tool_result', 'react loop'
                ]):
                    events_timeline.append({
                        'timestamp': timestamp,
                        'event': event,
                        'data': msg_data
                    })
            except:
                pass

# 按时间排序并显示
print(f"\n共找到 {len(events_timeline)} 个关键事件\n")

for i, item in enumerate(events_timeline, 1):
    ts = item['timestamp'][:22] if item['timestamp'] else 'N/A'
    event = item['event']
    
    # 简化显示
    print(f"{i:3}. [{ts}] {event}")
    
    # 显示额外信息
    if 'command' in item['data']:
        cmd = item['data']['command'][:80]
        print(f"      Command: {cmd}...")
    
    if 'error' in item['data'] and item['data']['error']:
        print(f"      ERROR: {item['data']['error'][:80]}...")
    
    if 'milestone' in item['data']:
        print(f"      Milestone: {item['data']['milestone']}")
    
    if 'reason' in item['data']:
        print(f"      Reason: {item['data']['reason'][:80]}...")
    
    print()

print("\n" + "=" * 80)
print("问题诊断:")
print("=" * 80)

# 统计里程碑失败次数
milestone_failures = sum(1 for e in events_timeline if 'Milestone validation failed' in e['event'])
replans = sum(1 for e in events_timeline if 'Replan triggered' in e['event'])
confirmations = sum(1 for e in events_timeline if 'confirmation' in e['event'].lower())

print(f"\n里程碑验证失败：{milestone_failures}次")
print(f"重规划触发：{replans}次")
print(f"确认操作：{confirmations}次")

if milestone_failures > 0:
    print("\n⚠️  根本原因分析:")
    print("  1. LLM 计划创建 PPT，但需要安装 python-pptx 依赖")
    print("  2. pip install 被识别为高危命令，需要用户确认")
    print("  3. 等待用户确认期间，可能触发了超时或其他问题")
    print("  4. 里程碑验证失败 → 触发重规划")
    print("  5. 重规划后 LLM 再次尝试安装 → 循环重复")
    print("\n💡 解决方案:")
    print("  - 在技能文档中明确说明依赖检查逻辑")
    print("  - 先检查是否已安装，避免重复安装")
    print("  - 使用虚拟环境或预安装依赖")

print("\n" + "=" * 80)
