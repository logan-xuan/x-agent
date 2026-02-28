/**
 * Agent Core WebSocket 连接管理 hook
 * 
 * 连接到 /ws/agent/{session_id} 端点，处理 agent_core 事件格式。
 * 
 * 消息格式:
 * - 发送: {"content": "用户消息"} 或 {"type": "abort"}
 * - 接收:
 *   - {"type": "chunk", "content": delta}
 *   - {"type": "thinking", "content": delta}
 *   - {"type": "message", "content": text, "model": model, "is_finished": true}
 *   - {"type": "tool_call", "tool_call_id": id, "name": name, "arguments": args}
 *   - {"type": "tool_result", "tool_call_id": id, "result": result, "is_error": bool}
 *   - {"type": "error", "message": error_message}
 */

import { useCallback, useState, useRef, useEffect } from 'react';
import { useWebSocket, ConnectionStatus } from './useWebSocket';

/** Agent 工具调用状态 */
export type AgentToolCallStatus = 'executing' | 'completed' | 'error';

/** Agent 工具调用 */
export interface AgentToolCall {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
    status: AgentToolCallStatus;
    result?: string;
    details?: Record<string, unknown>;
    isError?: boolean;
    durationMs?: number;
}

/** Agent 消息 */
export interface AgentMessage {
    id: string;
    sessionId: string;
    role: 'user' | 'assistant';
    content: string;
    createdAt: string;
    model?: string;
    provider?: string;
    stopReason?: string;
    usage?: {
        inputTokens?: number;
        outputTokens?: number;
    };
    toolCalls?: AgentToolCall[];
    thinking?: string;
}

/** useAgent hook 选项 */
interface UseAgentOptions {
    sessionId: string | null;
    wsBaseUrl?: string;
}

/** useAgent hook 返回值 */
interface UseAgentReturn {
    messages: AgentMessage[];
    sessionId: string | null;
    isLoading: boolean;
    streamingContent: string;
    streamingThinking: string;
    streamingModel: string;
    connectionStatus: ConnectionStatus;
    sendMessage: (content: string) => void;
    abort: () => void;
    clearMessages: () => void;
    createSession: (title?: string) => Promise<{ id: string; title: string }>;
    loadHistory: (sessionId: string) => Promise<void>;
}

const API_BASE_URL = '/api/v1';

/**
 * 构建 WebSocket 基础 URL
 * 在开发环境下使用当前页面的 host/port，让 Vite 代理 WebSocket 请求
 */
