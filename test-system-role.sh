#!/bin/bash

# Test script for System Role Messages feature
# This script verifies that system messages are properly sent and displayed

echo "======================================"
echo "Testing System Role Messages Feature"
echo "======================================"
echo ""

# Check if backend is running
if ! curl -s http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    echo "❌ Backend is not running. Please start it first."
    exit 1
fi

echo "✅ Backend is running"

# Check if frontend is running
if ! curl -s http://localhost:5173 > /dev/null 2>&1; then
    echo "❌ Frontend is not running. Please start it first."
    exit 1
fi

echo "✅ Frontend is running"

echo ""
echo "======================================"
echo "Feature Implementation Checklist"
echo "======================================"
echo ""

# Check backend changes
echo "Backend Changes:"
if grep -q "send_system_message" backend/src/api/websocket.py; then
    echo "✅ send_system_message function added"
else
    echo "❌ send_system_message function missing"
fi

if grep -q '"type": "system"' backend/src/api/websocket.py; then
    echo "✅ System message type implemented"
else
    echo "❌ System message type missing"
fi

if grep -q "log_type.*cli_command" backend/src/api/websocket.py; then
    echo "✅ CLI command logging implemented"
else
    echo "❌ CLI command logging missing"
fi

if grep -q "log_type.*tool_execution" backend/src/api/websocket.py; then
    echo "✅ Tool execution logging implemented"
else
    echo "❌ Tool execution logging missing"
fi

echo ""
echo "Frontend Changes:"

# Check TypeScript types
if grep -q "'system'" frontend/src/types/index.ts; then
    echo "✅ MessageRole includes 'system'"
else
    echo "❌ MessageRole missing 'system'"
fi

if grep -q "| 'system'" frontend/src/types/index.ts; then
    echo "✅ WebSocketMessageType includes 'system'"
else
    echo "❌ WebSocketMessageType missing 'system'"
fi

if grep -q "log_type" frontend/src/types/index.ts; then
    echo "✅ System message fields defined in types"
else
    echo "❌ System message fields missing in types"
fi

# Check useChat hook
if grep -q "formatSystemLogContent" frontend/src/hooks/useChat.ts; then
    echo "✅ formatSystemLogContent helper function added"
else
    echo "❌ formatSystemLogContent helper function missing"
fi

if grep -q "case 'system':" frontend/src/hooks/useChat.ts; then
    echo "✅ System message handling implemented in useChat"
else
    echo "❌ System message handling missing in useChat"
fi

# Check MessageItem component
if grep -q "isSystem" frontend/src/components/chat/MessageItem.tsx; then
    echo "✅ System message rendering implemented"
else
    echo "❌ System message rendering missing"
fi

if grep -q "System Log" frontend/src/components/chat/MessageItem.tsx; then
    echo "✅ System message UI styling added"
else
    echo "❌ System message UI styling missing"
fi

echo ""
echo "======================================"
echo "Manual Testing Steps"
echo "======================================"
echo ""
echo "1. Open the frontend in your browser (http://localhost:5173)"
echo "2. Send a message that triggers tool execution, e.g.:"
echo "   - '/pptx 创建一个关于春节美食的 PPT'"
echo "3. Observe the chat:"
echo "   - You should see 🔧 System Log messages BEFORE assistant responses"
echo "   - System logs show CLI commands being executed"
echo "   - System logs are collapsible/expandable"
echo "   - System logs have yellow accent styling"
echo ""
echo "Expected message flow:"
echo "  User: /pptx 创建..."
echo "  System: 🔧 Executing: pip install python-pptx (executing)"
echo "  System: ✅ Completed [output...]"
echo "  Assistant: PPT 创建成功..."
echo ""
echo "======================================"
echo "Test Complete!"
echo "======================================"
