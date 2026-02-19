#!/usr/bin/env python3
"""Analyze trace c80c57c5-73ff-42c5-b0ea-bb864ba0f572 for repeated pip install errors."""

import json
from pathlib import Path

log_file = Path('/Users/xuan.lx/Documents/x-agent/x-agent/backend/logs/x-agent.log')
trace_id = 'c80c57c5-73ff-42c5-b0ea-bb864ba0f572'

print("=" * 80)
print(f"分析 Trace: {trace_id}")
print("=" * 80)

found_lines = []
with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if trace_id in line:
            found_lines.append(line.strip())

print(f"\n找到 {len(found_lines)} 条相关日志\n")

# 统计所有 pip install 相关事件
pip_installs = []
errors = []
confirmations = []

for content in found_lines:
    try:
        data = json.loads(content)
        msg_data = json.loads(data.get('message', '{}'))
        event = msg_data.get('event', '')
        timestamp = data.get('timestamp', '')
        
        # 查找 pip install 命令
        if event == 'Executing terminal command' or event == 'Executing tool':
            command = msg_data.get('command', '')
            if isinstance(command, str) and 'pip install python-pptx' in command:
                pip_installs.append({
                    'timestamp': timestamp,
                    'event': event,
                    'command': command,
                    'output': msg_data.get('output', ''),
                    'error': msg_data.get('error', '')
                })
                
                print(f"\n[{'✅' if not msg_data.get('error') else '❌'}] {timestamp[:22] if timestamp else 'N/A'}")
                print(f"Event: {event}")
                print(f"Command: {command}")
                
                if msg_data.get('output'):
                    output = msg_data['output']
                    print(f"Output ({len(output)} chars):")
                    if len(output) > 300:
                        print(f"  {output[:300]}...")
                    else:
                        print(f"  {output}")
                
                if msg_data.get('error'):
                    error = msg_data['error']
                    print(f"ERROR: {error}")
                
                print("-" * 80)
        
        # 查找确认相关事件
        if 'confirmation' in event.lower() or 'high-risk' in event.lower():
            confirmations.append({
                'timestamp': timestamp,
                'event': event,
                'data': msg_data
            })
        
        # 收集错误
        if 'error' in msg_data and msg_data['error']:
            errors.append({
                'timestamp': timestamp,
                'event': event,
                'error': str(msg_data['error'])[:200]
            })
    
    except Exception as e:
        pass

# 统计信息
print("\n" + "=" * 80)
print("统计信息")
print("=" * 80)
print(f"\npip install python-pptx 执行次数：{len(pip_installs)}")
print(f"错误数量：{len(errors)}")
print(f"确认相关事件：{len(confirmations)}")

if len(pip_installs) > 1:
    print("\n⚠️  检测到重复安装！")
    
    # 检查是否有不同的命令
    unique_commands = set(cmd['command'][:100] for cmd in pip_installs)
    print(f"不同命令数：{len(unique_commands)}")
    
    # 检查成功/失败情况
    successful = sum(1 for cmd in pip_installs if not cmd.get('error'))
    failed = sum(1 for cmd in pip_installs if cmd.get('error'))
    
    print(f"成功：{successful} 次")
    print(f"失败：{failed} 次")
    
    if failed > 0:
        print("\n❌ 失败原因:")
        for i, cmd in enumerate(pip_installs, 1):
            if cmd.get('error'):
                print(f"\n[{i}] {cmd['timestamp'][:22] if cmd['timestamp'] else 'N/A'}")
                print(f"    Error: {cmd['error']}")
else:
    print("\n✅ 只安装了一次，没有重复")

# 查看 LLM 响应
print("\n" + "=" * 80)
print("LLM 响应分析")
print("=" * 80)

llm_log = Path('/Users/xuan.lx/Documents/x-agent/x-agent/backend/logs/prompt-llm.log')
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
                        'response': response
                    })
            except:
                pass

print(f"\n找到 {len(llm_calls)} 次 LLM 调用\n")

# 查找提到安装的响应
for i, resp in enumerate(llm_calls, 1):
    response_lower = resp['response'].lower()
    
    if 'install' in response_lower or '安装' in response_lower:
        print(f"[{i}] {resp['timestamp'][:22] if resp['timestamp'] else 'N/A'}")
        
        # 提取关键句子
        lines = resp['response'].split('\n')
        for line in lines:
            if 'install' in line.lower() or '安装' in line:
                if len(line) > 150:
                    print(f"  ...{line[:150]}...")
                else:
                    print(f"  {line}")
        print()

print("\n" + "=" * 80)
print("诊断结论")
print("=" * 80)

if len(pip_installs) > 1:
    print("\n🔍 可能的根本原因:")
    print("1. LLM 没有记住已经安装过依赖包")
    print("2. 每次 ReAct loop 迭代或重规划后都重新尝试安装")
    print("3. 缺少依赖状态检测机制（应该先 pip show 检查）")
    print("4. 高危命令确认流程导致延迟，被误判为失败")
    print("5. 技能文档没有明确说明要先检查再安装")
    
    print("\n💡 建议的解决方案:")
    print("1. 在技能文档中添加依赖检查指导（已实施）")
    print("2. 添加详细日志记录每次安装的触发原因")
    print("3. 实现依赖状态缓存机制")
    print("4. 优化高危命令确认超时处理")
else:
    print("\n✅ 安装次数正常，可能是其他原因导致的问题")

print("\n" + "=" * 80)
