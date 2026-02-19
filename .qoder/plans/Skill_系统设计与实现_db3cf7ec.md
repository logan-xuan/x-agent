# X-Agent Skill 系统设计与实现计划（基于 Anthropic 标准）

## 一、Skill 的精确定义

### Skill 是什么

**Skill（技能）** = 一个包含指令、脚本和资源的文件夹，Agent 可以发现和使用来完成任务

**本质**：
- 对 Agent 能力的**模块化扩展**
- 提供程序知识和特定上下文（Domain Expertise）
- 将多步任务转变为可重复、可审计的工作流

**核心优势**：
1. 赋予 Agent 新的能力（New Capabilities）
2. 提供特定领域知识（Domain Expertise）
3. 支持跨多个 AI 工具的互操作性（Interoperability）

---

## 二、Skill 的发现和加载机制

### 2.1 发现方式

| 发现方式 | 工作原理 | X-Agent 实现策略 |
|---------|---------|-----------------|
| **自动发现** | LLM 根据 description 中的关键词判断何时激活 Skill | System Prompt 注入 metadata，LLM 自主匹配 |
| **手动调用** | 用户键入 `/skill-name [arguments]` 直接调用 | 前端支持 `/` 命令菜单（Phase 2） |
| **嵌套目录自动发现** | 在子目录编辑时，自动扫描该目录的 `.claude/skills/` | 支持 `workspace/skills/` 和项目级 `.x-agent/skills/` |

### 2.2 加载位置的优先级

```
项目级别 (./.x-agent/skills/) → 个人级别 (~/.x-agent/skills/) → 工作空间级别 (workspace/skills/)
```

**同名 Skill 遵循"就近优先"原则**。

### 2.3 三层上下文加载策略（节省 Token）

| 阶段 | 内容 | Token 消耗 | 触发时机 |
|------|------|-----------|---------|
| **元数据** | name + description | ~100 tokens | 启动时加载所有 |
| **完整内容** | SKILL.md body | <5000 tokens | Skill 被激活时 |
| **按需资源** | scripts/, references/, assets/ | 无限制 | 需要时才加载 |

---

## 三、X-Agent Skill 结构规范

### 3.1 最小化结构（必需）

```
my-skill/
└── SKILL.md    # 必需 - 包含 YAML 前置元数据 + Markdown 说明
```

### 3.2 完整结构（推荐）

```
my-skill/
├── SKILL.md                    # 入口点（必需）
│   └── 100-200 行核心说明
├── references/                 # 详细参考文档（按需加载）
│   ├── REFERENCE.md           # API 文档、技术细节
│   ├── FORMS.md               # 表单模板、数据格式
│   └── domain-specific.md     # 领域特定文档
├── examples/                   # 示例输出
│   └── sample.md              # 预期输出格式示例
├── templates/                  # 模板文件
│   └── document-template.md
├── scripts/                    # 可执行脚本（LLM 可调用）
│   ├── validate.sh
│   ├── extract.py
│   └── helper.py
└── assets/                     # 静态资源
    ├── diagram.png            # 图表、图片
    └── lookup-table.json      # 查找表、模式
```

**推荐容量管理**：
- SKILL.md 保持在 500 行以下
- 详细文档拆分到 references/ 目录
- 复杂逻辑放在 scripts/ 中

---

## 四、SKILL.md 的前置元数据规范

### 4.1 必需字段

```yaml
---
name: skill-name              # 小写字母/数字/连字符，1-64 字符
description: What this skill does and when to use it  # 1-1024 字符
---
```

### 4.2 Phase 2 可选字段（扩展功能）

| 字段 | 用途 | 示例值 |
|------|------|--------|
| `disable-model-invocation` | 防止 LLM 自动触发，仅用户手动调用 | `true` |
| `user-invocable` | 从 `/` 菜单隐藏，仅 LLM 可用 | `false` |
| `argument-hint` | 自动完成提示 | `[filename] [format]` |
| `allowed-tools` | 此 Skill 激活时允许的工具列表 | `Read, Grep, Bash(git:*)` |
| `context` | 指定执行上下文 | `fork` (隔离执行) |
| `license` | 许可证 | `Apache-2.0` 或 `Proprietary` |

### 4.3 调用控制矩阵

