# AGENTS.md 编排能力与工具调用系统实现方案

## 一、当前状态分析

### 已有组件
| 组件 | 文件 | 状态 |
|------|------|------|
| ContextLoader | `backend/src/core/context_loader.py` | 支持 AGENTS.md 热重载 |
| ContextBuilder | `backend/src/memory/context_builder.py` | 构建上下文，注入 System Prompt |
| FileWatcher | `backend/src/memory/file_watcher.py` | 文件变更监听 |
| Plugin 基类 | `backend/src/plugins/base.py` | 插件框架，但无具体实现 |
| LLMRouter | `backend/src/services/llm/router.py` | LLM 调用路由 |
| SmartMemoryService | `backend/src/services/smart_memory.py` | 智能记忆写入 |

### 缺失组件
| 组件 | 作用 | 优先级 |
|------|------|--------|
| **Orchestrator** | 核心编排引擎，协调所有组件 | P0 |
| **PolicyParser** | 解析 AGENTS.md 为可执行策略 | P0 |
| **PolicyEngine** | 策略执行引擎 | P0 |
| **ReAct 循环** | LLM 思考-行动-观察循环 | P0 |
| **ToolManager** | 工具注册与执行管理 | P0 |
| **具体工具** | 文件操作、网络搜索等 | P1 |

---

## 二、架构设计

```
backend/src/
├── orchestrator/                    # 新增：编排引擎
│   ├── __init__.py
│   ├── engine.py                    # Orchestrator 主引擎
│   ├── policy_parser.py             # AGENTS.md 策略解析器
│   ├── policy_engine.py             # 策略执行引擎
│   ├── react_loop.py                # ReAct 循环实现
│   └── guards/                      # 守卫模块
│       ├── __init__.py
│       ├── session_guard.py         # 会话守卫
│       └── response_guard.py        # 响应守卫
│
├── tools/                           # 新增：工具系统
│   ├── __init__.py
│   ├── manager.py                   # 工具管理器
│   ├── base.py                      # 工具基类
│   ├── registry.py                  # 工具注册表
│   └── builtin/                     # 内置工具
│       ├── __init__.py
│       ├── file_ops.py              # 文件操作工具
│       ├── web_search.py            # 网络搜索工具
│       └── shell.py                 # Shell 命令工具
│
└── core/
    └── agent.py                     # 修改：集成 Orchestrator
```

---

## 三、实现任务

### Phase 1: 策略解析系统 (P0)

#### 1.1 PolicyParser - AGENTS.md 解析器
**文件**: `backend/src/orchestrator/policy_parser.py`

**核心逻辑**:
```python
class RuleType(Enum):
    HARD_CONSTRAINT = "hard_constraint"  # 硬约束：系统执行
    SOFT_GUIDELINE = "soft_guideline"    # 软引导：Prompt 注入
    IDENTITY = "identity"                # 身份：角色定义

@dataclass
class Rule:
    id: str
    type: RuleType
    source_section: str
    content: str
    action: Callable | None  # 硬约束的执行函数
    prompt_text: str | None  # 软引导的提示词

@dataclass
class PolicyBundle:
    hard_constraints: list[Rule]
    soft_guidelines: list[Rule]
    identity_rules: list[Rule]
    source_hash: str
```

**章节映射**:
- `## 安全准则` → HARD_CONSTRAINT
- `## 外部操作` → HARD_CONSTRAINT  
- `## 避免三连击` → SOFT_GUIDELINE
- `## 表情反应` → SOFT_GUIDELINE
- `## 记忆系统` → SOFT_GUIDELINE
- `## 首次启动` → IDENTITY

#### 1.2 PolicyEngine - 策略执行引擎
**文件**: `backend/src/orchestrator/policy_engine.py`

**核心方法**:
- `reload_if_changed()` - 检查变更并重载
- `enforce_session_rules(session_type)` - 执行会话规则
- `build_system_prompt_guidelines()` - 构建软引导 Prompt
- `get_context_load_rules()` - 获取上下文加载规则

---

### Phase 2: 工具调用系统 (P0)

#### 2.1 Tool 基类
**文件**: `backend/src/tools/base.py`

```python
@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None
    metadata: dict

class BaseTool(ABC):
    name: str
    description: str
    parameters: dict  # JSON Schema
    
    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        pass
    
    def to_openai_tool(self) -> dict:
        """转换为 OpenAI function calling 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }
        }
```

#### 2.2 ToolManager - 工具管理器
**文件**: `backend/src/tools/manager.py`

```python
class ToolManager:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
    
    def register(self, tool: BaseTool) -> None: ...
    def get_tool(self, name: str) -> BaseTool | None: ...
    def get_all_tools(self) -> list[BaseTool]: ...
    def get_openai_tools(self) -> list[dict]: ...
    async def execute(self, name: str, params: dict) -> ToolResult: ...
```

#### 2.3 内置工具示例

**文件操作工具** (`backend/src/tools/builtin/file_ops.py`):
- `read_file` - 读取文件
- `write_file` - 写入文件
- `list_dir` - 列出目录
- `search_file` - 搜索文件

**网络搜索工具** (`backend/src/tools/builtin/web_search.py`):
- `web_search` - 网络搜索 (可接入 DuckDuckGo API)

---

### Phase 3: ReAct 循环 (P0)

#### 3.1 ReActLoop 实现
**文件**: `backend/src/orchestrator/react_loop.py`

