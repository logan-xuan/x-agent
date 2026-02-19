# Phase 2 实现计划

## 目标功能

根据原始规划，Phase 2 需要实现以下核心功能：

### 1. ✅ 参数传递 ($ARGUMENTS)
**状态**: 部分实现，需要完善

**当前实现**:
- `argument_hint` 字段已定义在 SkillMetadata 中
- 但尚未在实际调用中传递参数

**需要实现**:
```python
# 在 Orchestrator 中解析用户命令的参数
# 例如：/pptx create my_presentation.pptx
# 参数 "create my_presentation.pptx" 需要传递给技能

def parse_skill_command(user_input: str) -> tuple[str, str]:
    """Parse /command and extract skill name and arguments."""
    if user_input.startswith('/'):
        parts = user_input[1:].split(' ', 1)
        skill_name = parts[0]
        arguments = parts[1] if len(parts) > 1 else ""
        return skill_name, arguments
    return user_input, ""
```

---

### 2. ⏳ 工具限制 (allowed-tools)
**状态**: 字段已定义，未实现执行逻辑

**当前实现**:
- `allowed_tools` 字段已在 SkillMetadata 中定义
- SkillParser 可以解析 YAML 中的 `allowed-tools` 字段

**需要实现**:
```python
# 在 ReAct Loop 中检查工具权限
def execute_tool(tool_name: str, skill_context: SkillContext):
    if skill_context.allowed_tools and tool_name not in skill_context.allowed_tools:
        raise ToolNotAllowedError(
            f"Tool '{tool_name}' is not allowed by skill '{skill_context.name}'"
        )
    # ... execute tool
```

**示例 SKILL.md 配置**:
```yaml
---
name: secure-analysis
description: "Secure file analysis with restricted tools"
allowed-tools: [read_file, list_dir]
---
```

---

### 3. ⏳ 前端 / 命令菜单
**状态**: 未实现

**需要实现**:
```typescript
// frontend/src/components/skills/SkillMenu.tsx
interface SkillMenuItem {
  name: string;
  description: string;
  shortcut: string;  // e.g., "/pptx"
  argumentHint?: string;  // e.g., "[command] [filename]"
}

// 从后端获取技能列表
const skills = await api.getSkills();
const menuItems = skills
  .filter(s => s.user_invocable)
  .map(s => ({
    name: s.name,
    description: s.description,
    shortcut: `/${s.name}`,
    argumentHint: s.argument_hint
  }));
```

**UI 设计**:
```
输入框弹出菜单:
/p  [自动补全]
├─ /pptx - Presentation creation...
├─ /pdf - PDF document analysis...
└─ /web-search - Web search...
```

---

### 4. ⏳ 子目录自动发现
**状态**: 已实现基础功能，需要增强

**当前实现**:
- SkillRegistry._scan_directory() 扫描一级子目录
- 只查找直接的 SKILL.md

**需要增强**:
```python
def _scan_directory(self, directory: Path, level: str = "unknown", depth: int = 0):
    """支持递归扫描子目录"""
    max_depth = 3  # 限制最大深度
    
    for item in directory.iterdir():
        if not item.is_dir():
            continue
        
        # 查找 SKILL.md
        skill_md = item / "SKILL.md"
        if skill_md.exists():
            # 找到技能
            metadata = self._parser.parse(skill_md)
            skills.append(metadata)
        
        # 递归扫描子目录 (如果未达到最大深度)
        if depth < max_depth:
            sub_skills = self._scan_directory(item, level, depth + 1)
            skills.extend(sub_skills)
```

---

### 5. ⏳ 动态上下文注入 (!`command)
**状态**: 未实现

**设计**:
- 支持在 System Prompt 中嵌入动态内容
- 使用特殊语法 !`command` 触发命令执行
- 将执行结果注入到上下文中

