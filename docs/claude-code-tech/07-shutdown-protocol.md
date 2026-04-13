# Claude Code Shutdown 协议深度分析

## 一、概述

Shutdown 协议是 Claude Code Swarm 系统的优雅关闭机制，确保 Teammate 在关闭前完成必要的清理工作。

## 二、Shutdown 流程

### 2.1 Leader 发起关闭

1. Leader 发送 shutdown_request 消息
2. 消息包含 requestId、from、reason、timestamp

### 2.2 Teammate 响应

Teammate 收到请求后可以：
- 批准：发送 shutdown_approved
- 拒绝：发送 shutdown_rejected (附带 reason)

### 2.3 关闭执行

批准后：
- In-Process Teammate: 调用 abortController.abort()
- tmux/iTerm2 Teammate: 调用 gracefulShutdown()

## 三、消息协议

### shutdown_request

```
{
  type: 'shutdown_request'
  requestId: string
  from: string
  reason?: string
  timestamp: string
}
```

### shutdown_approved

```
{
  type: 'shutdown_approved'
  requestId: string
  from: string
  timestamp: string
  paneId?: string       // tmux 面板 ID
  backendType?: string  // 'in-process' | 'tmux' | 'iterm2'
}
```

### shutdown_rejected

```
{
  type: 'shutdown_rejected'
  requestId: string
  from: string
  reason: string
  timestamp: string
}
```

## 四、In-Process Teammate 关闭

1. 发送 shutdown_approved 消息
2. 查找任务的 abortController
3. 调用 abort() 终止执行
4. 任务状态更新为 killed

## 五、进程外 Teammate 关闭

1. 发送 shutdown_approved 消息
2. 调用 gracefulShutdown(0, 'other')
3. 进程退出

## 六、设计优点

1. 协商式关闭：Teammate 可以拒绝不合时宜的关闭请求
2. 可追溯：requestId 关联请求和响应
3. 后端感知：响应包含 backendType 便于 Leader 处理
4. 优雅退出：给 Teammate 机会完成清理

## 七、可改进点

1. 无强制关闭：如果 Teammate 不响应，无法强制关闭
2. 无超时机制：Leader 可能无限等待响应
3. 无批量关闭：需要逐个发送关闭请求
