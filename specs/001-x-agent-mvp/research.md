# Research: X-Agent MVP

**Feature**: X-Agent MVP  
**Created**: 2026-02-14  
**Related**: [spec.md](./spec.md), [plan.md](./plan.md)

## 技术选型决策

### 后端框架

**决策**: FastAPI

**理由**:
- 原生异步支持，符合性能优先原则（宪法 VI）
- Pydantic 集成，天然支持类型注解（宪法 I）
- 自动 OpenAPI 文档生成，减少维护成本
- WebSocket 支持完善，满足实时通信需求
- 社区活跃，文档丰富，适合个人项目

**替代方案**:
| 框架 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| Flask | 轻量、灵活 | 需额外配置异步，生态老旧 | 不适用 |
| Django | 功能全面 | 过于重量级，违反 YAGNI | 不适用 |
| Tornado | 异步原生 | 维护活跃度下降 | 不适用 |

---

### 前端框架

**决策**: React 18 + Vite

**理由**:
- React 生态成熟，组件化符合关注点分离（宪法 III）
- Vite 构建速度快，HMR 体验好
- TypeScript 严格模式支持（宪法 I）
- 与 shadcn/ui 组件库兼容
- 符合 /ui-ux-pro-max 设计要求

**替代方案**:
| 框架 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| Vue 3 | 简单易学 | 生态规模略逊 | 备选 |
| Svelte | 性能优秀 | 较新，长期风险 | 不适用 |
| Next.js | SSR 支持 | 过于重量级，MVP 不需要 | 不适用 |

---

### 数据库

**决策**: SQLite

**理由**:
- 零配置，适合个人本地部署
- 单文件存储，备份简单
- Python 标准库支持
- MVP 数据量小，性能足够
- 后续可迁移到 PostgreSQL

**替代方案**:
| 数据库 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| PostgreSQL | 功能强大 | 需额外安装配置 | 后续版本考虑 |
| MongoDB | 文档存储 | 关系型数据更适合对话历史 | 不适用 |

---

### ORM

**决策**: SQLAlchemy 2.0

**理由**:
- Python ORM 标准
- 2.0 版本支持类型注解
- 异步支持完善
- 迁移工具成熟（Alembic）

---

### LLM SDK

**决策**: OpenAI SDK + 阿里云百炼 SDK 双支持

**理由**:
- OpenAI SDK 是行业标准，兼容多数提供商
- 阿里云百炼是国内优质选择
- 通过统一抽象层封装，支持一主多备

**抽象设计**:

```python
class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list, stream: bool = False) -> AsyncIterator[str]:
        pass

class OpenAIProvider(LLMProvider):
    # OpenAI 实现

class BailianProvider(LLMProvider):
    # 阿里云百炼实现
```

---

### WebSocket 库

**决策**: FastAPI 原生 WebSocket

**理由**:
- 与 FastAPI 深度集成
- 支持异步
- 自动文档生成

**消息协议设计**:

```typescript
// 客户端 → 服务器
interface UserMessage {
  type: 'user_message';
  sessionId: string;
  content: string;
}

// 服务器 → 客户端
interface AssistantChunk {
  type: 'assistant_chunk';
  sessionId: string;
  content: string;  // 增量内容
}

interface AssistantEnd {
  type: 'assistant_end';
  sessionId: string;
  metadata: {
    model: string;
    tokens: number;
  };
}
```

---

### 日志方案

**决策**: Python structlog + 前端自定义实现

**理由**:
- 结构化日志符合可调试性设计（宪法 IV）
- JSON 格式便于分析
- 支持上下文追踪 ID

**日志格式**:

```json
{
  "timestamp": "2026-02-14T10:00:00Z",
  "level": "INFO",
  "module": "x_agent.llm",
  "request_id": "uuid",
  "message": "LLM request completed",
  "duration_ms": 1500,
  "tokens": 150
}
```

---

### 配置管理

**决策**: Pydantic-Settings + PyYAML + Watchdog 热重载

