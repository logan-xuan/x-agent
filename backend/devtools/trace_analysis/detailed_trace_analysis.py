#!/usr/bin/env python3
"""Detailed analysis of trace f861b6ff-4c48-4487-a4a4-3566e4bbaad8."""

import json
from pathlib import Path

print("=" * 80)
print("详细分析：html2pptx is not a function 错误")
print("=" * 80)

# 查看 x-agent.log 中的命令执行
log_file = Path('logs/x-agent.log')
trace_id = 'f861b6ff-4c48-4487-a4a4-3566e4bbaad8'

commands_executed = []

with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if trace_id in line:
            try:
                data = json.loads(line)
                msg_data = json.loads(data.get('message', '{}'))
                event = msg_data.get('event', '')
                
                # 查找终端命令执行
                if event == 'Executing terminal command' and 'command' in msg_data:
                    cmd = msg_data['command']
                    if isinstance(cmd, str) and ('node' in cmd or '.js' in cmd):
                        commands_executed.append({
                            'timestamp': data.get('timestamp'),
                            'command': cmd,
                            'output': msg_data.get('output', ''),
                            'error': msg_data.get('error', '')
                        })
            except:
                pass

print(f"\n找到 {len(commands_executed)} 次 Node.js 相关命令执行\n")

for i, cmd_info in enumerate(commands_executed, 1):
    print(f"[{i}] {cmd_info['timestamp'][:22] if cmd_info['timestamp'] else 'N/A'}")
    print(f"    Command: {cmd_info['command'][:150]}")
    if cmd_info['error']:
        error_text = str(cmd_info['error'])
        print(f"    ERROR: {error_text[:200]}")
    if cmd_info['output']:
        output_text = str(cmd_info['output'])
        if 'TypeError' in output_text or 'Error' in output_text:
            print(f"    OUTPUT (has error): {output_text[:200]}")
    print()

# 查看 LLM 的响应
print("\n" + "=" * 80)
print("LLM 响应分析")
print("=" * 80)

llm_log = Path('logs/prompt-llm.log')
llm_responses = []

with open(llm_log, 'r', encoding='utf-8') as f:
    for line in f:
        if trace_id in line:
            try:
                data = json.loads(line)
                response = data.get('response', '')
                if len(response) > 50:
                    llm_responses.append({
                        'timestamp': data.get('timestamp'),
                        'response': response
                    })
            except:
                pass

print(f"\n找到 {len(llm_responses)} 次 LLM 响应\n")

# 查找提到 html2pptx 或 JavaScript 的响应
for i, resp in enumerate(llm_responses, 1):
    response_lower = resp['response'].lower()
    
    if 'html2pptx' in response_lower or 'javascript' in response_lower or 'node.js' in response_lower:
        print(f"[{i}] {resp['timestamp'][:22] if resp['timestamp'] else 'N/A'}")
        
        # 检查是否包含代码
        has_code = '```' in resp['response']
        if has_code:
            print(f"    ⚠️  包含代码块")
            
            # 提取第一段代码
            code_start = resp['response'].find('```')
            if code_start != -1:
                code_end = resp['response'].find('```', code_start + 3)
                if code_end != -1:
                    code_block = resp['response'][code_start:code_end + 3]
                    lines = code_block.split('\n')
                    preview = '\n'.join(lines[:5])
                    print(f"    Code preview:\n{preview}")
                    if len(lines) > 5:
                        print(f"    ... ({len(lines) - 5} more lines)")
        print()

print("\n" + "=" * 80)
print("诊断结论")
print("=" * 80)

if len(commands_executed) > 1:
    print("\n⚠️  检测到重复执行相同的命令！")
    print("\n根本原因:")
    print("1. JavaScript 代码中 html2pptx 未正确导入")
    print("2. 可能缺少 require('pptxgenjs') 或 const html2pptx = require(...)")
    print("3. LLM 生成的代码有语法错误")
    print("4. 每次失败后 LLM 重试但没有修复正确的导入")
    
    # 检查是否有不同的命令
    unique_commands = set(cmd['command'][:100] for cmd in commands_executed)
    if len(unique_commands) < len(commands_executed):
        print("\n📊 统计:")
        print(f"   总执行次数：{len(commands_executed)}")
        print(f"   不同命令数：{len(unique_commands)}")
        print(f"   → LLM 在重复执行相同或相似的命令")
else:
    print("\n✅ 命令执行次数正常")

print("\n" + "=" * 80)