| 前置元数据配置 | 用户可调用 | LLM 可调用 | 何时加载到上下文 |
|---------------|-----------|-----------|-----------------|
| (默认) | ✅ 是 | ✅ 是 | 描述始终，完整内容按需 |
| disable-model-invocation | ✅ 是 | ❌ 否 | 描述不加载，用户调用时加载 |
| user-invocable: false | ❌ 否 | ✅ 是 | 描述始终，完整内容按需 |

---

## 五、架构设计

### 5.1 四层架构

#### Layer 1: Skill Metadata Registry（元数据注册层）
**职责**：技能发现与描述
- 扫描 `backend/src/skills/`、`workspace/skills/`、`.x-agent/skills/`
- 提取 `SKILL.md` YAML frontmatter（name, description, optional fields）
- 构建技能注册表，供 System Prompt 注入使用

**实现位置**：`backend/src/services/skill_registry.py`

#### Layer 2: Skill Content Loader（内容加载层）
**职责**：按需加载 Skill 完整内容
- 懒加载 SKILL.md body（仅在激活时）
- 支持 references/ 文件的按需读取
- 缓存已加载内容（避免重复加载）

**实现位置**：`backend/src/services/skill_loader.py`

#### Layer 3: Script Executor（脚本执行层）
**职责**：安全执行 Skill 脚本
- 支持 Python/Bash/Node.js 脚本执行
- 参数传递和环境变量注入
- 沙箱环境与工具权限控制

**实现位置**：`backend/src/services/skill_executor.py`

#### Layer 4: System Prompt Injector（系统提示注入层）
**职责**：将技能 metadata 注入到 LLM
- 在 `_build_messages()` 中，添加技能列表到 System Prompt
- 支持调用控制（哪些技能可见、哪些隐藏）
- Token 预算管理（避免超限）

**实现位置**：修改 `orchestrator/engine.py` 的 `_build_messages()` 方法

---

## 六、实现步骤（分阶段）

### Phase 1: 核心基础（MVP）

#### Task 1.1: 创建 Skill Metadata 模型
**文件**：`backend/src/models/skill.py`

```python
@dataclass
class SkillMetadata:
    """Skill 元数据（YAML frontmatter）"""
    name: str                              # 必需：技能名称
    description: str                       # 必需：技能描述
    path: Path                            # 技能目录路径
    has_scripts: bool = False             # 是否有 scripts/目录
    has_references: bool = False          # 是否有 references/目录
    has_assets: bool = False              # 是否有 assets/目录
    
    # Phase 2 可选字段
    disable_model_invocation: bool = False
    user_invocable: bool = True
    argument_hint: str | None = None
    allowed_tools: list[str] | None = None
    context: str | None = None
    license: str | None = None
```

#### Task 1.2: 实现 Skill Metadata 解析器
**文件**：`backend/src/services/skill_parser.py`

**核心功能**：
- 解析 SKILL.md 的 YAML frontmatter
- 验证必需字段（name, description）
- 检测目录结构（scripts/, references/, assets/）
- 返回 SkillMetadata 对象

**示例代码**：
```python
def parse_skill_metadata(skill_md_path: Path) -> SkillMetadata:
    content = skill_md_path.read_text(encoding='utf-8')
    
    # 解析 YAML frontmatter
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            yaml_content = parts[1]
            metadata = yaml.safe_load(yaml_content)
    
    # 验证必需字段
    if 'name' not in metadata:
        raise ValueError(f"SKILL.md must have 'name' field: {skill_md_path}")
    if 'description' not in metadata:
        raise ValueError(f"SKILL.md must have 'description' field: {skill_md_path}")
    
    # 检测目录结构
    skill_dir = skill_md_path.parent
    has_scripts = (skill_dir / 'scripts').exists()
    has_references = (skill_dir / 'references').exists()
    has_assets = (skill_dir / 'assets').exists()
    
    return SkillMetadata(
        name=metadata['name'],
        description=metadata['description'],
        path=skill_dir,
        has_scripts=has_scripts,
        has_references=has_references,
        has_assets=has_assets,
        # Phase 2 字段
        disable_model_invocation=metadata.get('disable-model-invocation', False),
        user_invocable=metadata.get('user-invocable', True),
        argument_hint=metadata.get('argument-hint'),
        allowed_tools=metadata.get('allowed-tools'),
        context=metadata.get('context'),
        license=metadata.get('license'),
    )
```

#### Task 1.3: 实现 Skill Registry
**文件**：`backend/src/services/skill_registry.py`

