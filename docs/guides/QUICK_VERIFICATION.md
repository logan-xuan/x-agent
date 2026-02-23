# System Role Messages - 快速验证指南

## 🎯 功能说明

现在 X-Agent 已经实现了三类消息角色分离：
- **User**: 用户输入的消息
- **Assistant**: AI 的思考和回复
- **System**: CLI 命令执行、工具调用、错误日志（新增）

---

## 🚀 如何验证

### **方法 1: 运行自动化测试脚本**

```bash
./test-system-role.sh
```

**预期输出**:
```
======================================
Testing System Role Messages Feature
======================================

✅ Backend is running
✅ Frontend is running

======================================
Feature Implementation Checklist
======================================

Backend Changes:
✅ send_system_message function added
✅ System message type implemented
✅ CLI command logging implemented
✅ Tool execution logging implemented

Frontend Changes:
✅ MessageRole includes 'system'
✅ WebSocketMessageType includes 'system'
✅ System message fields defined in types
✅ formatSystemLogContent helper function added
✅ System message handling implemented in useChat
✅ System message rendering implemented
✅ System message UI styling added
```

---

### **方法 2: 手动测试**

#### **Step 1: 启动服务**
```bash
# Terminal 1 - 后端
cd backend
uv run uvicorn src.main:app --reload

# Terminal 2 - 前端
cd frontend
yarn dev
```

#### **Step 2: 打开浏览器**
访问 http://localhost:5173

#### **Step 3: 发送技能命令**
在聊天框中输入：
```
/pptx 创建一个关于春节美食的 PPT
```

#### **Step 4: 观察聊天窗口**

你应该看到以下消息流：

```
┌──────────────────────────────────────┐
│ 👤 YOU                               │
│ /pptx 创建一个关于春节美食的 PPT       │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│ 🔧 System Log: cli_command       ▼   │
│ Executing: pip install python-pptx   │
│ (executing)                          │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│ 🔧 System Log: tool_execution    ▼   │
│ ✅ Completed                         │
│ Successfully installed python-pptx   │
└──────────────────────────────────────┘

┌──────────────────────────────────────┐
│ 🤖 X-AGENT                           │
│ 正在为您创建 PPT...                  │
│ ...                                  │
└──────────────────────────────────────┘
```

---

## 🎨 UI 特征

### **System 消息样式**
- **位置**: 独立显示，不依赖左右对齐
- **边框**: 左侧黄色边框 (`border-l-4 border-yellow-500`)
- **背景**: 半透明黑色/白色 (`bg-black/10 dark:bg-white/5`)
- **字体**: 等宽字体显示日志内容 (`font-mono`)
- **字号**: 小字号 (`text-xs`)
- **交互**: 可折叠/展开 (`<details>` 标签)
- **图标**: 🔧 emoji + 状态 emoji (✅/❌)

### **Dark Mode 适配**
- Light: `text-yellow-700` + `bg-black/10`
- Dark: `text-yellow-400` + `bg-white/5`

---

## 📊 技术验证

### **后端检查点**

1. **WebSocket 函数**
   ```bash
   grep -n "send_system_message" backend/src/api/websocket.py
   ```
   
   应该看到：
   - Line ~33: 函数定义
   - Line ~415: CLI command 调用
   - Line ~440: Tool result 调用

2. **消息类型**
   ```bash
   grep -n '"type": "system"' backend/src/api/websocket.py
   ```
   
   应该看到在 `send_system_message()` 函数中

3. **日志类型**
   ```bash
   grep -n "log_type" backend/src/api/websocket.py
   ```
   
   应该看到：
   - `cli_command` (当工具是 run_in_terminal)
   - `tool_execution` (当收到 tool_result)

---

### **前端检查点**

1. **TypeScript 类型**
   ```bash
   grep -n "'system'" frontend/src/types/index.ts
   ```
   
   应该看到：
   - Line ~4: `MessageRole = 'user' | 'assistant' | 'system'`
   - Line ~56: `| 'system'` in WebSocketMessageType

2. **useChat Hook**
   ```bash
   grep -n "case 'system':" frontend/src/hooks/useChat.ts
   ```
   
   应该看到 system 消息处理逻辑

3. **MessageItem 组件**
   ```bash
   grep -n "isSystem" frontend/src/components/chat/MessageItem.tsx
   ```
   
   应该看到 system 消息的专用渲染逻辑

---

## 🔍 调试技巧

### **查看 WebSocket 消息**

打开浏览器开发者工具 → Network → WS → Frames

当你发送 `/pptx` 命令时，应该看到：

```json
// ← 后端发送的系统消息
{
  "type": "system",
  "session_id": "...",
  "trace_id": "...",
  "log_type": "cli_command",
  "log_data": {
    "command": "pip install python-pptx",
    "status": "executing",
    "tool_call_id": "..."
  }
}

// ← 后端发送的系统消息
{
  "type": "system",
  "session_id": "...",
  "trace_id": "...",
  "log_type": "tool_execution",
  "log_data": {
    "tool_call_id": "...",
    "success": true,
    "output": "Successfully installed...",
    "error": null
  }
}
```

---

## ⚠️ 常见问题

### **Q1: 为什么看不到 System 消息？**

**检查清单**:
1. 后端是否正常运行？ (`curl http://localhost:8000/api/v1/health`)
2. 前端是否正常运行？ (`curl http://localhost:5173`)
3. 是否使用了技能命令？（只有工具执行才会触发 system 消息）
4. 浏览器控制台是否有报错？

### **Q2: System 消息太占空间？**

**解决方案**: 
- 点击黄色的标题栏可以折叠消息
- 折叠后只显示标题，不显示详细日志

### **Q3: 所有工具都会触发 System 消息吗？**

**当前实现**:
- ✅ `run_in_terminal` (CLI 命令) - 已支持
- ⏳ 其他工具 - 后续可以添加

---

## 📈 性能影响

### **消息数量**
- 每个工具调用 → 2 条 system 消息（executing + result）
- 对于复杂任务（多次工具调用），可能会增加消息数量

### **优化建议**
1. System 消息默认折叠，不影响阅读
2. 可以考虑添加"隐藏所有 system 消息"开关
3. 可以考虑限制 system 消息数量（只保留最近 N 条）

---

## 🎉 验收标准

### **功能验收** ✅
- [x] System 消息正确发送
- [x] System 消息正确解析
- [x] System 消息正确显示
- [x] UI 样式符合设计
- [x] 支持 dark mode

### **质量验收** ✅
- [x] TypeScript 类型完整
- [x] 无编译错误
- [x] 自动化测试通过
- [x] 代码已提交并推送

### **用户体验验收** ✅
- [x] 消息分类清晰
- [x] 视觉反馈友好
- [x] 交互设计合理
- [x] 响应式适配

---

## 📝 相关文档

- **实现方案**: `backend/devtools/system-role-implementation.md`
- **实现总结**: `backend/devtools/IMPLEMENTATION_SUMMARY.md`
- **测试脚本**: `test-system-role.sh`

---

## 🚀 下一步

如果想进一步增强 system 消息功能，可以考虑：

1. **执行时长统计**: 计算并显示工具执行时间
2. **彩色输出**: 根据成功/失败使用不同颜色
3. **日志过滤**: 提供 UI 开关控制显示哪些类型的 system 消息
4. **日志导出**: 允许下载执行日志
5. **实时日志流**: 对于长时间命令，实时显示 stdout/stderr

---

**验证完成日期**: 2026-02-18  
**版本**: v1.0.0  
**状态**: ✅ Production Ready
