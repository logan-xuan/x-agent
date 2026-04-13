# Claude Code Plan 模式与审批深度分析

## 一、概述

Plan 模式是 Claude Code Swarm 系统的安全机制，要求 Teammate 在执行实际操作前先制定计划并获得 Team Lead 的审批。

## 二、Plan 模式触发条件

Teammate 在以下情况下进入 Plan 模式：
1. planModeRequired = true (spawn 时设置)
2. permissionMode = 'plan'

## 三、Plan 审批流程

### 3.1 Teammate 端

1. 进入 Plan 模式
2. 创建 plan.md 文件
3. 发送 plan_approval_request 消息给 Team Lead
4. 等待响应 (awaitingPlanApproval = true)
5. 收到响应后：
   - approved = true: 退出 Plan 模式，执行计划
   - approved = false: 根据 feedback 修改计划，重新提交

### 3.2 Team Lead 端

1. 收到 plan_approval_request
2. 审核 planContent
3. 发送 plan_approval_response：
   - approved = true + permissionMode (继承 leader 的模式)
   - approved = false + feedback

## 四、消息协议

### plan_approval_request

```
{
  type: 'plan_approval_request'
  from: string           // Teammate 名称
  timestamp: string
  planFilePath: string   // plan.md 路径
  planContent: string    // 计划内容
  requestId: string      // 请求 ID
}
```

### plan_approval_response

```
{
  type: 'plan_approval_response'
  requestId: string
  approved: boolean
  feedback?: string      // 拒绝时的反馈
  timestamp: string
  permissionMode?: PermissionMode  // 批准时继承的权限模式
}
```

## 五、权限模式继承

当 Leader 批准计划时，会传递 permissionMode：
- Leader 是 'plan' 模式 -> Teammate 获得 'default' 模式
- Leader 是其他模式 -> Teammate 继承该模式

这确保了 Teammate 在执行计划时有足够的权限。

## 六、设计优点

1. 安全性：防止 Teammate 未经审批执行危险操作
2. 可追溯：计划文件提供审计记录
3. 灵活性：Leader 可以提供反馈要求修改
4. 权限继承：批准时自动提升权限

## 七、可改进点

1. 无超时机制：Teammate 可能无限等待审批
2. 无部分批准：只能全部批准或拒绝
3. 无计划版本控制：修改后的计划无历史记录
4. 单一审批者：只有 Team Lead 可以审批