function getDefaultWsBaseUrl(): string {
    // 如果设置了环境变量，使用环境变量
    if (import.meta.env.VITE_WS_URL) {
        return import.meta.env.VITE_WS_URL;
    }

    // 否则使用当前页面的 host/port，让 Vite 代理处理
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws`;
}

/**
 * Agent Core WebSocket 管理 hook
 */
export function useAgent({
    sessionId,
    wsBaseUrl = getDefaultWsBaseUrl(),
}: UseAgentOptions): UseAgentReturn {
    const [messages, setMessages] = useState<AgentMessage[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [streamingContent, setStreamingContent] = useState('');
    const [streamingThinking, setStreamingThinking] = useState('');
    const [streamingModel, setStreamingModel] = useState('');
    const [currentSessionId, setCurrentSessionId] = useState<string | null>(sessionId);

    // 跟踪当前消息的工具调用
    const pendingToolCallsRef = useRef<Map<string, AgentToolCall>>(new Map());

    // WebSocket URL - 使用新的 agent 端点
    const wsUrl = currentSessionId ? `${wsBaseUrl}/agent/${currentSessionId}` : '';

    // 同步 sessionId
    useEffect(() => {
        setCurrentSessionId(sessionId);
    }, [sessionId]);

    // 处理 WebSocket 消息
    const handleWebSocketMessage = useCallback((data: unknown) => {
        if (!data || typeof data !== 'object') {
            console.error('[Agent] Invalid message format:', data);
            return;
        }

        const msg = data as Record<string, unknown>;
        const msgType = msg.type as string;

        if (!msgType) {
            console.error('[Agent] Message missing type field:', msg);
            return;
        }

        console.log('[Agent] Message:', msgType, msg);

        switch (msgType) {
            case 'chunk':
                // 文本流式增量
                if (msg.content) {
                    setStreamingContent(prev => prev + (msg.content as string));
                }
                break;

            case 'thinking':
                // 思考内容增量
                if (msg.content) {
                    setStreamingThinking(prev => prev + (msg.content as string));
                }
                break;

            case 'message':
                // 完整消息
                if (msg.is_finished) {
                    const finalContent = (msg.content as string) || streamingContent;

                    const assistantMessage: AgentMessage = {
                        id: `assistant-${Date.now()}`,
                        sessionId: currentSessionId || '',
                        role: 'assistant',
                        content: finalContent,
                        createdAt: new Date().toISOString(),
                        model: msg.model as string | undefined,
                        provider: msg.provider as string | undefined,
                        stopReason: msg.stop_reason as string | undefined,
                        usage: msg.usage as { inputTokens?: number; outputTokens?: number } | undefined,
                        toolCalls: pendingToolCallsRef.current.size > 0
                            ? Array.from(pendingToolCallsRef.current.values())
                            : undefined,
                        thinking: streamingThinking || undefined,
                    };

                    setMessages(prev => [...prev, assistantMessage]);
                    setStreamingContent('');
                    setStreamingThinking('');
                    setStreamingModel('');
                    setIsLoading(false);

                    // 清空待处理的工具调用
                    pendingToolCallsRef.current.clear();
                }
                break;

            case 'tool_call':
                // 工具调用开始
                {
                    const toolCall: AgentToolCall = {
                        id: msg.tool_call_id as string,
                        name: msg.name as string,
                        arguments: msg.arguments as Record<string, unknown> || {},
                        status: 'executing',
                    };
                    pendingToolCallsRef.current.set(toolCall.id, toolCall);

                    // 强制更新以显示工具调用
                    setMessages(prev => [...prev]);
                }
                break;

            case 'tool_result':
                // 工具调用结果
                {
                    const toolCallId = msg.tool_call_id as string;
                    const existing = pendingToolCallsRef.current.get(toolCallId);
                    if (existing) {
                        existing.status = (msg.is_error as boolean) ? 'error' : 'completed';
                        existing.result = msg.result as string;
                        existing.details = msg.details as Record<string, unknown> | undefined;
                        existing.isError = msg.is_error as boolean;
                        existing.durationMs = msg.duration_ms as number | undefined;
                        pendingToolCallsRef.current.set(toolCallId, existing);

                        // 强制更新以显示工具结果
                        setMessages(prev => [...prev]);
                    }
                }
                break;

            case 'tool_update':
                // 工具执行更新 (进度)
                console.log('[Agent] Tool update:', msg);
                break;

            case 'error':
                // 错误消息
                console.error('[Agent] Error:', msg.message);
                setIsLoading(false);
                break;

            case 'pong':
                // 心跳响应，忽略
                break;

            default:
                console.warn('[Agent] Unknown message type:', msgType);
        }
    }, [currentSessionId, streamingContent, streamingThinking]);

    // WebSocket 连接
    const { status, send } = useWebSocket({
        url: wsUrl,
        onMessage: handleWebSocketMessage,
        onConnect: () => {
            console.log('[Agent] WebSocket connected');
        },
        onDisconnect: () => {
            console.log('[Agent] WebSocket disconnected');
            setIsLoading(false);
        },
        onError: (error) => {
            console.error('[Agent] WebSocket error:', error);
            setIsLoading(false);
        },
    });

    // 发送消息
    const sendMessage = useCallback((content: string) => {
        if (!content.trim() || status !== 'connected') {
            return;
        }

        // 添加用户消息
        const userMessage: AgentMessage = {
            id: `user-${Date.now()}`,
            sessionId: currentSessionId || '',
            role: 'user',
            content: content,
            createdAt: new Date().toISOString(),
        };
        setMessages(prev => [...prev, userMessage]);

        // 重置状态
        setIsLoading(true);
        setStreamingContent('');
        setStreamingThinking('');
        pendingToolCallsRef.current.clear();

        // 发送消息
        send({ content });
    }, [status, currentSessionId, send]);

    // 中止处理
    const abort = useCallback(() => {
        if (status === 'connected') {
            send({ type: 'abort' });
            setIsLoading(false);
        }
    }, [status, send]);

    // 清空消息
    const clearMessages = useCallback(() => {
        setMessages([]);
        setStreamingContent('');
        setStreamingThinking('');
        pendingToolCallsRef.current.clear();
    }, []);

    // 创建新会话
    const createSession = useCallback(async (title?: string): Promise<{ id: string; title: string }> => {
        const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title }),
        });

        if (!response.ok) {
            throw new Error('Failed to create session');
        }

        const session = await response.json();
        setCurrentSessionId(session.id);
        setMessages([]);
        return session;
    }, []);

    // 加载会话历史
    const loadHistory = useCallback(async (sid: string) => {
        try {
            const response = await fetch(`${API_BASE_URL}/chat/sessions/${sid}/history`);

            if (!response.ok) {
                throw new Error('Failed to load history');
            }

            const history = await response.json();
            // 转换为 AgentMessage 格式
            const agentMessages: AgentMessage[] = history.map((msg: any) => ({
                id: msg.id || `msg-${Date.now()}-${Math.random()}`,
                sessionId: sid,
                role: msg.role as 'user' | 'assistant',
                content: msg.content,
                createdAt: msg.created_at || new Date().toISOString(),
                model: msg.metadata?.model,
                provider: msg.metadata?.provider,
            }));
            setMessages(agentMessages);
            setCurrentSessionId(sid);
        } catch (error) {
            console.error('Failed to load history:', error);
            throw error;
        }
    }, []);

    return {
        messages,
        sessionId: currentSessionId,
        isLoading,
        streamingContent,
        streamingThinking,
        streamingModel,
        connectionStatus: status,
        sendMessage,
        abort,
        clearMessages,
        createSession,
        loadHistory,
    };
}