**实现方案**:
```python
async def inject_dynamic_context(system_prompt: str, skill_context: SkillContext) -> str:
    """Process dynamic context injection commands."""
    import re
    import subprocess
    
    # 查找所有 !`command` 模式
    pattern = r'!`([^`]+)`'
    matches = re.findall(pattern, system_prompt)
    
    for command_template in matches:
        # 替换变量
        command = command_template.replace('$SKILL_DIR', str(skill_context.path))
        
        # 执行命令
        try:
            result = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=skill_context.path
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # 替换为执行结果
                system_prompt = system_prompt.replace(
                    f'!`{command_template}`',
                    stdout.decode('utf-8')
                )
            else:
                logger.warning(f"Dynamic context command failed: {stderr}")
        except Exception as e:
            logger.error(f"Dynamic context command error: {e}")
    
    return system_prompt
```

**使用示例**:
```markdown
# 在 SKILL.md 的 System Prompt 中

你可以使用以下工具：!`ls -la scripts/ | grep '\.js$'`

当前可用脚本:
!`find . -name "*.py" -type f | head -n 10`
```

---

## 实施顺序和优先级

### 🔴 高优先级（立即实现）

1. **参数传递 ($ARGUMENTS)** - 核心功能
   - 文件：orchestrator/engine.py, orchestrator/task_analyzer.py
   - 预计工作量：2 小时
   
2. **工具限制 (allowed-tools)** - 安全功能
   - 文件：orchestrator/react_loop.py, tools/manager.py
   - 预计工作量：1.5 小时

### 🟡 中优先级

3. **前端 / 命令菜单** - 用户体验
   - 文件：frontend/src/components/skills/, backend/api/v1/skills.py
   - 预计工作量：3 小时

### 🟢 低优先级

4. **子目录自动发现** - 增强功能
   - 文件：services/skill_registry.py
   - 预计工作量：1 小时

5. **动态上下文注入** - 高级功能
   - 文件：orchestrator/engine.py
   - 预计工作量：2 小时

---

## 测试计划

### 单元测试

```python
# test_phase2_features.py

class TestSkillArguments:
    def test_parse_arguments(self):
        skill_name, args = parse_skill_command("/pptx create test.pptx")
        assert skill_name == "pptx"
        assert args == "create test.pptx"
    
    def test_no_arguments(self):
        skill_name, args = parse_skill_command("/pptx")
        assert skill_name == "pptx"
        assert args == ""

class TestAllowedTools:
    def test_allowed_tool_execution(self):
        skill = SkillMetadata(
            name="test",
            description="Test skill",
            path=Path("/tmp"),
            allowed_tools=["read_file", "list_dir"]
        )
        
        # Should succeed
        execute_tool("read_file", skill)
        
        # Should fail
        with pytest.raises(ToolNotAllowedError):
            execute_tool("run_in_terminal", skill)
```

### 集成测试

```python
# test_integration_phase2.py

class TestSkillInvocationWithArguments:
    def test_full_workflow(self):
        """Test complete workflow with arguments"""
        # User types: "/pptx create presentation.pptx"
        response = await client.post("/api/chat", {
            "message": "/pptx create presentation.pptx"
        })
        
        # Should:
        # 1. Parse skill name "pptx" and arguments "create presentation.pptx"
        # 2. Load skill context
        # 3. Check allowed tools
        # 4. Execute with arguments
```

---

## 验收标准

### Phase 2A (参数 + 工具限制)

- ✅ 用户可以输入 `/skill-name arguments`
- ✅ 参数正确传递给技能执行
- ✅ allowed-tools 限制生效
- ✅ 尝试使用未授权工具时抛出明确错误

### Phase 2B (前端菜单 + 子目录)

- ✅ 输入 `/` 弹出技能菜单
- ✅ 显示技能描述和参数提示
- ✅ 自动发现嵌套子目录中的技能

### Phase 2C (动态上下文)

- ✅ !`command` 语法被正确解析
- ✅ 命令执行结果注入到系统提示
- ✅ 错误处理完善

---

## 风险和挑战

### 已知风险

1. **安全性**: 动态上下文注入可能被滥用
   - 缓解措施：限制可执行的命令类型，添加白名单机制

2. **性能**: 每次请求都解析技能可能较慢
   - 缓解措施：增强缓存机制，TTL 从 5 分钟降至 2 分钟

3. **复杂性**: 参数传递可能与现有消息处理冲突
   - 缓解措施：在 TaskAnalyzer 中添加专门的解析逻辑

---

## 下一步行动

### 立即开始

1. **实现参数传递** (2h)
   - 修改 TaskAnalyzer 解析 /command
   - 在 Orchestrator 中传递 arguments
   - 编写单元测试

2. **实现工具限制** (1.5h)
   - 在 ReAct Loop 中添加工具权限检查
   - 创建 ToolNotAllowedError 异常类
   - 编写测试用例

3. **更新技能文档** (0.5h)
   - 为 pptx 技能添加 allowed-tools
   - 添加 argument-hint 示例
   - 验证解析正确

完成以上 3 步后，Phase 2 核心功能即可用！🎉
