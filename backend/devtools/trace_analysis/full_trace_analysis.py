#!/usr/bin/env python3
"""Complete analysis of trace 804f02a0-a84d-4e1b-9954-5fca7de47aba."""

import json
from pathlib import Path

print("=" * 80)
print("完整分析 Trace: 804f02a0-a84d-4e1b-9954-5fca7de47aba")
print("=" * 80)

# 1. 查看 x-agent.log
log_file = Path('logs/x-agent.log')
trace_id = '804f02a0-a84d-4e1b-9954-5fca7de47aba'

found_lines = []
with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if trace_id in line:
            found_lines.append(line.strip())

print(f"\n[x-agent.log] 找到 {len(found_lines)} 条日志\n")

# 提取关键事件
events = []
for content in found_lines:
    try:
        data = json.loads(content)
        msg_data = json.loads(data.get('message', '{}'))
        event = msg_data.get('event', '')
        events.append(event)
        
        # 显示重要事件
        if event not in ['Trying provider', 'Successfully used provider', 'Exiting LLMRouter.chat']:
            print(f"  - {event}")
    except:
        pass

# 统计事件
from collections import Counter
event_counts = Counter(events)
print("\n事件统计:")
for event, count in sorted(event_counts.items(), key=lambda x: -x[1]):
    if count > 1 or event not in ['Trying provider', 'Successfully used provider']:
        print(f"  {event}: {count}次")

# 2. 查看 prompt-llm.log
print("\n" + "=" * 80)
print("[prompt-llm.log] LLM 响应分析")
print("=" * 80)

llm_log = Path('logs/prompt-llm.log')
llm_calls = []

with open(llm_log, 'r', encoding='utf-8') as f:
    for line in f:
        if trace_id in line:
            try:
                data = json.loads(line)
                response = data.get('response', '')
                if len(response) > 50:
                    llm_calls.append({
                        'timestamp': data.get('timestamp'),
                        'success': data.get('success'),
                        'response': response
                    })
            except:
                pass

print(f"\n找到 {len(llm_calls)} 次 LLM 调用\n")

for i, call in enumerate(llm_calls, 1):
    print(f"[{i}] Timestamp: {call['timestamp']}")
    print(f"    Success: {call['success']}")
    
    response = call['response']
    
    # 检查是否提到安装
    has_install = 'install' in response.lower() or '安装' in response
    has_npm = 'npm' in response.lower()
    has_pip = 'pip' in response.lower()
    
    if has_install or has_npm or has_pip:
        print(f"    ⚠️  包含安装相关内容!")
        preview = response[:300].replace('\n', '\\n')
        print(f"    Preview: {preview}...")
    else:
        preview = response[:200].replace('\n', '\\n')
        print(f"    Preview: {preview}...")
    
    print()

# 3. 查找用户原始请求
print("\n" + "=" * 80)
print("[查找用户原始请求]")
print("=" * 80)

for content in found_lines:
    try:
        data = json.loads(content)
        msg_data = json.loads(data.get('message', '{}'))
        event = msg_data.get('event', '')
        
        if event == 'User message received':
            content_text = msg_data.get('content', '')
            print(f"\n用户请求:\n{content_text}")
    except:
        pass

print("\n" + "=" * 80)
print("分析完成")
print("=" * 80)