**核心功能**：
- `discover_skills()`: 扫描三个目录，返回技能列表
- `get_skill_metadata(name)`: 获取单个技能的元数据
- `list_all_skills()`: 列出所有可用技能（支持过滤）
- `reload_if_changed()`: 热重载支持

**扫描逻辑**：
```python
def discover_all_skills(workspace_path: Path) -> list[SkillMetadata]:
    """扫描所有技能目录，返回技能列表（支持优先级覆盖）"""
    
    # 定义扫描路径（优先级从高到低）
    scan_paths = [
        (workspace_path / ".x-agent" / "skills", "project"),      # 最高优先级
        (workspace_path / "skills", "workspace"),                 # 中等优先级
        (BACKEND_PATH / "src" / "skills", "system"),              # 最低优先级
    ]
    
    skills: dict[str, SkillMetadata] = {}
    
    for skill_dir, level in scan_paths:
        if not skill_dir.exists():
            continue
            
        for item in skill_dir.iterdir():
            if not item.is_dir():
                continue
                
            skill_md = item / "SKILL.md"
            if not skill_md.exists():
                continue
            
            try:
                metadata = parse_skill_metadata(skill_md)
                skills[metadata.name] = metadata  # 高优先级覆盖低优先级
                logger.info(
                    f"Discovered {level} skill: {metadata.name}",
                    extra={"path": str(item)}
                )
            except Exception as e:
                logger.warning(
                    f"Failed to parse skill {item.name}: {e}"
                )
    
    return list(skills.values())
```

#### Task 1.4: 集成到 Orchestrator
**文件**：`backend/src/orchestrator/engine.py`

**修改点**：

##### A. 初始化 Skill Registry
```python
def __init__(self, workspace_path: str, ...) -> None:
    # ... 现有代码 ...
    
    # 新增：Skill Registry
    from ..services.skill_registry import SkillRegistry
    self._skill_registry = SkillRegistry(Path(workspace_path))
```

##### B. 修改 System Prompt 构建
在 `_build_messages()` 方法中，tools 列表之后添加：

```python
# Add tools
tools = self._tool_manager.get_all_tools()
if tools:
    tool_names = [t.name for t in tools]
    system_parts.append(f"\n# 可用工具\n你可以使用以下工具：{', '.join(tool_names)}")
    # Add explicit instruction for tool usage
    system_parts.append("\n# 工具使用规则\n**重要：当用户要求执行任何操作时，你必须立即调用相应的工具，而不是用文字询问用户确认。**\n例如：\n- 用户要求删除文件 → 直接调用 run_in_terminal 工具执行 rm 命令\n- 用户要求创建目录 → 直接调用 run_in_terminal 工具执行 mkdir 命令\n- 用户要求移动文件 → 直接调用 run_in_terminal 工具执行 mv 命令\n\n不要用文字询问用户是否确认。如果操作需要用户确认，系统会自动处理确认流程。")

# ===== 新增：Skills 注入 =====
skills = self._skill_registry.list_all_skills()
if skills:
    # 过滤出 LLM 可调用的技能
    llm_callable_skills = [
        s for s in skills 
        if not s.disable_model_invocation and s.user_invocable
    ]
    
    if llm_callable_skills:
        skill_descriptions = [
            f"{s.name}({s.description})" 
            for s in llm_callable_skills
        ]
        system_parts.append(f"\n# 可用技能\n你还可以使用以下技能：{', '.join(skill_descriptions)}")
        
        # 添加使用说明
        system_parts.append(
            "\n\n**技能使用说明**："
            "技能是以目录形式组织的知识包。每个技能包含："
            "\n- SKILL.md：详细的使用指南和工作流程"
            "\n- scripts/：可直接运行的示例代码（Python/Bash/Node.js 等）"
            "\n- references/：参考资料和文档"
            "\n- assets/：模板和资源文件"
            "\n\n你可以通过 read_file 工具读取任何技能的文件来学习如何使用它。"
            "当需要执行脚本时，使用 run_in_terminal 工具。"
        )
```

#### Task 1.5: 确保文件访问工具可用
**验证清单**：
- ✅ `read_file` 工具已注册（LLM 读取 SKILL.md）
- ✅ `run_in_terminal` 工具已注册（LLM 执行脚本）
- ✅ `search_files` 工具已注册（LLM 发现技能目录）

这些工具已经存在，无需修改。

---

