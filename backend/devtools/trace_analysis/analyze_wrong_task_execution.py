#!/usr/bin/env python3
"""Analyze trace 62e57d67-b8db-4b47-8fa2-7396e062f9b0 for wrong task execution."""

import json
from pathlib import Path

log_file = Path('/Users/xuan.lx/Documents/x-agent/x-agent/backend/logs/x-agent.log')
trace_id = '62e57d67-b8db-4b47-8fa2-7396e062f9b0'

print("=" * 80)
print(f"分析 Trace: {trace_id}")
print("=" * 80)

# 查找所有用户消息和工具调用
events = []

with open(log_file, 'r', encoding='utf-8') as f:
    for line in f:
        if trace_id in line:
            try:
                data = json.loads(line)
                msg_data = json.loads(data.get('message', '{}'))
                event = msg_data.get('event', '')
                timestamp = data.get('timestamp', '')
                
                # 收集用户消息
                if event == 'User message received':
                    events.append({
                        'timestamp': timestamp,
                        'event': 'USER_MESSAGE',
                        'content': msg_data.get('content', '')
                    })
                
                # 收集工具调用
                elif event == 'Executing terminal command':
                    events.append({
                        'timestamp': timestamp,
                        'event': 'TOOL_CALL',
                        'command': msg_data.get('command', '')
                    })
                
                # 收集 LLM 响应
                elif 'ReAct loop' in event or 'tool_call' in event:
                    events.append({
                        'timestamp': timestamp,
                        'event': event,
                        'data': msg_data
                    })
                
                # 收集重规划事件
                elif 'replan' in event.lower() or 'milestone' in event.lower():
                    events.append({
                        'timestamp': timestamp,
                        'event': event,
                        'data': msg_data
                    })
            
            except:
                pass

# 按时间排序显示
print(f"\n共找到 {len(events)} 个关键事件\n")

user_messages = []
tool_calls = []

for i, item in enumerate(events, 1):
    ts = item['timestamp'][:22] if item['timestamp'] else 'N/A'
    event = item['event']
    
    print(f"{i:3}. [{ts}] {event}")
    
    if event == 'USER_MESSAGE':
        content = item['content']
        user_messages.append(content)
        preview = content[:100] if len(content) > 100 else content
        print(f"      Content: {preview}...")
    
    elif event == 'TOOL_CALL':
        command = item['command']
        tool_calls.append(command)
        preview = command[:100] if len(command) > 100 else command
        print(f"      Command: {preview}")
    
    elif 'replan' in event.lower():
        reason = item['data'].get('reason', '')
        print(f"      Reason: {reason[:100]}")
    
    elif 'milestone' in event.lower():
        status = item['data'].get('status', '')
        print(f"      Status: {status}")
    
    print()

print("\n" + "=" * 80)
print("问题诊断")
print("=" * 80)

print(f"\n用户消息数量：{len(user_messages)}")
print(f"工具调用数量：{len(tool_calls)}")

if len(user_messages) > 1:
    print("\n📝 所有用户消息:")
    for i, msg in enumerate(user_messages, 1):
        print(f"\n[{i}] {msg[:150]}...")

if len(tool_calls) > 0:
    print("\n🔧 所有工具调用:")
    for i, cmd in enumerate(tool_calls, 1):
        print(f"\n[{i}] {cmd[:150]}")

# 检查是否有 PPT 相关命令
ppt_commands = [cmd for cmd in tool_calls if 'ppt' in cmd.lower() or 'pptx' in cmd.lower()]
if ppt_commands:
    print("\n⚠️  检测到 PPT 相关命令:")
    for cmd in ppt_commands:
        print(f"   - {cmd[:100]}")

print("\n" + "=" * 80)
print("可能的根本原因:")
print("=" * 80)

print("""
1. **上下文记忆混淆**
   - 系统可能保留了之前的对话历史
   - LLM 在执行时参考了旧的上下文而非最新请求

2. **重规划导致任务回退**
   - 如果第一次创建失败触发重规划
   - LLM 可能回退到之前成功的计划模板

3. **技能文档路径依赖**
   - pptx 技能文档中可能有示例代码
   - LLM 直接复制了示例中的春节旅游主题

4. **工作区文件残留**
   - 之前创建的 PPT 文件仍在工作区
   - LLM 误以为需要继续处理旧文件

建议的解决方案:
1. 在每次新请求时清空短期记忆
2. 重规划时明确更新任务目标
3. 技能文档使用通用示例，避免具体主题
4. 执行前检查工作区，清理或重命名旧文件
""")

print("\n" + "=" * 80)
