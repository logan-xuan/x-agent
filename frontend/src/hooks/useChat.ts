/** Chat state management hook */

import { useCallback, useState } from 'react';
import { Message, Session } from '../types';
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
  createSession: (title?: string) => Promise<Session>;
  loadHistory: (sessionId: string) => Promise<void>;
}

const API_BASE_URL = 'http://localhost:8000/api/v1';

export function useChat({
  sessionId,
  wsBaseUrl = 'ws://localhost:8000/ws',
}: UseChatOptions): UseChatReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingModel, setStreamingModel] = useState('');
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(sessionId);
  
  // WebSocket URL - connection is automatic when url changes
  const wsUrl = currentSessionId ? `${wsBaseUrl}/chat/${currentSessionId}` : '';
  
  // Handle incoming WebSocket messages
  const handleWebSocketMessage = useCallback((data: unknown) => {
    const msg = data as {
      type: string;
      content?: string;
      is_finished?: boolean;
      model?: string;
      error?: string;
      session_id?: string;
    };
    
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
        // Note: msg.content contains the FULL content from backend, 
        // NOT additional content to append to streamingContent
        if (msg.is_finished) {
          // Use the content from the message (backend sends full content)
          const finalContent = msg.content || streamingContent;
          
          // Create the final message
          const assistantMessage: Message = {
            id: `assistant-${Date.now()}`,
            session_id: msg.session_id || currentSessionId || '',
            role: 'assistant',
            content: finalContent,
            created_at: new Date().toISOString(),
            metadata: msg.model ? { model: msg.model } : undefined,
          };
          
          setMessages(prev => [...prev, assistantMessage]);
          setStreamingContent('');
          setStreamingModel('');
          setIsLoading(false);
        }
        break;
        
      case 'error':
        console.error('Chat error:', msg.error);
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
    createSession,
    loadHistory,
  };
}