**理由**:
- 类型安全：Pydantic 模型提供完整的类型验证
- 验证自动：配置加载时自动验证，错误即时反馈
- 热重载支持：配置文件变更自动检测，无需重启服务
- 厂商无关：统一的模型配置抽象，不依赖特定厂商
- 一主多备：内置故障转移逻辑，自动切换备用模型
- 人类可读：YAML 格式，注释支持，易于维护

**配置架构设计**:

```
┌─────────────────────────────────────────────────────────────┐
│                    ConfigManager (单例)                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Loader    │  │   Watcher   │  │   Validator         │ │
│  │  (YAML解析)  │  │ (文件监听)   │  │  (Pydantic校验)      │ │
│  └──────┬──────┘  └──────┬──────┘  └─────────────────────┘ │
│         │                │                                   │
│         └────────────────┼───────────────────────────────────┘
│                          │                                    │
│                    ┌─────▼──────┐                            │
│                    │ ConfigModel │                            │
│                    │  (Pydantic) │                            │
│                    └─────┬──────┘                            │
│                          │                                    │
│         ┌────────────────┼────────────────┐                   │
│         ▼                ▼                ▼                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐           │
│  │   Models    │  │   Server    │  │   Logging   │           │
│  │  (LLM配置)   │  │  (服务配置)  │  │  (日志配置)  │           │
│  └─────────────┘  └─────────────┘  └─────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

**配置模型设计**:

```python
class ModelConfig(BaseModel):
    """模型配置 - 厂商无关设计"""
    name: str                    # 配置名称: primary, backup-1, etc.
    provider: Literal["openai", "bailian", "custom"]
    base_url: HttpUrl
    api_key: SecretStr          # 加密存储
    model_id: str               # 模型标识
    is_primary: bool = False    # 是否主模型
    timeout: float = 30.0       # 请求超时
    max_retries: int = 2        # 最大重试次数
    
class ConfigModel(BaseSettings):
    """根配置模型"""
    models: List[ModelConfig] = Field(min_items=1)
    server: ServerConfig
    logging: LoggingConfig
    
    @validator('models')
    def validate_primary(cls, v):
        """确保有且仅有一个主模型"""
        primaries = [m for m in v if m.is_primary]
        if len(primaries) != 1:
            raise ValueError("必须有且仅有一个主模型")
        return v
```

**配置文件示例 (x-agent.yaml)**:

```yaml
# X-Agent 配置文件
# 所有配置集中管理，不依赖环境变量

models:
  # 主模型配置
  - name: primary
    provider: openai
    base_url: https://api.openai.com/v1
    api_key: sk-your-openai-key-here
    model_id: gpt-3.5-turbo
    is_primary: true
    timeout: 30.0
    max_retries: 2
  
  # 备用模型配置 (阿里云百炼)
  - name: backup-bailian
    provider: bailian
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    api_key: sk-your-bailian-key-here
    model_id: qwen-turbo
    is_primary: false
    timeout: 45.0
    max_retries: 3
  
  # 备用模型配置 (另一个 OpenAI 账户)
  - name: backup-openai
    provider: openai
    base_url: https://api.openai.com/v1
    api_key: sk-your-backup-key-here
    model_id: gpt-3.5-turbo
    is_primary: false

server:
  host: "0.0.0.0"
  port: 8000
  cors_origins:
    - "http://localhost:5173"
    - "http://127.0.0.1:5173"

logging:
  level: INFO
  format: json
  file: logs/x-agent.log
  max_size: 10MB
  backup_count: 5