### Phase 2: 扩展功能

#### Task 2.1: 支持参数传递
**目标**：支持 `$ARGUMENTS` 占位符替换

**实现**：
- 在 Skill 被调用时，将参数注入到 SKILL.md 内容
- 替换所有 `$ARGUMENTS` 出现的位置

#### Task 2.2: 工具限制（allowed-tools）
**目标**：Skill 激活时限制可用工具范围

**实现**：
- 解析 `allowed-tools` 字段
- 在执行时临时修改 ToolManager 的可用工具列表

#### Task 2.3: 前端 `/` 命令菜单
**目标**：支持用户手动调用技能

**实现**：
- 前端查询可用技能列表
- 显示为 `/skill-name` 命令菜单
- 支持参数输入

#### Task 2.4: 子目录自动发现
**目标**：支持 Monorepo 结构

**实现**：
- 递归扫描子目录中的 `.x-agent/skills/`
- 支持项目级技能覆盖

---

### Phase 3: 高级功能

#### Task 3.1: 子代理执行（context: fork）
**目标**：支持隔离执行上下文

**实现**：
- 创建隔离的会话上下文
- 子代理只能看到 Skill 内容，无法访问对话历史

#### Task 3.2: 动态上下文注入
**目标**：支持 `` !`command`` 语法

**实现**：
- 在发送给 LLM 前执行命令
- 用实际输出替换占位符

#### Task 3.3: 钩子系统
**目标**：生命周期自动化

**实现**：
- on_skill_load: 技能加载时
- on_skill_complete: 技能执行完成后

---

### Phase 4: 生态建设

#### Task 4.1: 权限规则引擎
**目标**：Skill 级别的访问控制

#### Task 4.2: 企业/个人 Skill 分层
**目标**：多层级 Skill 管理

#### Task 4.3: 插件集成
**目标**：支持第三方 Skill 插件

#### Task 4.4: 开放标准兼容
**目标**：符合 agentskills.io 规范

---

## 七、案例验证

### Case 1: skill-creator 技能测试

**测试场景**：用户要求"帮我创建一个新的技能"

**预期流程**：

```
1. System Prompt 注入
   ↓
   "可用技能：skill-creator(创建新技能的完整指南)..."
   
2. LLM 识别并决定使用 skill-creator
   ↓
3. LLM 调用 read_file 读取 backend/src/skills/skill-creator/SKILL.md
   ↓
4. LLM 阅读 SKILL.md，理解创建步骤
   ↓
5. LLM 可能调用 read_file 读取 scripts/init_skill.py 了解用法
   ↓
6. LLM 指导用户执行或直接调用 run_in_terminal 执行脚本
   ↓
7. 成功创建新技能目录
```

**验收标准**：
- ✅ LLM 能正确发现 skill-creator 技能
- ✅ LLM 能读取并遵循 SKILL.md 的指南
- ✅ 最终能成功创建一个新技能目录

### Case 2: pptx 技能测试

**测试场景**：用户要求"帮我制作一个关于 AI 发展的 PPT"

**预期流程**：

```
1. System Prompt 注入
   ↓
   "可用技能：pptx(PowerPoint 演示文稿创建、编辑和分析)..."
   
2. LLM 识别并决定使用 pptx 技能
   ↓
3. LLM 调用 read_file 读取 backend/src/skills/pptx/SKILL.md
   ↓
4. LLM 学习 PPT 制作方法（html2pptx 工作流）
   ↓
5. LLM 可能调用 read_file 读取 scripts/html2pptx.js 了解用法
   ↓
6. LLM 编写 HTML 内容（遵循 SKILL.md 的设计原则）
   ↓
7. LLM 调用 run_in_terminal 执行 node scripts/html2pptx.js
   ↓
