# Phase 2 实施总结

## 📊 当前状态分析

### ✅ 已完成（基础设施）

1. **数据模型** - `SkillMetadata` 已包含所有 Phase 2 字段
   ```python
   # backend/src/models/skill.py
   @dataclass
   class SkillMetadata:
       # Phase 2 fields (lines 42-47)
       disable_model_invocation: bool = False
       user_invocable: bool = True
       argument_hint: str | None = None
       allowed_tools: list[str] | None = None
       context: str | None = None
       license: str | None = None
   ```

2. **解析器** - `SkillParser` 可以解析 YAML 中的 Phase 2 字段
   ```python
   # backend/src/services/skill_parser.py (lines 74-79)
   metadata = SkillMetadata(
       disable_model_invocation=metadata_dict.get('disable-model-invocation', False),
       user_invocable=metadata_dict.get('user-invocable', True),
       argument_hint=metadata_dict.get('argument-hint'),
       allowed_tools=metadata_dict.get('allowed-tools'),
       context=metadata_dict.get('context'),
       license=metadata_dict.get('license'),
   )
   ```

3. **技能注册表** - `SkillRegistry` 已实现基础发现功能
   - 扫描 system skills (`backend/src/skills/`)
   - 扫描 user skills (`workspace/skills/`)
   - 支持优先级覆盖

---

### ⏳ 待实施（核心功能）

#### 1. 参数传递 ($ARGUMENTS) - 🔴 高优先级

**目标**: 支持 `/skill-name arguments` 格式的命令

**需要修改的文件**:
- `backend/src/orchestrator/task_analyzer.py` - 添加命令解析逻辑
- `backend/src/orchestrator/engine.py` - 传递参数到 ReAct Loop
- `backend/src/orchestrator/react_loop.py` - 在工具调用中使用参数

**实施方案**:

```python
# Step 1: 在 TaskAnalyzer 中添加解析函数
def parse_skill_command(user_message: str) -> tuple[str, str]:
    """Parse /command format and extract skill name and arguments."""
    if user_message.startswith('/'):
        parts = user_message[1:].split(' ', 1)
        skill_name = parts[0]
        arguments = parts[1] if len(parts) > 1 else ""
        return skill_name, arguments
    return "", user_message

# Step 2: 在 Orchestrator.process_request 中调用
skill_name, arguments = parse_skill_command(user_message)
if skill_name:
    # Load specific skill context
    skill = skill_registry.get_skill_metadata(skill_name)
    if skill:
        # Pass arguments to ReAct loop
        working_messages.append({
            "role": "system",
            "content": f"🔧 Skill Invocation: {skill_name}\n"
                      f"Arguments: {arguments}\n\n"
                      f"You are now executing the '{skill_name}' skill. "
                      f"Follow its guidelines and use the provided arguments."
        })
```

**验收标准**:
- ✅ 用户可以输入 `/pptx create presentation.pptx`
- ✅ 系统正确解析出 `skill_name="pptx"`, `arguments="create presentation.pptx"`
- ✅ 参数传递给 LLM 并在工具调用中使用

---

#### 2. 工具限制 (allowed-tools) - 🔴 高优先级

**目标**: 当技能指定了 allowed-tools 时，限制 LLM 只能使用这些工具

**需要修改的文件**:
- `backend/src/tools/manager.py` - 添加工具权限检查
- `backend/src/orchestrator/react_loop.py` - 在执行前验证工具权限

**实施方案**:

```python
# Step 1: 在 ToolManager 中添加权限检查
class ToolManager:
    def execute_tool(
        self,
        tool_name: str,
        params: dict[str, Any],
        skill_context: SkillMetadata | None = None
    ) -> ToolResult:
        # Check if tool is allowed
        if skill_context and skill_context.allowed_tools:
            if tool_name not in skill_context.allowed_tools:
                raise ToolNotAllowedError(
                    f"Tool '{tool_name}' is not allowed by skill '{skill_context.name}'. "
                    f"Allowed tools: {', '.join(skill_context.allowed_tools)}"
                )
        
        # ... existing execution logic
```

