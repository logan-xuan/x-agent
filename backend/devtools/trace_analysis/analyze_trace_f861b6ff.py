#!/usr/bin/env python3
"""Analyze trace f861b6ff-4c48-4487-a4a4-3566e4bbaad8 for repeated errors."""

import json
from pathlib import Path

log_file = Path('logs/x-agent.log')
trace_id = 'f861b6ff-4c48-4487-a4a4-3566e4bbaad8'

print("=" * 80)
print(f"分析 Trace: {trace_id}")
print("=" * 80)

found_lines = []
with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if trace_id in line:
            found_lines.append(line.strip())

print(f"\n找到 {len(found_lines)} 条相关日志\n")

# 查找所有错误和工具调用
errors = []
tool_calls = []

for content in found_lines:
    try:
        data = json.loads(content)
        msg_data = json.loads(data.get('message', '{}'))
        event = msg_data.get('event', '')
        
        # 收集错误
        if 'error' in msg_data and msg_data['error']:
            error_msg = str(msg_data['error'])[:200]
            errors.append({
                'timestamp': data.get('timestamp'),
                'event': event,
                'error': error_msg,
                'data': msg_data
            })
        
        # 收集工具调用
        if event == 'Executing tool':
            tool_name = msg_data.get('name', '')
            arguments = msg_data.get('arguments', {})
            
            if tool_name == 'run_in_terminal' and isinstance(arguments, dict):
                command = str(arguments.get('command', ''))
                if 'node' in command or '.js' in command:
                    tool_calls.append({
                        'timestamp': data.get('timestamp'),
                        'command': command[:150],
                        'output': msg_data.get('output', '')[:200] if 'output' in msg_data else '',
                        'error': msg_data.get('error', '')[:200] if 'error' in msg_data else ''
                    })
    except:
        pass

# 显示错误统计
print("=" * 80)
print("错误统计")
print("=" * 80)
print(f"\n共发现 {len(errors)} 个错误\n")

for i, err in enumerate(errors[:10], 1):  # 只显示前 10 个
    print(f"{i}. [{err['timestamp'][:22] if err['timestamp'] else 'N/A'}] {err['event']}")
    print(f"   Error: {err['error']}")
    print()

# 显示工具调用
print("\n" + "=" * 80)
print("JavaScript 工具调用")
print("=" * 80)
print(f"\n共发现 {len(tool_calls)} 次 Node.js 脚本执行\n")

for i, call in enumerate(tool_calls, 1):
    print(f"{i}. [{call['timestamp'][:22] if call['timestamp'] else 'N/A'}]")
    print(f"   Command: {call['command']}")
    if call['error']:
        print(f"   ERROR: {call['error']}")
    elif call['output']:
        print(f"   Output: {call['output']}")
    print()

# 查找 html2pptx 相关内容
print("\n" + "=" * 80)
print("html2pptx 相关内容")
print("=" * 80)

for content in found_lines:
    try:
        data = json.loads(content)
        msg_data = json.loads(data.get('message', '{}'))
        
        # 检查是否提到 html2pptx
        full_text = json.dumps(msg_data)
        if 'html2pptx' in full_text.lower():
            event = msg_data.get('event', '')
            print(f"\n[{event}]")
            for key in ['command', 'output', 'error']:
                if key in msg_data:
                    val = str(msg_data[key])[:300]
                    print(f"{key}: {val}")
    except:
        pass

print("\n" + "=" * 80)
print("诊断结论")
print("=" * 80)

if len(errors) > 3:
    print("\n⚠️  检测到重复错误！")
    print("\n可能原因:")
    print("1. html2pptx 模块没有正确导入")
    print("2. pptxgenjs 包没有安装或版本不兼容")
    print("3. JavaScript 脚本代码有误")
    print("4. LLM 在反复尝试相同的错误方法")
else:
    print("\n✅ 错误数量正常")

print("\n" + "=" * 80)