8. 成功生成 PPTX 文件
```

**验收标准**：
- ✅ LLM 能正确发现 pptx 技能
- ✅ LLM 能理解并遵循 SKILL.md 的工作流
- ✅ 最终能生成一个 PPTX 文件

---

## 八、关键技术细节

### 8.1 SKILL.md 解析逻辑

```python
def parse_skill_metadata(skill_md_path: Path) -> SkillMetadata:
    """解析 SKILL.md 的 YAML frontmatter 和目录结构"""
    
    content = skill_md_path.read_text(encoding='utf-8')
    
    # 解析 YAML frontmatter
    metadata = {}
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            yaml_content = parts[1]
            try:
                metadata = yaml.safe_load(yaml_content)
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in SKILL.md: {e}")
    
    # 验证必需字段
    if 'name' not in metadata:
        raise ValueError(f"SKILL.md must have 'name' field: {skill_md_path}")
    if 'description' not in metadata:
        raise ValueError(f"SKILL.md must have 'description' field: {skill_md_path}")
    
    # 检测目录结构
    skill_dir = skill_md_path.parent
    has_scripts = (skill_dir / 'scripts').exists()
    has_references = (skill_dir / 'references').exists()
    has_assets = (skill_dir / 'assets').exists()
    
    return SkillMetadata(
        name=metadata['name'],
        description=metadata['description'],
        path=skill_dir,
        has_scripts=has_scripts,
        has_references=has_references,
        has_assets=has_assets,
        # Phase 2 字段
        disable_model_invocation=metadata.get('disable-model-invocation', False),
        user_invocable=metadata.get('user-invocable', True),
        argument_hint=metadata.get('argument-hint'),
        allowed_tools=metadata.get('allowed-tools'),
        context=metadata.get('context'),
        license=metadata.get('license'),
    )
```

### 8.2 System Prompt 注入示例

```text
# 可用工具
你可以使用以下工具：read_file, write_file, run_in_terminal, search_files, web_search

# 可用技能
你还可以使用以下技能：
- skill-creator(创建新技能的完整指南，包括 SKILL.md 编写、脚本开发、资源组织)
- pptx(PowerPoint 演示文稿创建、编辑和分析。支持从 HTML 转换、XML 访问、主题分析)
- docx(Word 文档处理和编辑。支持读取内容、创建新文档、修改现有文档)
- pdf(PDF 文件读取、合并、拆分和信息提取。支持文本提取、表单处理)

**技能使用说明**：技能是以目录形式组织的知识包。每个技能包含：
- SKILL.md：详细的使用指南和工作流程（通过 read_file 读取）
- scripts/：可直接运行的示例代码（通过 run_in_terminal 执行）
- references/：参考资料和文档（按需加载）
- assets/：模板和资源文件（直接使用）

你可以通过 read_file 工具读取任何技能的文件来学习如何使用它。
当需要执行脚本时，使用 run_in_terminal 工具。
```

### 8.3 性能优化

**技能发现缓存**：
```python
class SkillRegistry:
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path
        self._cache: dict[str, SkillMetadata] = {}
        self._last_scan_time: datetime | None = None
        self._cache_ttl_seconds = 300  # 5 分钟
    
    def list_all_skills(self) -> list[SkillMetadata]:
        """列出所有技能（带缓存）"""
        if self._is_cache_valid():
            return list(self._cache.values())
        
        # 重新扫描
        skills = discover_all_skills(self.workspace_path)
        self._cache = {s.name: s for s in skills}
        self._last_scan_time = datetime.now()
        
        return list(self._cache.values())
    
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if self._last_scan_time is None:
            return False
        
        elapsed = (datetime.now() - self._last_scan_time).total_seconds()
        return elapsed < self._cache_ttl_seconds
```

**Token 预算管理**：
```python
def build_skill_injection(system_parts: list[str], skills: list[SkillMetadata]):
    """构建技能注入，控制 Token 消耗"""
    
    MAX_SKILLS = 20  # 最多注入 20 个技能
    MAX_DESCRIPTION_LENGTH = 100  # 每个描述最多 100 字符
    
    llm_callable_skills = [
        s for s in skills 
        if not s.disable_model_invocation and s.user_invocable
    ][:MAX_SKILLS]
    
    skill_descriptions = []
    total_chars = 0
    
    for skill in llm_callable_skills:
        desc = skill.description[:MAX_DESCRIPTION_LENGTH]
        skill_desc = f"{skill.name}({desc})"
        skill_descriptions.append(skill_desc)
        total_chars += len(skill_desc)
    
    # 检查是否超过 Token 预算（约 1 token = 4 字符）
    if total_chars > 2000:  # 约 500 tokens
        logger.warning(f"Skill injection exceeds token budget: {total_chars} chars")
    
    system_parts.append(f"\n# 可用技能\n{', '.join(skill_descriptions)}")
