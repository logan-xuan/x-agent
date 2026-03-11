# Phase 2A 验证指南

## ✅ 验证步骤

### Step 1: 验证参数解析逻辑 (已完成)

**测试结果**:
```bash
✅ /demo-skill create test.txt → skill='demo-skill', args='create test.txt'
✅ /pptx → skill='pptx', args=''
✅ /skill-name arg1 arg2 arg3 → skill='skill-name', args='arg1 arg2 arg3'
✅ Hello world → skill='', args='Hello world'
✅ 空字符串处理正确
✅ 多余空格处理正确
```

**结论**: 参数解析逻辑 ✅ 完全正确

---

### Step 2: 前端 UI 测试 (推荐)

#### 方法 1: Web 界面测试

1. **打开浏览器访问**: http://localhost:5173

2. **输入测试命令**:
   ```
   /demo-skill list directory
   ```

3. **观察要点**:
   - LLM 是否识别出这是技能调用
   - 是否读取了 demo-skill 的 SKILL.md
   - 是否正确传递了参数 "list directory"

4. **预期行为**:
   ```
   AI 应该:
   1. 识别出 /demo-skill 命令
   2. 显示技能上下文（描述、参数等）
   3. 根据参数执行相应操作
   ```

#### 方法 2: API 直接测试

使用 curl 命令：
```bash
curl -X POST http://localhost:8888/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "/demo-skill create test.txt",
    "session_id": "test-phase2-001"
  }'
```

---

### Step 3: 后端日志验证

查看实时日志：
```bash
tail -f backend/backend.log | grep -i "skill"
```

**关键日志条目**:
```
✅ "Skill command detected" - 检测到技能命令
✅ "Skill 'demo-skill' loaded" - 加载技能元数据
✅ "Skill Invocation: demo-skill" - 技能上下文注入
```

**示例日志输出**:
```json
{
  "level": "INFO",
  "message": "Skill command detected",
  "extra": {
    "session_id": "xxx",
    "skill_name": "demo-skill",
    "arguments": "create test.txt"
  }
}
```

---

### Step 4: 数据库验证 (可选)

检查会话消息中是否包含技能上下文：

```python
import sqlite3

conn = sqlite3.connect('backend/x-agent.db')
cursor = conn.cursor()

# 查询最近的消息
cursor.execute("""
    SELECT role, content, created_at 
    FROM messages 
    WHERE session_id IN (
        SELECT id FROM sessions 
        ORDER BY created_at DESC 
        LIMIT 1
    )
    AND role = 'system'
    ORDER BY created_at DESC
    LIMIT 5
""")

for row in cursor.fetchall():
    print(f"[{row[2]}] {row[0]}: {row[1][:200]}...")

conn.close()
```

---

## 📊 验收清单

### Phase 2A 功能验收

- [ ] ✅ 参数解析逻辑正确 (6/6 测试通过)
- [ ] ⏳ 前端可以输入 `/command` 格式
- [ ] ⏳ 后端正确解析技能名称和参数
- [ ] ⏳ 技能上下文注入到系统提示
- [ ] ⏳ LLM 能够看到技能信息
- [ ] ⏳ 日志记录技能调用过程

### 文档完整性

- [x] ✅ 实现计划文档
- [x] ✅ 状态总结文档  
- [x] ✅ 完成报告文档
- [x] ✅ 验证指南文档 (本文档)
- [x] ✅ 单元测试用例

---

## 🔍 故障排查

### 问题 1: 参数解析失败

**症状**: 技能名称或参数为空

**排查步骤**:
```bash
# 1. 检查代码是否正确提交
git log --oneline -n 5

# 2. 确认 task_analyzer.py 包含 parse_skill_command
grep -n "parse_skill_command" backend/src/orchestrator/task_analyzer.py

# 3. 重启服务
./restart-services.sh
```

### 问题 2: 技能未找到

**症状**: 日志显示 "Skill 'xxx' not found"

