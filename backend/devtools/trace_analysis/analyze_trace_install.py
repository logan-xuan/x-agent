#!/usr/bin/env python3
"""Analyze trace 804f02a0-a84d-4e1b-9954-5fca7de47aba for repeated npm/pip installs."""

import json
from pathlib import Path

log_file = Path('logs/x-agent.log')
trace_id = '804f02a0-a84d-4e1b-9954-5fca7de47aba'

print("=" * 80)
print(f"分析 Trace: {trace_id}")
print("=" * 80)

found_lines = []
with open(log_file, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        if trace_id in line:
            found_lines.append((i, line.strip()))

print(f"\n找到 {len(found_lines)} 条相关日志\n")

# 统计所有工具调用
tool_calls = []
npm_count = 0
pip_count = 0

for line_num, content in found_lines:
    try:
        data = json.loads(content)
        msg_data = json.loads(data.get('message', '{}'))
        event = msg_data.get('event', '')
        
        # 查找 run_in_terminal 调用
        if event == 'Executing tool':
            tool_name = msg_data.get('name', '')
            arguments = msg_data.get('arguments', {})
            
            if tool_name == 'run_in_terminal' and isinstance(arguments, dict):
                command = str(arguments.get('command', ''))
                
                # 检查是否是安装命令
                is_npm = 'npm install pptx' in command or 'npm install -g pptx' in command
                is_pip = 'pip install python-pptx' in command or 'pip3 install python-pptx' in command
                
                if is_npm or is_pip:
                    pkg_type = 'npm' if is_npm else 'pip'
                    if is_npm:
                        npm_count += 1
                    else:
                        pip_count += 1
                    
                    tool_calls.append({
                        'line': line_num,
                        'type': pkg_type,
                        'command': command[:100],
                        'output_preview': msg_data.get('output', '')[:100] if 'output' in msg_data else ''
                    })
                    
                    print(f"L{line_num}: {pkg_type.upper()} 安装 (第{npm_count if is_npm else pip_count}次)")
                    print(f"   Command: {command[:120]}")
                    if 'output' in msg_data:
                        output = msg_data['output']
                        if len(output) > 150:
                            output = output[:150] + '...'
                        print(f"   Output preview: {output}")
                    print()
    
    except Exception as e:
        pass

print("=" * 80)
print("统计结果:")
print("-" * 80)
print(f"npm install pptx 执行次数：{npm_count}")
print(f"pip install python-pptx 执行次数：{pip_count}")
print(f"总重复安装次数：{npm_count + pip_count}")

if npm_count > 1 or pip_count > 1:
    print("\n⚠️  检测到重复安装问题！")
    print("\n可能原因:")
    print("1. LLM 没有记住已经安装过依赖包")
    print("2. 每次 ReAct loop 迭代都重新检查并安装")
    print("3. 缺少依赖状态检测机制")
else:
    print("\n✅ 未发现重复安装问题")

print("=" * 80)
