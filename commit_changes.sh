#!/bin/bash

# X-Agent 防 LLM 幻觉工具调用增强功能 - 代码提交脚本

echo "======================================"
echo "提交：防 LLM 幻觉工具调用增强功能"
echo "======================================"
echo ""

cd /Users/xuan.lx/Documents/x-agent/x-agent

echo "1. 查看修改的文件..."
git status --short

echo ""
echo "2. 添加修改的文件..."
git add backend/src/orchestrator/react_loop.py
git add backend/src/orchestrator/engine.py

echo ""
echo "3. 查看变更内容..."
git diff --cached --stat

echo ""
echo "4. 提交代码..."
git commit -m "feat: 实施三层防护机制杜绝 LLM 幻觉性完成声明

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
- 244d6165-b3dc-4f5a-bd3a-69a3b55bf2df (原始问题案例)"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 提交成功！"
    echo ""
    echo "5. 查看提交历史..."
    git log --oneline -5
else
    echo ""
    echo "❌ 提交失败"
    exit 1
fi

echo ""
echo "======================================"
echo "提交完成"
echo "======================================"