**排查步骤**:
```bash
# 1. 检查技能文件是否存在
ls -la workspace/skills/demo-skill/SKILL.md

# 2. 列出所有可用技能
python3 << 'EOF'
import sys
sys.path.insert(0, 'backend/src')
from services.skill_registry import SkillRegistry
from pathlib import Path

registry = SkillRegistry(Path('workspace'))
skills = registry.list_all_skills()

print(f"发现 {len(skills)} 个技能:")
for skill in skills:
    print(f"  - {skill.name}")
EOF

# 3. 检查工作目录配置
cat backend/x-agent.yaml | grep -A 5 "workspace:"
```

### 问题 3: 上下文未注入

**症状**: LLM 没有响应技能命令

**排查步骤**:
```bash
# 1. 检查 engine.py 修改
grep -A 10 "Step 0.5" backend/src/orchestrator/engine.py

# 2. 检查 _build_messages 修改
grep -A 5 "skill_context_msg" backend/src/orchestrator/engine.py

# 3. 查看详细日志
export LOG_LEVEL=DEBUG
./restart-services.sh
```

---

## 🎯 快速验证脚本

创建一个简单的测试脚本：

```bash
#!/bin/bash
# quick_verify.sh

echo "🧪 Phase 2A 快速验证"
echo "=" * 60

# 1. 检查文件修改
echo "1️⃣ 检查核心文件..."
if grep -q "parse_skill_command" backend/src/orchestrator/task_analyzer.py; then
    echo "   ✅ task_analyzer.py 已修改"
else
    echo "   ❌ task_analyzer.py 未修改"
fi

if grep -q "skill_context_msg" backend/src/orchestrator/engine.py; then
    echo "   ✅ engine.py 已修改"
else
    echo "   ❌ engine.py 未修改"
fi

# 2. 检查服务状态
echo ""
echo "2️⃣ 检查服务状态..."
if curl -s http://localhost:8888/health > /dev/null 2>&1; then
    echo "   ✅ 后端服务运行正常"
else
    echo "   ❌ 后端服务未运行"
fi

# 3. 检查技能文件
echo ""
echo "3️⃣ 检查技能文件..."
if [ -f "workspace/skills/demo-skill/SKILL.md" ]; then
    echo "   ✅ demo-skill 存在"
else
    echo "   ❌ demo-skill 不存在"
fi

echo ""
echo "=" * 60
echo "验证完成！"
```

运行：
```bash
chmod +x quick_verify.sh
./quick_verify.sh
```

---

## 📝 测试记录模板

### 测试用例 1: 基本参数传递

**输入**: `/demo-skill create test.txt`

**期望结果**:
- skill_name: `demo-skill`
- arguments: `create test.txt`
- 技能上下文注入：✅

**实际结果**:
- skill_name: ________
- arguments: ________
- 技能上下文注入：________

**状态**: ⬜ 通过 / ⬜ 失败

---

### 测试用例 2: 无参数命令

**输入**: `/pptx`

**期望结果**:
- skill_name: `pptx`
- arguments: `` (空字符串)
- 技能上下文注入：✅

**实际结果**:
- skill_name: ________
- arguments: ________
- 技能上下文注入：________

**状态**: ⬜ 通过 / ⬜ 失败

---

### 测试用例 3: 非技能命令

**输入**: `你好，请帮我写一首诗`

**期望结果**:
- skill_name: `` (空字符串)
- arguments: `你好，请帮我写一首诗`
- 技能上下文注入：❌ (不应注入)

**实际结果**:
- skill_name: ________
- arguments: ________
- 技能上下文注入：________

**状态**: ⬜ 通过 / ⬜ 失败

---

## 🎉 验证完成标志

当所有以下条件满足时，Phase 2A 验证通过：

- ✅ 参数解析单元测试 6/6 通过
- ✅ 前端可以正常输入 `/command` 格式
- ✅ 后端日志显示技能调用信息
- ✅ 技能上下文正确注入到 LLM
- ✅ LLM 能够根据技能指南执行操作

**预计验证时间**: 10-15 分钟

**下一步**: 根据验证结果决定是否继续实施工具限制功能
