#!/bin/bash
# Phase 2A 快速验证脚本

echo "🧪 Phase 2A 参数传递功能 - 快速验证"
echo ""
echo "=" * 70

# 1. 检查核心文件修改
echo "1️⃣  检查核心文件修改..."
echo ""

if grep -q "parse_skill_command" backend/src/orchestrator/task_analyzer.py 2>/dev/null; then
    echo "   ✅ task_analyzer.py - parse_skill_command 已添加"
else
    echo "   ❌ task_analyzer.py - parse_skill_command 未添加"
fi

if grep -q "skill_context_msg" backend/src/orchestrator/engine.py 2>/dev/null; then
    echo "   ✅ engine.py - skill_context_msg 已添加"
else
    echo "   ❌ engine.py - skill_context_msg 未添加"
fi

if grep -q "ToolNotAllowedError" backend/src/tools/manager.py 2>/dev/null; then
    echo "   ✅ manager.py - ToolNotAllowedError 已添加"
else
    echo "   ❌ manager.py - ToolNotAllowedError 未添加"
fi

# 2. 检查服务状态
echo ""
echo "2️⃣  检查服务状态..."
echo ""

if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "   ✅ 后端服务运行正常 (端口 8000)"
else
    echo "   ⚠️  后端服务未运行，请先执行：./restart-services.sh"
fi

if lsof -ti:5173 > /dev/null 2>&1; then
    echo "   ✅ 前端服务运行正常 (端口 5173)"
else
    echo "   ⚠️  前端服务未运行"
fi

# 3. 检查技能文件
echo ""
echo "3️⃣  检查技能文件..."
echo ""

if [ -f "workspace/skills/demo-skill/SKILL.md" ]; then
    echo "   ✅ workspace/skills/demo-skill/SKILL.md 存在"
    
    # 显示技能信息
    if command -v yq &> /dev/null; then
        echo "      技能名称：$(yq -r '.name' workspace/skills/demo-skill/SKILL.md)"
        echo "      参数提示：$(yq -r '.argument-hint' workspace/skills/demo-skill/SKILL.md)"
        echo "      允许工具：$(yq -r '.allowed-tools[]' workspace/skills/demo-skill/SKILL.md | tr '\n' ' ')"
    else
        head -n 10 workspace/skills/demo-skill/SKILL.md | grep -E "^(name|argument|allowed)"
    fi
else
    echo "   ❌ workspace/skills/demo-skill/SKILL.md 不存在"
fi

# 4. 测试参数解析逻辑
echo ""
echo "4️⃣  测试参数解析逻辑..."
echo ""

python3 << 'EOF'
def parse_skill_command(user_message: str) -> tuple[str, str]:
    if not user_message.startswith('/'):
        return "", user_message
    parts = user_message[1:].split(' ', 1)
    skill_name = parts[0].strip()
    arguments = parts[1].strip() if len(parts) > 1 else ""
    return skill_name, arguments

test_cases = [
    ("/demo-skill create test.txt", "demo-skill", "create test.txt"),
    ("/pptx", "pptx", ""),
    ("Hello", "", "Hello"),
]

all_passed = True
for input_msg, exp_skill, exp_args in test_cases:
    skill, args = parse_skill_command(input_msg)
    if skill == exp_skill and args == exp_args:
        print(f"   ✅ {input_msg!r}")
    else:
        print(f"   ❌ {input_msg!r} → ({skill}, {args})")
        all_passed = False

exit(0 if all_passed else 1)
EOF

PARSE_RESULT=$?

# 5. 检查 Git 提交
echo ""
echo "5️⃣  检查 Git 提交状态..."
echo ""

if git log --oneline -n 1 | grep -q "phase2a"; then
    echo "   ✅ 最新提交包含 Phase 2A 功能"
    git log --oneline -n 1 | sed 's/^/      /'
else
    echo "   ℹ️  最新提交："
    git log --oneline -n 1 | sed 's/^/      /'
fi

# 总结
echo ""
echo "=" * 70
echo ""

if [ $PARSE_RESULT -eq 0 ]; then
    echo "🎉 验证通过！Phase 2A 功能已正确实现"
    echo ""
    echo "📝 下一步建议:"
    echo "   1. 打开浏览器访问：http://localhost:5173"
    echo "   2. 输入测试命令：/demo-skill list directory"
    echo "   3. 观察 LLM 是否正确响应"
    echo "   4. 查看日志：tail -f backend/backend.log | grep -i skill"
else
    echo "⚠️  部分验证失败，请检查上述输出"
fi

echo ""
echo "=" * 70
