# System 角色消息实现方案

## 现状分析

### 当前实现
```typescript
// 只有两种角色在使用
export type MessageRole = 'user' | 'assistant' | 'system';

// 实际使用中：
- user: 用户输入 ✅
- assistant: AI 回复 + tool_calls 数组 ✅
- system: 未使用 ❌
```

### 问题
工具执行信息（CLI 命令、错误日志）被混在 assistant 消息中，导致：
1. 用户难以区分 AI 思考和系统执行
2. 调试时找不到详细的执行日志
3. 消息历史混乱

---

## 实现方案

### 1. WebSocket 消息类型扩展

**新增 system 消息类型**：
```typescript
export interface WebSocketMessage {
  type: WebSocketMessageType;
  // ... existing fields
  
  // NEW: System message fields
  log_type?: 'cli_command' | 'tool_execution' | 'error' | 'info';
  log_data?: {
    command?: string;
    output?: string;
    error?: string;
    duration_ms?: number;
    success?: boolean;
  };
}
```

### 2. 后端发送 System 消息

**在 Orchestrator 中添加**：
```python
# When executing CLI command
await websocket.send_json({
    "type": "system",
    "log_type": "cli_command",
    "log_data": {
        "command": "pip install python-pptx",
        "status": "executing"
    }
})

# After execution
await websocket.send_json({
    "type": "system",
    "log_type": "tool_execution",
    "log_data": {
        "command": "pip install python-pptx",
        "output": "Successfully installed...",
        "duration_ms": 2340,
        "success": True
    }
})
```

### 3. 前端处理 System 消息

**在 useChat.ts 中**：
```typescript
case 'system':
  // Create a system message for logs
  const systemMessage: Message = {
    id: `system-${Date.now()}`,
    session_id: msg.session_id || currentSessionId || '',
    role: 'system',
    content: formatSystemLog(msg.log_data),
    created_at: new Date().toISOString(),
    metadata: {
      log_type: msg.log_type,
      ...msg.log_data
    }
  };
  
  setMessages(prev => [...prev, systemMessage]);
  break;
```

### 4. 前端显示优化

**MessageItem.tsx 样式区分**：
```tsx
const getStyleByRole = (role: MessageRole) => {
  switch (role) {
    case 'user':
      return 'bg-blue-500 text-white ml-auto';
    case 'assistant':
      return 'bg-gray-100 dark:bg-gray-800 mr-auto';
    case 'system':
      return 'bg-yellow-50 dark:bg-yellow-900/20 border-l-4 border-yellow-500 w-full text-xs';
  }
};

// For system messages, show collapsible details
{message.role === 'system' && (
  <details className="text-xs">
    <summary className="cursor-pointer text-yellow-700 dark:text-yellow-400">
      🔧 System: {message.metadata?.log_type}
    </summary>
    <pre className="mt-2 p-2 bg-black/10 rounded overflow-auto">
      {message.content}
    </pre>
  </details>
)}
```

---

## 消息流转示例

### 场景：用户请求创建 PPT

```
1. User sends: "/pptx 创建春节美食 PPT"
   → Message added: { role: 'user', content: '/pptx 创建春节美食 PPT' }

2. Backend starts thinking
   → WebSocket: { type: 'assistant_start' }
   → Message added: { role: 'assistant', content: '正在思考...' }

3. Backend decides to run pip install
   → WebSocket: { 
       type: 'system', 
       log_type: 'cli_command',
       log_data: { command: 'pip install python-pptx', status: 'executing' }
     }
   → Message added: { 
       role: 'system', 
       content: '🔧 Executing: pip install python-pptx',
       metadata: { log_type: 'cli_command', ... }
     }

4. Command completes
   → WebSocket: {
       type: 'system',
       log_type: 'tool_execution',
       log_data: { 
         command: 'pip install python-pptx',
         output: 'Successfully installed...',
         duration_ms: 2340,
         success: true
       }
     }
   → Message updated or new message added

5. Assistant responds
   → WebSocket: { type: 'assistant_chunk', content: '依赖已安装...' }
   → Message updated: { role: 'assistant', content: '依赖已安装...' }

6. Final response
   → WebSocket: { type: 'message', is_finished: true }
   → Complete conversation:
     - User: "/pptx 创建春节美食 PPT"
     - System: "🔧 Executing: pip install python-pptx"
     - System: "✅ Completed in 2.3s"
     - Assistant: "依赖已安装，现在开始创建 PPT..."
```

---

## 优势

### 用户体验
1. **清晰可见**：用户能看到后台执行了什么命令
2. **调试友好**：出问题时能快速定位是哪一步失败
3. **学习价值**：用户可以了解 AI 是如何完成任务的

### 技术优势
1. **职责分离**：AI 思考 vs 系统执行 明确区分
2. **日志完整**：所有执行细节都有记录
3. **可扩展**：未来可以添加更多 system 消息类型

---

## 实施步骤

### Phase 1: 后端支持 (Priority: High)
1. ✅ 在 WebSocket 协议中添加 system 消息类型
2. ✅ 在 ToolManager 中添加 system 消息发送
3. ✅ 在错误处理中添加 system 消息发送

### Phase 2: 前端支持 (Priority: Medium)
1. ✅ 在 useChat.ts 中处理 system 消息
2. ✅ 在 MessageItem.tsx 中添加 system 样式
3. ✅ 添加折叠/展开功能

### Phase 3: 优化体验 (Priority: Low)
1. ⏳ System 消息默认折叠
2. ⏳ 提供"显示详细日志"开关
3. ⏳ 支持按类型过滤 system 消息

---

## 注意事项

1. **不要过度暴露**：敏感的系统内部信息不应该显示
2. **保持简洁**：system 消息应该简短明了
3. **性能考虑**：大量 system 消息可能影响性能，需要限制数量
4. **用户选择**：提供关闭 system 消息显示的选项
