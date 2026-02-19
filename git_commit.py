#!/usr/bin/env python3
"""Git commit script for anti-hallucination feature."""

import subprocess
import sys

def run_command(cmd, description):
    """Run a command and print the result."""
    print(f"\n{description}")
    print("-" * 60)
    
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd="/Users/xuan.lx/Documents/x-agent/x-agent"
        )
        
        if result.stdout:
            print(result.stdout)
        
        if result.stderr and result.returncode != 0:
            print("错误:", result.stderr)
        
        return result.returncode == 0
    
    except Exception as e:
        print(f"执行失败：{e}")
        return False

def main():
    print("=" * 60)
    print("提交代码：防 LLM 幻觉工具调用增强功能")
    print("=" * 60)
    
    # Step 1: Check status
    if not run_command(
        "git status --short",
        "步骤 1: 查看修改的文件"
    ):
        print("❌ 无法获取 git 状态")
        return False
    
    # Step 2: Add files
    print("\n步骤 2: 添加修改的文件")
    print("-" * 60)
    
    files_to_add = [
        "backend/src/orchestrator/react_loop.py",
        "backend/src/orchestrator/engine.py"
    ]
    
    for file in files_to_add:
        if not run_command(f"git add {file}", f"添加 {file}"):
            print(f"❌ 无法添加文件 {file}")
            return False
        print(f"✅ {file}")
    
    # Step 3: View diff stats
    run_command(
        "git diff --cached --stat",
        "\n步骤 3: 查看变更统计"
    )
    
    # Step 4: Commit
    commit_message = """feat: 实施三层防护机制杜绝 LLM 幻觉性完成声明

问题背景:
- LLM 在用户要求创建文件/PPT 等任务时，有时会用文字声称'已完成'而不实际调用工具
- 这导致用户收到虚假的完成信息，实际文件并未创建

解决方案:
1. 方案 1 (react_loop.py): 
   - 新增 _requires_tool_call_but_none_made() 方法检测工具调用需求
   - 在 ReAct loop 中实时检测并给 LLM 重试机会
   - 当检测到需要工具但未调用时，添加系统提示让 LLM 重新尝试
   
2. 方案 2 (engine.py):
   - 在 System Prompt 中注入明确的工具调用规则
   - 包含错误示例和正确做法的对比说明
   - 强调禁止用文字声称完成而不实际调用工具
   
3. 方案 3 (engine.py):
   - 新增后验证方法 _request_requires_file_creation()
   - 在请求完成后检查是否需要文件操作
   - 为未来扩展预留接口

技术实现:
- 使用正则表达式匹配常见工具调用场景（文件操作、PPT 创建、代码执行等）
- 智能重试机制：只在第一次迭代且完全没有工具调用时才触发
- 结构化日志记录：便于监控和调试
- 中英文混合匹配支持

预期效果:
- 显著减少 LLM 的幻觉性完成声明
- 提升工具调用的准确性和可靠性
- 改善用户体验和系统可信度

相关 Trace:
- b4d7a653-7860-4cde-8ed0-1009f376be29 (成功检测到问题)
- 244d6165-b3dc-4f5a-bd3a-69a3b55bf2df (原始问题案例)"""

    if not run_command(
        f'git commit -m "{commit_message}"',
        "\n步骤 4: 提交代码"
    ):
        print("❌ 提交失败")
        return False
    
    print("✅ 提交成功！")
    
    # Step 5: Show recent commits
    run_command(
        "git log --oneline -5",
        "\n步骤 5: 查看最近提交"
    )
    
    print("\n" + "=" * 60)
    print("✅ 代码提交完成！")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