**验收标准**:
- ✅ 技能可以定义 `allowed-tools: [read_file, write_file]`
- ✅ 尝试使用 `run_in_terminal` 时抛出明确错误
- ✅ 错误信息包含允许的工具列表

---

#### 3. 前端 / 命令菜单 - 🟡 中优先级

**目标**: 输入 `/` 时弹出技能菜单，显示可用技能和参数提示

**需要创建的文件**:
- `frontend/src/components/skills/SkillMenu.tsx`
- `backend/src/api/v1/skills.py` - API endpoint

**实施方案**:

```typescript
// frontend/src/components/skills/SkillMenu.tsx
interface SkillMenuItem {
  name: string;
  description: string;
  shortcut: string;  // e.g., "/pptx"
  argumentHint?: string;  // e.g., "[command] [filename]"
}

// Fetch skills from backend
const { data: skills } = useQuery(['skills'], () => 
  api.get('/api/skills')
);

const menuItems = skills
  .filter(s => s.user_invocable)
  .map(s => ({
    name: s.name,
    description: s.description,
    shortcut: `/${s.name}`,
    argumentHint: s.argument_hint
  }));
```

**API Endpoint**:
```python
# backend/src/api/v1/skills.py
@router.get("/skills")
async def list_skills():
    """List all user-invocable skills with Phase 2 metadata."""
    registry = get_skill_registry()
    skills = registry.list_all_skills()
    
    # Filter and format
    return [
        {
            "name": s.name,
            "description": s.description,
            "argument_hint": s.argument_hint,
            "user_invocable": s.user_invocable,
            "has_scripts": s.has_scripts,
        }
        for s in skills
        if s.user_invocable
    ]
```

---

#### 4. 子目录自动发现 - 🟢 低优先级

**目标**: 递归扫描子目录，发现嵌套的技能

**需要修改的文件**:
- `backend/src/services/skill_registry.py` - `_scan_directory()` 方法

**实施方案**:

```python
def _scan_directory(
    self, 
    directory: Path, 
    level: str = "unknown",
    max_depth: int = 3,
    current_depth: int = 0
) -> list[SkillMetadata]:
    """Scan a directory for skills (with recursive support)."""
    skills = []
    
    if not directory.exists() or not directory.is_dir():
        return skills
    
    # Don't scan too deep
    if current_depth >= max_depth:
        return skills
    
    for item in directory.iterdir():
        if not item.is_dir():
            continue
        
        # Look for SKILL.md
        skill_md = item / "SKILL.md"
        if skill_md.exists():
            try:
                metadata = self._parser.parse(skill_md)
                skills.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to parse skill {item}: {e}")
        
        # Recursively scan subdirectories
        sub_skills = self._scan_directory(
            item, 
            level, 
            max_depth, 
            current_depth + 1
        )
        skills.extend(sub_skills)
    
    return skills
```

---

#### 5. 动态上下文注入 (!`command) - 🟢 低优先级

**目标**: 在 System Prompt 中支持 !`command` 语法，执行结果注入上下文

**需要修改的文件**:
- `backend/src/orchestrator/engine.py` - `_build_messages()` 方法

**实施方案**:

