# Claude Code 上下文共享深度分析

## 一、概述

上下文共享是 Claude Code 多智能体系统的核心机制，确保子 Agent 能够继承父 Agent 的必要上下文，同时保持适当的隔离。

## 二、Fork Context Messages

当创建子 Agent 时，可以通过 forkContextMessages 传递父 Agent 的对话历史：

1. 过滤不完整的工具调用 (filterIncompleteToolCalls)
2. 合并到子 Agent 的初始消息
3. 子 Agent 继承父 Agent 的上下文

## 三、Worker Tools 继承

子 Agent 的工具集由以下因素决定：

1. Agent 定义中的 tools 字段
2. resolveAgentTools() 解析
3. 父 Agent 的 MCP 客户端 (可继承)
4. Agent 特定的 MCP 服务器 (可添加)

### 工具继承规则

- tools: ['*'] - 继承所有工具
- tools: ['Read', 'Write'] - 只继承指定工具
- useExactTools: true - 使用父 Agent 的精确工具集 (用于 fork)

## 四、权限继承

### 权限模式继承

子 Agent 的权限模式由以下因素决定：

1. Agent 定义中的 permissionMode
2. 父 Agent 的模式 (某些模式优先)
3. allowedTools 参数

### 优先级规则

- bypassPermissions: 始终优先
- acceptEdits: 始终优先
- auto (TRANSCRIPT_CLASSIFIER): 始终优先
- 其他: 使用 Agent 定义的模式

### allowedTools 处理

当提供 allowedTools 时：
- 保留 SDK 级别的 cliArg 权限
- 清除父 Agent 的 session 级别权限
- 使用提供的 allowedTools 作为新的 session 权限

## 五、createSubagentContext

createSubagentContext 是创建子 Agent 上下文的核心函数：

1. 创建新的 ToolUseContext
2. 设置 agentId 和 agentType
3. 配置 options (工具、模型、MCP 等)
4. 设置 abortController
5. 配置 getAppState (可能有权限覆盖)
6. 决定是否共享 setAppState

### 同步 vs 异步 Agent

- 同步 Agent: 共享 setAppState、abortController
- 异步 Agent: 独立的 setAppState、独立的 abortController

## 六、ReadFileState 共享

子 Agent 可以继承父 Agent 的文件状态缓存：

- forkContextMessages 存在: 克隆父 Agent 的缓存
- 否则: 创建新的缓存

这避免了重复读取相同文件。

## 七、设计优点

1. 灵活继承：可以选择性继承上下文
2. 权限隔离：子 Agent 不会自动获得父 Agent 的所有权限
3. 缓存共享：避免重复文件读取
4. 工具控制：精确控制子 Agent 可用的工具

## 八、可改进点

1. 上下文大小：大量历史消息可能导致 token 浪费
2. 缓存一致性：父 Agent 修改文件后，子 Agent 缓存可能过时
3. 权限复杂性：多层继承规则可能难以理解
