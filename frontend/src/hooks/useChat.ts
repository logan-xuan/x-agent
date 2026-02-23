/** Chat state management hook */

import { useCallback, useState, useRef } from 'react';
import { Message, Session, ToolCall, WebSocketMessage } from '../types';
import { useWebSocket, ConnectionStatus } from './useWebSocket';

interface UseChatOptions {
  sessionId: string | null;
  wsBaseUrl?: string;
}

interface UseChatReturn {
  messages: Message[];
  sessionId: string | null;
  isLoading: boolean;
  streamingContent: string;
  streamingModel: string;
  connectionStatus: ConnectionStatus;
  sendMessage: (content: string) => void;
  confirmToolCall: (toolCallId: string, confirmationId?: string, command?: string) => void;
  createSession: (title?: string) => Promise<Session>;
  loadHistory: (sessionId: string) => Promise<void>;
}

const API_BASE_URL = '/api/v1';

/** Format system log content for display */
function formatSystemLogContent(
  logType: string | undefined,
  logData: Record<string, unknown> | undefined
): string {
  if (!logType || !logData) {
    return `[System] ${JSON.stringify(logData || {})}`;
  }

  switch (logType) {
    case 'cli_command':
      return `🔧 Executing: ${logData.command || 'Unknown command'} (${logData.status || 'running'})`;
    
    case 'tool_execution':
      const status = logData.success ? '✅' : '❌';
      const output = logData.output ? `\n${logData.output}` : '';
      const error = logData.error ? `\nError: ${logData.error}` : '';
      return `${status} Completed${output}${error}`;
    
    case 'error':
      return `⚠️ System Error: ${logData.error || 'Unknown error'}`;
    
    case 'info':
      return `ℹ️ ${logData.message || 'System info'}`;
    
    default:
      return `[System:${logType}] ${JSON.stringify(logData)}`;
  }
}