```python
async def inject_dynamic_context(
    system_prompt: str,
    skill_context: SkillMetadata
) -> str:
    """Process dynamic context injection commands."""
    import re
    import subprocess
    
    # Find all !`command` patterns
    pattern = r'!`([^`]+)`'
    matches = re.findall(pattern, system_prompt)
    
    for command_template in matches:
        # Replace variables
        command = command_template.replace(
            '$SKILL_DIR', 
            str(skill_context.path)
        )
        
        # Execute command
        try:
            result = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=skill_context.path
            )
            stdout, stderr = await result.communicate()
            
            if result.returncode == 0:
                # Replace with output
                system_prompt = system_prompt.replace(
                    f'!`{command_template}`',
                    stdout.decode('utf-8').strip()
                )
            else:
                logger.warning(
                    f"Dynamic context command failed: {stderr.decode()}"
                )
        except Exception as e:
            logger.error(f"Dynamic context command error: {e}")
    
    return system_prompt
```

**使用示例**:
```markdown
# In SKILL.md system prompt section

Available scripts in this skill:
!`ls -la scripts/ | grep '\.js$' | awk '{print $9}'`

Current environment:
Python: !`python3 --version`
Node.js: !`node --version`
```

---

## 🎯 实施顺序建议

### Phase 2A (核心功能) - 预计 4 小时

1. **参数传递** (2h)
   - 修改 TaskAnalyzer 添加解析逻辑
   - 在 Orchestrator 中传递参数
   - 编写单元测试
   
2. **工具限制** (1.5h)
   - 在 ToolManager 添加权限检查
   - 创建 ToolNotAllowedError 异常类
   - 编写测试用例

3. **更新示例技能** (0.5h)
   - 为 pptx 技能添加 allowed-tools
   - 添加 argument-hint 示例

### Phase 2B (用户体验) - 预计 3 小时

4. **后端 API** (1h)
   - 创建 `/api/skills` endpoint
   - 返回格式化技能列表

5. **前端菜单** (2h)
   - 创建 SkillMenu 组件
   - 集成到 MessageInput
   - 样式和交互优化

### Phase 2C (增强功能) - 预计 3 小时

6. **子目录发现** (1h)
   - 修改 SkillRegistry 支持递归
   - 添加深度限制
   - 性能优化

7. **动态上下文** (2h)
   - 实现 !`command` 解析器
   - 添加安全限制（白名单机制）
   - 错误处理完善

---

## 📝 立即可执行的行动

### 第一步：验证当前状态

运行以下命令查看现有技能：
```bash
cd /Users/xuan.lx/Documents/x-agent/x-agent/backend
python3 -c "
from src.services.skill_registry import SkillRegistry
from pathlib import Path

registry = SkillRegistry(Path('/Users/xuan.lx/Documents/x-agent/x-agent/workspace'))
skills = registry.list_all_skills()

for skill in skills:
    print(f'{skill.name}:')
    print(f'  - argument_hint: {skill.argument_hint}')
    print(f'  - allowed_tools: {skill.allowed_tools}')
    print()
"
```

### 第二步：实施参数传递

编辑文件：`backend/src/orchestrator/task_analyzer.py`

添加函数：
```python
def parse_skill_command(user_message: str) -> tuple[str, str]:
    """Parse /command format."""
    if user_message.startswith('/'):
        parts = user_message[1:].split(' ', 1)
        skill_name = parts[0]
        arguments = parts[1] if len(parts) > 1 else ""
        return skill_name, arguments
    return "", user_message
```

### 第三步：测试

创建测试技能：
```bash
mkdir -p /Users/xuan.lx/Documents/x-agent/x-agent/workspace/skills/test-skill
cat > /Users/xuan.lx/Documents/x-agent/x-agent/workspace/skills/test-skill/SKILL.md << 'EOF'
---
name: test-skill
description: "Test skill for Phase 2"
argument-hint: "[action] [target]"
allowed-tools: [read_file, write_file]
user-invocable: true
---

# Test Skill

Use this skill to test Phase 2 features.

## Usage

```bash
/test-skill create test.txt
```
EOF
```

---

## ✅ 完成标志

Phase 2 完成后，系统应该能够：

1. ✅ 解析 `/skill-name arguments` 格式
2. ✅ 限制技能只能使用授权的工具
3. ✅ 在前端显示技能菜单
4. ✅ 自动发现嵌套子目录中的技能
5. ✅ 执行动态命令并注入上下文

每个功能都有对应的单元测试和集成测试！🎉