```python
class ReActLoop:
    """ReAct 循环：思考 → 行动 → 观察"""
    
    MAX_ITERATIONS = 5
    
    async def run(
        self,
        messages: list[dict],
        tools: list[BaseTool],
        on_thinking: Callable | None = None,
        on_tool_call: Callable | None = None,
    ) -> str:
        """
        循环执行：
        1. LLM 思考，决定是否调用工具
        2. 如果需要工具，执行并获取结果
        3. 将工具结果注入上下文
        4. 重复直到 LLM 给出最终回答
        """
        for i in range(self.MAX_ITERATIONS):
            response = await self._llm.chat(
                messages, 
                tools=tools  # OpenAI function calling
            )
            
            if response.tool_calls:
                # 执行工具调用
                for tool_call in response.tool_calls:
                    result = await self._execute_tool(tool_call)
                    messages.append({
                        "role": "tool",
                        "content": result.output,
                        "tool_call_id": tool_call.id
                    })
            else:
                # 最终回答
                return response.content
        
        return "达到最大迭代次数"
```

---

### Phase 4: Orchestrator 主引擎 (P0)

#### 4.1 Orchestrator 实现
**文件**: `backend/src/orchestrator/engine.py`

```python
class Orchestrator:
    """核心编排引擎"""
    
    def __init__(self, workspace_path: str):
        self.policy_engine = PolicyEngine(workspace_path)
        self.tool_manager = ToolManager()
        self.react_loop = ReActLoop()
        self.session_guard = SessionGuard()
        self.response_guard = ResponseGuard()
        
        # 注册内置工具
        self._register_builtin_tools()
    
    async def process_request(
        self,
        session_id: str,
        user_message: str,
        session_type: SessionType = SessionType.MAIN,
    ) -> AsyncGenerator[dict, None]:
        """处理用户请求的完整流程"""
        
        # 1. 策略重载
        policy, reloaded = self.policy_engine.reload_if_changed()
        yield {"event": "policy_check", "reloaded": reloaded}
        
        # 2. 会话守卫 - 应用硬约束
        context_rules = self.session_guard.apply_rules(
            session_type, 
            policy.hard_constraints
        )
        
        # 3. 加载上下文
        context = await self._load_context(session_id, context_rules)
        
        # 4. 构建消息
        messages = self._build_messages(context, user_message)
        
        # 5. ReAct 循环
        async for event in self.react_loop.run_streaming(
            messages,
            tools=self.tool_manager.get_all_tools(),
        ):
            yield event
        
        # 6. 响应后处理
        final_response = self.response_guard.process(response, policy)
        
        # 7. 记忆写入
        await self._write_memory(user_message, final_response)
        
        yield {"event": "final_answer", "content": final_response}
```

---

### Phase 5: 集成到现有 Agent (P0)

#### 5.1 修改 Agent 类
**文件**: `backend/src/core/agent.py`

修改 `chat()` 方法，集成 Orchestrator:

```python
class Agent:
    def __init__(self, ...):
        # 新增 Orchestrator
        self._orchestrator = Orchestrator(workspace_path)
    
    async def chat(self, session_id, user_message, stream=False):
        # 使用 Orchestrator 处理请求
        if stream:
            return self._orchestrator.process_request(
                session_id, user_message, stream=True
            )
        else:
            # 非流式版本
            result = await self._orchestrator.process_request_sync(
                session_id, user_message
            )
            return result
```

---

### Phase 6: WebSocket 流式事件 (P1)

#### 6.1 扩展 WebSocket 事件
**文件**: `backend/src/api/websocket.py`

新增事件类型:
- `thinking` - LLM 思考中
- `tool_call` - 工具调用开始
- `tool_result` - 工具执行结果
- `policy_reload` - 策略重载通知

---

## 四、文件变更清单

### 新增文件 (9个)
| 文件 | 行数估计 | 说明 |
|------|----------|------|
| `backend/src/orchestrator/__init__.py` | ~20 | 模块导出 |
| `backend/src/orchestrator/engine.py` | ~200 | Orchestrator 主引擎 |
| `backend/src/orchestrator/policy_parser.py` | ~150 | 策略解析器 |
| `backend/src/orchestrator/policy_engine.py` | ~120 | 策略执行引擎 |
| `backend/src/orchestrator/react_loop.py` | ~180 | ReAct 循环 |
| `backend/src/orchestrator/guards/__init__.py` | ~15 | 守卫模块导出 |
| `backend/src/orchestrator/guards/session_guard.py` | ~80 | 会话守卫 |
| `backend/src/orchestrator/guards/response_guard.py` | ~100 | 响应守卫 |
| `backend/src/tools/__init__.py` | ~20 | 工具模块导出 |
| `backend/src/tools/base.py` | ~80 | 工具基类 |
| `backend/src/tools/manager.py` | ~100 | 工具管理器 |
| `backend/src/tools/builtin/__init__.py` | ~15 | 内置工具导出 |
| `backend/src/tools/builtin/file_ops.py` | ~150 | 文件操作工具 |
| `backend/src/tools/builtin/web_search.py` | ~80 | 网络搜索工具 |

### 修改文件 (3个)
| 文件 | 修改内容 |
|------|----------|
| `backend/src/core/agent.py` | 集成 Orchestrator，替换直接 LLM 调用 |
| `backend/src/api/websocket.py` | 新增流式事件类型 |
| `backend/src/memory/context_builder.py` | 集成 PolicyEngine 构建软引导 Prompt |

---

## 五、依赖项

无需新增依赖，使用现有：
- `openai` - 已有，支持 function calling
- `watchdog` - 已有，文件监听
- `pydantic` - 已有，数据模型

---

## 六、验收标准

1. **策略解析**: AGENTS.md 变更后下次请求立即生效
2. **工具调用**: Agent 能成功调用文件操作工具完成任务
3. **ReAct 循环**: 多轮思考-行动能正确执行
4. **流式输出**: WebSocket 正确推送 thinking/tool_call 事件
5. **测试覆盖**: 核心模块单元测试通过