```

**一主多备故障转移设计**:

```python
class LLMRouter:
    """LLM 路由管理器 - 实现一主多备自动切换"""
    
    def __init__(self, config_manager: ConfigManager):
        self.config = config_manager
        self.providers: Dict[str, LLMProvider] = {}
        self._init_providers()
    
    def _init_providers(self):
        """初始化所有模型提供商"""
        for model_config in self.config.models:
            provider = create_provider(model_config)
            self.providers[model_config.name] = provider
    
    async def chat(self, messages: List[Message], **kwargs) -> AsyncIterator[str]:
        """智能路由 - 优先主模型，故障自动切换"""
        primary = self._get_primary()
        backups = self._get_backups()
        
        # 尝试主模型
        try:
            async for chunk in primary.chat(messages, **kwargs):
                yield chunk
            return
        except Exception as e:
            logger.warning(f"主模型故障: {e}, 尝试备用模型")
        
        # 依次尝试备用模型
        for backup in backups:
            try:
                async for chunk in backup.chat(messages, **kwargs):
                    yield chunk
                logger.info(f"已切换到备用模型: {backup.name}")
                return
            except Exception as e:
                logger.warning(f"备用模型 {backup.name} 故障: {e}")
        
        # 所有模型都不可用
        raise AllModelsUnavailableError("所有模型均不可用")
```

**热重载机制**:

```python
class ConfigWatcher:
    """配置文件变更监听器"""
    
    def __init__(self, config_path: Path, callback: Callable):
        self.config_path = config_path
        self.callback = callback
        self.observer = Observer()
    
    def start(self):
        """启动监听"""
        handler = ConfigChangeHandler(self.callback)
        self.observer.schedule(handler, str(self.config_path.parent))
        self.observer.start()
    
    def stop(self):
        """停止监听"""
        self.observer.stop()
        self.observer.join()

class ConfigChangeHandler(FileSystemEventHandler):
    def __init__(self, callback: Callable):
        self.callback = callback
        self.last_modified = 0
    
    def on_modified(self, event):
        if event.src_path.endswith('x-agent.yaml'):
            # 防抖处理
            current = time.time()
            if current - self.last_modified > 1.0:
                self.last_modified = current
                logger.info("检测到配置文件变更，正在重新加载...")
                self.callback()
```

---

### 测试策略

**后端**:
- pytest: 单元测试和集成测试
- pytest-asyncio: 异步测试支持
- httpx: HTTP 客户端测试
- 覆盖率目标: 80%+

**前端**:
- Vitest: 单元测试
- Playwright: E2E 测试
- React Testing Library: 组件测试

---

### 代码质量工具

**后端**:
- ruff: 快速 Python linter (替代 flake8 + black)
- mypy: 类型检查
- pre-commit: 提交前检查

**前端**:
- ESLint: 代码检查
- Prettier: 代码格式化
- TypeScript: 类型检查

---

## 架构决策记录

### ADR-001: 前后端分离

**状态**: 已接受

**上下文**: MVP 需要 Web 界面和后端服务

**决策**: 前后端分离部署

**后果**:
- 正面: 技术栈独立，团队可并行开发
- 正面: 前端可独立迭代 UI
- 负面: 需要处理 CORS 和部署协调

---

### ADR-002: 分层架构

**状态**: 已接受

**上下文**: 需要满足模块化 + 插件式架构要求

**决策**: 五层架构（API → Core → Services → Models → DB）

**后果**:
- 正面: 职责清晰，符合关注点分离
- 正面: 便于测试和替换实现
- 负面: 初期开发成本略高

---

### ADR-003: SQLite 作为 MVP 数据库

**状态**: 已接受

**上下文**: MVP 阶段单用户本地部署

**决策**: 使用 SQLite，后续迁移到 PostgreSQL

**后果**:
- 正面: 零配置，快速启动
- 正面: 单文件便于备份
- 负面: 并发性能有限（MVP 单用户无影响）
- 负面: 需要规划迁移路径

---

## 风险与缓解

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| LLM API 不稳定 | 中 | 高 | 一主多备配置 |
| WebSocket 连接问题 | 低 | 中 | 实现自动重连 |
| 前端构建复杂 | 低 | 低 | 使用 Vite 简化配置 |
| 类型安全漏洞 | 低 | 中 | mypy + TypeScript 严格模式 |