```

---

## 九、风险与缓解

### 风险 1: Context Token 超限
**问题**：技能太多导致 System Prompt 过长

**缓解措施**：
- ✅ 仅注入 name + description（约 10-20 字/技能）
- ✅ 限制最大技能数量（如 20 个）
- ✅ 按相关性排序（未来优化）
- ✅ Token 预算监控和警告

### 风险 2: 技能冲突
**问题**：不同层级的同名技能内容不同

**缓解措施**：
- ✅ 明确优先级：项目 > 工作空间 > 系统
- ✅ 在日志中记录覆盖情况
- ✅ 提供技能列表查询接口

### 风险 3: Script 执行安全
**问题**：LLM 可能执行危险脚本

**缓解措施**：
- ✅ 复用现有的 `run_in_terminal` 安全机制（黑名单、确认机制）
- ✅ 不自动执行任何脚本，所有执行都经过 LLM 决策
- ✅ 高危命令需要用户确认
- ✅ Phase 2 支持 `allowed-tools` 白名单

### 风险 4: 恶意 Skill 注入
**问题**：第三方 Skill 可能包含恶意指令

**缓解措施**：
- ✅ Phase 4 实现权限规则引擎
- ✅ 仅信任已知来源的 Skill
- ✅ 支持 Skill 签名验证（未来）

---

## 十、预期输出

### Phase 1（核心 MVP）
- ✅ `SkillMetadata` 数据模型
- ✅ `SkillParser` 解析器
- ✅ `SkillRegistry` 注册中心（带缓存）
- ✅ 集成到 Orchestrator（System Prompt 注入）
- ✅ 2 个案例技能成功运行（skill-creator, pptx）
- ✅ 用户技能目录支持（workspace/skills/）

### Phase 2（扩展功能）
- 📝 参数传递（$ARGUMENTS）
- 📝 工具限制（allowed-tools）
- 📝 前端 `/` 命令菜单
- 📝 子目录自动发现

### Phase 3（高级功能）
- 📝 子代理执行（context: fork）
- 📝 动态上下文注入（!`command``）
- 📝 钩子系统

### Phase 4（生态建设）
- 📝 权限规则引擎
- 📝 企业/个人 Skill 分层
- 📝 插件集成
- 📝 agentskills.io 标准兼容

---

## 十一、与 Anthropic 标准的兼容性

### ✅ 已兼容的特性

| 特性 | Anthropic | X-Agent | 状态 |
|------|-----------|---------|------|
| SKILL.md 格式 | YAML frontmatter + Markdown | 相同 | ✅ Phase 1 |
| 三层加载策略 | 元数据→完整内容→资源 | 相同 | ✅ Phase 1 |
| 优先级覆盖 | 项目 > 个人 > 企业 | 项目 > 工作空间 > 系统 | ✅ Phase 1 |
| 自动发现 | 基于 description | 相同 | ✅ Phase 1 |
| 手动调用 | `/skill-name` | 待实现 | ⏳ Phase 2 |
| 参数传递 | $ARGUMENTS | 待实现 | ⏳ Phase 2 |
| 工具限制 | allowed-tools | 待实现 | ⏳ Phase 2 |
| 子代理 | context: fork | 待实现 | ⏳ Phase 3 |
| 动态注入 | !`command`` | 待实现 | ⏳ Phase 3 |

### ⚠️ 差异化设计

| 特性 | Anthropic | X-Agent | 原因 |
|------|-----------|---------|------|
| 技能位置 | ~/.claude/skills/, ./.claude/skills/ | workspace/skills/, .x-agent/skills/ | 适配现有架构 |
| 发现机制 | Claude Code 内置 | 独立 SkillRegistry 服务 | 解耦设计 |
| 执行环境 | 高度沙箱化 | 复用现有工具 | 简化实现 |

---

## 十二、下一步行动

### 立即开始（Phase 1）

1. **创建 SkillMetadata 模型** (`backend/src/models/skill.py`)
2. **实现 SkillParser** (`backend/src/services/skill_parser.py`)
3. **实现 SkillRegistry** (`backend/src/services/skill_registry.py`)
4. **修改 Orchestrator** (`backend/src/orchestrator/engine.py`)
5. **测试 skill-creator 案例**
6. **测试 pptx 案例**

### 验收标准

- ✅ System Prompt 中包含技能列表
- ✅ LLM 能自主发现并使用技能
- ✅ skill-creator 能成功指导创建新技能
- ✅ pptx 能成功生成 PPT

准备好开始了吗？我们可以从 Task 1.1 开始逐步实现！