export function useChat({
  sessionId,
  wsBaseUrl = 'ws://localhost:8000/ws',
}: UseChatOptions): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingModel, setStreamingModel] = useState('');
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(sessionId);

  // Track pending tool calls for the current assistant message
  const pendingToolCallsRef = useRef<Map<string, ToolCall>>(new Map());

  // WebSocket URL - connection is automatic when url changes
  const wsUrl = currentSessionId ? `${wsBaseUrl}/chat/${currentSessionId}` : '';

  // Handle incoming WebSocket messages
  const handleWebSocketMessage = useCallback((data: unknown) => {
    // Enhanced debug logging - log ALL messages with type info
    console.log('[WS_MESSAGE] Raw data type:', typeof data);
    console.log('[WS_MESSAGE] Raw data:', JSON.stringify(data, null, 2));
    
    // Defensive check: ensure data is a valid object
    if (!data || typeof data !== 'object') {
      console.error('[WS_MESSAGE] Invalid message format:', data);
      return;
    }
    
    const msg = data as Record<string, unknown> & {
      type: string;
      content?: string;
      is_finished?: boolean;
      model?: string;
      error?: string | Record<string, unknown>;
      session_id?: string;
      name?: string;
      arguments?: Record<string, unknown>;
      tool_call_id?: string;
      success?: boolean;
      result?: unknown;
      log_type?: 'cli_command' | 'tool_execution' | 'error' | 'info';
      log_data?: Record<string, unknown>;
    };
    
    // Validate message type
    if (!msg.type || typeof msg.type !== 'string') {
      console.error('[WS_MESSAGE] Message missing type field:', msg);
      return;
    }

    console.log('[WS_MESSAGE] Parsed message type:', msg.type);
    console.log('[WS_MESSAGE] Message object:', msg);

    // Debug logging for tool events
    if (msg.type === 'tool_call' || msg.type === 'tool_result' || msg.type === 'awaiting_confirmation') {
      console.log('[DEBUG] WebSocket message:', msg.type, msg);
    }
    
    // Debug logging for compression status
    if (msg.type === 'compression_status') {
      console.log('[DEBUG] Compression status:', {
        session_id: msg.session_id,
        message_count: (msg as any).message_count,
        token_count: (msg as any).token_count,
        threshold_rounds: (msg as any).threshold_rounds,
        threshold_tokens: (msg as any).threshold_tokens,
        needs_compression: (msg as any).needs_compression,
        compressed: (msg as any).compressed,
      });
    }

    switch (msg.type) {
      case 'chunk':
        // Streaming chunk
        if (msg.content) {
          setStreamingContent(prev => prev + msg.content);
        }
        if (msg.model) {
          setStreamingModel(msg.model);
        }
        break;

      case 'message':
        // Complete message - use the final content from backend
        if (msg.is_finished) {
          // Use the content from the message (backend sends full content)
          const finalContent = msg.content || streamingContent;

          // Create the final message with any pending tool calls
          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            session_id: msg.session_id || currentSessionId || '',
            role: 'assistant',
            content: finalContent,
            created_at: new Date().toISOString(),
            metadata: msg.model ? { model: msg.model } : undefined,
            tool_calls: pendingToolCallsRef.current.size > 0
              ? Array.from(pendingToolCallsRef.current.values())
              : undefined,
          };

          setMessages(prev => [...prev, assistantMessage]);
          setStreamingContent('');
          setStreamingModel('');
          setIsLoading(false);

          // Clear pending tool calls
          pendingToolCallsRef.current.clear();
        }
        break;

      case 'tool_call':
        // Tool call started - track it
        if (msg.tool_call_id && msg.name) {
          const toolCall: ToolCall = {
            id: msg.tool_call_id,
            name: msg.name as ToolCall['name'],
            arguments: msg.arguments || {},
            status: 'executing',
          };
          pendingToolCallsRef.current.set(msg.tool_call_id, toolCall);

          // Update the streaming message to show tool call
          setMessages(prev => {
            const lastMsg = prev[prev.length - 1];
            
            // If last message is assistant, append tool call to it
            if (lastMsg && lastMsg.role === 'assistant') {
              const updatedMsg: Message = {
                ...lastMsg,
                tool_calls: lastMsg.tool_calls
                  ? [...lastMsg.tool_calls, toolCall]
                  : [toolCall],
              };
              return [...prev.slice(0, -1), updatedMsg];
            }
            
            // Otherwise create a new assistant message with the tool call
            const newAssistantMsg: Message = {
              id: `assistant-${Date.now()}`,
              session_id: msg.session_id || currentSessionId || '',
              role: 'assistant',
              content: '',
              created_at: new Date().toISOString(),
              tool_calls: [toolCall],
            };
            return [...prev, newAssistantMsg];
          });
        }
        break;

      case 'tool_result':
        // Tool execution completed - update the tool call
        console.log('[DEBUG] tool_result received:', {
          tool_call_id: msg.tool_call_id,
          success: msg.success,
          result: msg.result,
        });
        
        if (msg.tool_call_id) {
          // Determine status based on result metadata
          const resultData = typeof msg.result === 'object' && msg.result !== null ? msg.result as Record<string, unknown> : null;
          let newStatus: ToolCall['status'] = msg.success ? 'completed' : 'error';
          
          console.log('[DEBUG] resultData:', resultData);
          
          if (resultData?.requires_confirmation) {
            newStatus = 'needs_confirmation';
            // Stop loading since we're waiting for user confirmation
            setIsLoading(false);
            setStreamingContent('');
            console.log('[DEBUG] Setting needs_confirmation status');
          } else if (resultData?.is_blocked) {
            newStatus = 'blocked';
          }
          
          const existingCall = pendingToolCallsRef.current.get(msg.tool_call_id);
          const updatedCall: ToolCall = existingCall
            ? { ...existingCall, status: newStatus, result: msg.result as any }
            : {
                id: msg.tool_call_id,
                name: 'run_in_terminal' as const,
                arguments: { command: ((resultData as any)?.command as string) || '' },
                status: newStatus,
                result: msg.result as any,
              };
          
          pendingToolCallsRef.current.set(msg.tool_call_id, updatedCall);

          // Update the message with the tool result
          setMessages(prev => {
            return prev.map(message => {
              if (message.tool_calls) {
                const hasToolCall = message.tool_calls.some(tc => tc.id === msg.tool_call_id);
                if (hasToolCall) {
                  return {
                    ...message,
                    tool_calls: message.tool_calls.map(tc =>
                      tc.id === msg.tool_call_id ? updatedCall : tc
                    ),
                  };
                }
              }
              return message;
            });
          });
        }
        break;

      case 'awaiting_confirmation':
        // High-risk command is waiting for user confirmation
        // Stop loading state since we're waiting for user action
        setIsLoading(false);
        setStreamingContent('');
        break;

      case 'system':
        // System log message (CLI commands, tool executions, errors, etc.)
        const systemMessage: Message = {
          id: `system-${Date.now()}-${Math.random()}`,
          session_id: msg.session_id || currentSessionId || '',
          role: 'system',
          content: formatSystemLogContent(msg.log_type, msg.log_data),
          created_at: new Date().toISOString(),
          metadata: {
            log_type: msg.log_type,
            ...msg.log_data,
          },
        };
        
        setMessages(prev => [...prev, systemMessage]);
        break;

      case 'error':
        // Fix: Handle both string and object error formats with defensive checks
        let errorDisplay: string;
        try {
          if (typeof msg.error === 'string') {
            errorDisplay = msg.error;
          } else if (msg.error && typeof msg.error === 'object') {
            errorDisplay = (msg.error as any)?.message || JSON.stringify(msg.error);
          } else {
            errorDisplay = 'Unknown error occurred';
          }
        } catch (e) {
          errorDisplay = `Error processing error message: ${e}`;
        }
        
        console.error('Chat error:', errorDisplay);
        setIsLoading(false);
        setStreamingContent('');
        break;
    }
  }, [currentSessionId, streamingContent]);

  // WebSocket connection - automatic based on wsUrl
  const { status: connectionStatus, send: wsSend } = useWebSocket({
    url: wsUrl,
    onMessage: handleWebSocketMessage,
    onConnect: () => {
      console.log('WebSocket connected');
    },
    onDisconnect: () => {
      console.log('WebSocket disconnected');
    },
  });

  // Send message via WebSocket
  const sendMessage = useCallback((content: string) => {
    if (!currentSessionId || connectionStatus !== 'connected') {
      console.warn('Cannot send message: not connected');
      return;
    }

    // Add user message immediately
    const userMessage: Message = {
      id: `user-${Date.now()}`,
      session_id: currentSessionId,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    // Send via WebSocket
    wsSend({ content });
  }, [currentSessionId, connectionStatus, wsSend]);

  // Confirm a high-risk tool call
  const confirmToolCall = useCallback((toolCallId: string, confirmationId?: string, command?: string) => {
    if (!currentSessionId || connectionStatus !== 'connected') {
      console.warn('Cannot confirm tool call: not connected');
      return;
    }

    // Send confirmation via WebSocket
    wsSend({
      type: 'tool_confirm',
      tool_call_id: toolCallId,
      confirmation_id: confirmationId,
      command: command,
    });

    // Update local state to show confirmation sent
    setMessages(prev => {
      return prev.map(message => {
        if (message.tool_calls) {
          return {
            ...message,
            tool_calls: message.tool_calls.map(tc =>
              tc.id === toolCallId
                ? { ...tc, status: 'executing' as const }
                : tc
            ),
          };
        }
        return message;
      });
    });
  }, [currentSessionId, connectionStatus, wsSend]);

  // Create a new session
  const createSession = useCallback(async (title?: string): Promise<Session> => {
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

  // Load session history
  const loadHistory = useCallback(async (sid: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/sessions/${sid}/history`);

      if (!response.ok) {
        throw new Error('Failed to load history');
      }

      const history = await response.json();
      setMessages(history);
      setCurrentSessionId(sid);
    } catch (error) {
      console.error('Failed to load history:', error);
    }
  }, []);

  return {
    messages,
    sessionId: currentSessionId,
    isLoading,
    streamingContent,
    streamingModel,
    connectionStatus,
    sendMessage,
    confirmToolCall,
    createSession,
    loadHistory,
  };
}
